# Workload Identity Federation

Step 7 of `SETUP.md`, kept apart because it is the step that costs the most
time when it goes wrong. Almost every mistake in it produces the same
credentials error at the same point in a deployment, and the message names
none of the possible causes.

The point of all this is that **no service account key exists anywhere**. A
long lived JSON key stored as a repository secret is the credential most likely
to leak, and there is no reason to hold one. GitHub mints a short lived OIDC
token for each job, and Google exchanges it for a short lived access token, on
the conditions this configuration sets.

I continue in the shell from `SETUP.md`, with `PROJECT_ID`, `PROJECT_NUMBER`,
`POOL_ID`, `PROVIDER_ID`, `GITHUB_REPOSITORY` and the `sa_email` helper still
set.

## What is trusted, and by whom

| Deployer | May be impersonated by | Which GitHub guards |
|---|---|---|
| `github-deployer-staging` | A job running in the `staging` environment | The environment accepts the branch `develop` only |
| `github-deployer-prod` | A job running in the `production` environment | The environment needs my approval and accepts `v*` tags only |

Each deployer is bound to exactly one principal, the subject of a job in its
own environment. A job on a feature branch or in a pull request presents a
different subject, so it can obtain neither identity. The earlier version of
this file trusted every job in the repository, which would have let a job on
any branch deploy.

## Piece 1, the pool

```bash
gcloud iam workload-identity-pools create "${POOL_ID}" \
  --location="global" \
  --display-name="GitHub Actions" \
  --project="${PROJECT_ID}"
```

## Piece 2, read the subject GitHub really issues

I do this before the provider and before any binding, because getting it wrong
cost me a failed run.

GitHub now issues an immutable subject for this repository. The subject is not
`repo:OWNER/REPO:environment:NAME`. It carries the numeric ids of the owner and
the repository as well.

```text
repo:OWNER@OWNER_ID/REPO@REPOSITORY_ID:environment:NAME
```

The exact prefix for a repository is read from GitHub. The reply carries
`sub_claim_prefix`.

```bash
gh api "repos/${GITHUB_REPOSITORY}/actions/oidc/customization/sub"
```

I set two variables from what it returns. `SUBJECT_PREFIX` is everything in the
subject before `:environment:`, and `REPOSITORY_ID` is the number after `REPO@`.

```bash
export SUBJECT_PREFIX="repo:OWNER@OWNER_ID/REPO@REPOSITORY_ID"
export REPOSITORY_ID="REPOSITORY_ID"
```

## Piece 3, the provider, its mapping and its condition

These are one command, which is why they are easy to get wrong together.

The **attribute condition** is not optional. Google refuses to create a GitHub
OIDC provider without one, because a provider with no condition trusts every
GitHub Actions job on the whole platform. Mine names the repository twice, by
name and by its numeric id. The id does not change if the repository is
renamed, and somebody who later takes over an abandoned name gets a different
id, so the name alone would be the weaker check.

The **attribute mapping** carries the subject, which the bindings in piece 4
match on, and four attributes a later binding could refer to.

```bash
gcloud iam workload-identity-pools providers create-oidc "${PROVIDER_ID}" \
  --location="global" \
  --workload-identity-pool="${POOL_ID}" \
  --display-name="GitHub Actions OIDC" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner,attribute.environment=assertion.environment" \
  --attribute-condition="assertion.repository == '${GITHUB_REPOSITORY}' && assertion.repository_id == '${REPOSITORY_ID}'" \
  --project="${PROJECT_ID}"
```

## Piece 4, one binding for each deployer

The member is a single `principal`, not a `principalSet`. It names one subject
and nothing wider. The GitHub environment is `production` and the service
account is `github-deployer-prod`, and the binding has to use each name in the
right place.

```bash
POOL_PATH="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}"

gcloud iam service-accounts add-iam-policy-binding \
  "$(sa_email github-deployer-staging)" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principal://iam.googleapis.com/${POOL_PATH}/subject/${SUBJECT_PREFIX}:environment:staging" \
  --project="${PROJECT_ID}"

gcloud iam service-accounts add-iam-policy-binding \
  "$(sa_email github-deployer-prod)" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principal://iam.googleapis.com/${POOL_PATH}/subject/${SUBJECT_PREFIX}:environment:production" \
  --project="${PROJECT_ID}"
```

The path uses the **project number**, not the project id.

## The other bindings a deployment needs

They are granted in `SETUP.md` and listed here because the failure table refers
to them.

| Binding | On | Granted in |
|---|---|---|
| `roles/run.admin` and `roles/artifactregistry.writer` for each deployer | The project | Step 4 |
| `roles/iam.serviceAccountUser` for each deployer | Its own environment's runtime identity only | Step 4 |
| `roles/secretmanager.secretAccessor` for each deployer | Its own `database-migration-url` secret only | Step 6 |
| `roles/secretmanager.secretAccessor` for each runtime identity | Its own `database-url`, `jwt-secret` and `resend-api-key` | Step 6 |

Deploying a revision that runs as the runtime identity counts as using that
identity, which is what `serviceAccountUser` allows. It is the binding most
often missed.

The separation protects the secrets and the data. It does not fence off the
services from each other, because `roles/run.admin` is granted on the project.
The staging deployer could change the production service. It still could not
make a revision read a production secret, since it may not act as the
production runtime identity and the staging one has no access to those secrets.

## Read back the provider resource name

This exact string, not the provider id, goes into the
`GCP_WORKLOAD_IDENTITY_PROVIDER` secret of both GitHub environments in step 9.
It is the same value in both. What differs is `GCP_DEPLOY_SERVICE_ACCOUNT`.

```bash
gcloud iam workload-identity-pools providers describe "${PROVIDER_ID}" \
  --location="global" \
  --workload-identity-pool="${POOL_ID}" \
  --project="${PROJECT_ID}" \
  --format='value(name)'
# projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github/providers/github-actions
```

## The failure that cost a run

The first deployment authenticated and then failed.

**Symptom.** The step "Authenticate to Google Cloud" is green. The first
`gcloud` call after it fails with "Unable to acquire impersonated credentials"
and `Permission 'iam.serviceAccounts.getAccessToken' denied`.

**Cause.** The binding in piece 4 named the old subject form,
`repo:OWNER/REPO:environment:staging`. GitHub presented the immutable form with
the two ids in it. The subjects did not match, so nothing was allowed to
impersonate the deployer.

**Why it hides.** The auth step only writes a credential file. It exchanges no
token, so it passes whatever the bindings say. The first real exchange happens
at the first `gcloud` call that needs a token, and that is where a federation
mistake shows up.

**Fix.** I read the prefix with the command in piece 2, remove the wrong
binding with the command at the end of this file, add the right one and run the
failed run again.

## When it fails anyway

I work down this table instead of guessing. All but the first row surface after
the auth step, not in it.

| Symptom | Almost always |
|---|---|
| The auth step itself fails at once | The job lacks `id-token: write`, so the runner cannot mint the OIDC token |
| "Unable to acquire impersonated credentials" with `iam.serviceAccounts.getAccessToken` denied | The `workloadIdentityUser` binding names a subject the job does not present. I check the immutable subject form first, then the environment name, then that the path uses the project number |
| The same error on a release only | The binding says `prod` where the GitHub environment is `production`, or the job did not run in that environment |
| An error saying the credential was rejected by the attribute condition | The repository name or `REPOSITORY_ID` in the condition does not match this repository |
| The provider cannot be found | The provider resource name in the GitHub secret is wrong, usually the project id in place of the number |
| The image push is denied, naming `artifactregistry.repositories.uploadArtifacts` | `roles/artifactregistry.writer` is missing for that deployer |
| The migration step cannot read its secret, or reports an empty migration URL | That deployer lacks `secretAccessor` on its own `database-migration-url` |
| The deploy is denied, naming `iam.serviceAccounts.actAs` | `roles/iam.serviceAccountUser` on that environment's runtime identity is missing, or the variable names the other environment's runtime identity |
| The deploy is denied with a `run.` permission | `roles/run.admin` is missing for that deployer |
| The revision is refused or will not start, naming a secret | The runtime identity lacks `secretAccessor` on one of its three secrets |
| Everything looks right and the exchange still fails | `iamcredentials.googleapis.com` or `sts.googleapis.com` was never enabled. See step 2 |

## Proving it works

There is no manual trigger on either workflow, so the proof is a staging
deployment. Each step after the auth step exercises one grant. The image push
proves the federation binding and the registry role. The migration proves the
secret grant. The deploy proves `run.admin` and `serviceAccountUser`. A run
that fails part way can be run again without a new commit.

## Revoking access

There is no key to rotate, which is the whole point. To cut an environment off
I remove its binding. Access stops on the next job, and nothing has to be
regenerated or handed out again.

```bash
gcloud iam service-accounts remove-iam-policy-binding \
  "$(sa_email github-deployer-staging)" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principal://iam.googleapis.com/${POOL_PATH}/subject/${SUBJECT_PREFIX}:environment:staging" \
  --project="${PROJECT_ID}"
```
