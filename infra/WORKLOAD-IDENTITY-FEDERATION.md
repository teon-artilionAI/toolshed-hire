# Workload Identity Federation

Step 7 of `SETUP.md`, separated out because it is the step that costs a day
when it goes wrong. Every mistake in it produces the same opaque credentials
error at the same point in the deploy workflow, and the message names none of
the possible causes.

The point of all this is that **no service account key exists anywhere**. A
long lived JSON key stored as a repository secret is the credential most likely
to leak, and there is no reason to hold one. Instead GitHub mints a short lived
OIDC token for each job, and Google exchanges it for a short lived access
token, on conditions this configuration sets.

Continue in the shell from `SETUP.md`, with `PROJECT_ID`, `PROJECT_NUMBER`,
`POOL_ID`, `PROVIDER_ID`, `GITHUB_REPOSITORY`, `GITHUB_OWNER`,
`DEPLOY_SA_EMAIL` and `RUNTIME_SA_EMAIL` still set.

## Piece 1, the pool

```bash
gcloud iam workload-identity-pools create "${POOL_ID}" \
  --location="global" \
  --display-name="GitHub Actions" \
  --project="${PROJECT_ID}"
```

## Pieces 2, 3 and 4, the provider, its mapping and its condition

These three are one command, which is why they are so easy to get wrong
together.

The **attribute condition** is not a hardening suggestion. Google refuses to
create a GitHub OIDC provider without one, because a provider with no condition
trusts every GitHub Actions job on the entire platform, including a job in a
repository belonging to somebody you have never met. The error when you omit it
is clear, unlike everything else in this file.

The **attribute mapping** must include `attribute.repository`, because the IAM
binding in piece 5a refers to it and cannot be written against an attribute the
provider never produced.

```bash
gcloud iam workload-identity-pools providers create-oidc "${PROVIDER_ID}" \
  --location="global" \
  --workload-identity-pool="${POOL_ID}" \
  --display-name="GitHub Actions OIDC" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
  --attribute-condition="assertion.repository_owner == '${GITHUB_OWNER}'" \
  --project="${PROJECT_ID}"
```

## Piece 5, three IAM bindings

```bash
# a. Let this repository, and only this repository, impersonate the deployer.
#    Without this the token exchange succeeds and the impersonation fails,
#    which is the most confusing of all the failure modes because the log
#    shows a successful authentication step before it.
gcloud iam service-accounts add-iam-policy-binding "${DEPLOY_SA_EMAIL}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/attribute.repository/${GITHUB_REPOSITORY}" \
  --project="${PROJECT_ID}"

# b. Let the deployer create Cloud Run revisions.
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${DEPLOY_SA_EMAIL}" \
  --role="roles/run.admin"

# c. Let the deployer push images to Artifact Registry.
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${DEPLOY_SA_EMAIL}" \
  --role="roles/artifactregistry.writer"
```

### The fourth binding, which is the one most often missed

Deploying a revision that runs as the runtime identity counts as *using* that
identity, so the deployer needs permission on it. This is not part of the
canonical trio and is skipped by almost everyone following a checklist:

```bash
gcloud iam service-accounts add-iam-policy-binding "${RUNTIME_SA_EMAIL}" \
  --member="serviceAccount:${DEPLOY_SA_EMAIL}" \
  --role="roles/iam.serviceAccountUser" \
  --project="${PROJECT_ID}"
```

The fifth, `roles/secretmanager.secretAccessor` on the migration URL secret,
was granted in step 6 of `SETUP.md`.

## Read back the provider resource name

This exact string, not the provider id, is what goes into the
`GCP_WORKLOAD_IDENTITY_PROVIDER` secret in step 8:

```bash
gcloud iam workload-identity-pools providers describe "${PROVIDER_ID}" \
  --location="global" \
  --workload-identity-pool="${POOL_ID}" \
  --project="${PROJECT_ID}" \
  --format='value(name)'
# projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github/providers/github-actions
```

Note the **project number**, not the project id. Substituting the id here is a
common failure and produces, of course, an opaque credentials error.

## When it fails anyway

The auth step of `.github/workflows/deploy.yml` is where all of this surfaces.
Work down this table rather than guessing.

| Symptom | Almost always |
|---|---|
| `Unable to acquire impersonated credentials` | Binding 5a missing, or its principalSet names the wrong repository, or it uses the project id instead of the project number |
| `The caller does not have permission` on the deploy | Binding 5b or the fourth binding, `iam.serviceAccountUser` on the runtime account, is missing |
| `denied: Permission artifactregistry.repositories.uploadArtifacts denied` | Binding 5c missing |
| `Invalid value for attribute condition` at provider creation | The condition references an attribute the mapping does not produce |
| `Service account impersonation is not allowed` for this identity | The provider has no attribute condition, or the condition excludes this repository owner |
| `Requested entity was not found` at the auth step | The provider resource name in the GitHub secret is wrong, usually the project id in place of the number |
| Everything is correct and it still fails | `iamcredentials.googleapis.com` or `sts.googleapis.com` was never enabled. See step 2 |

## Verifying it without a deployment

The cheapest confirmation is to run the deploy workflow manually against a
commit that is already deployed, using the `workflow_dispatch` trigger. It
exercises exactly the same authentication path and touches nothing new if the
image and the schema have not changed.

```bash
gh workflow run deploy.yml --ref main
gh run watch
```

## Rotating or revoking access

There is no key to rotate, which is the entire point. To revoke the
repository's access, remove binding 5a. Access stops on the next job, and
nothing has to be regenerated or redistributed.

```bash
gcloud iam service-accounts remove-iam-policy-binding "${DEPLOY_SA_EMAIL}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/attribute.repository/${GITHUB_REPOSITORY}" \
  --project="${PROJECT_ID}"
```
