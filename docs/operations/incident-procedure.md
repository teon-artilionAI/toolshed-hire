# Incident procedure

Toolshed Hire, Task 3. Written on 23 October 2026.

## Who is responsible

Teon Kleynhans is the incident lead, the only engineer and the account holder
for Google Cloud, Neon, Vercel, Resend and GitHub. There is no separate on-call
rota for a one-person project. The lecturer is not an incident responder.

The incident lead decides whether an event is an incident, directs containment,
approves any production traffic change, and writes the record afterwards.

## What counts as an incident

| Severity | Example | First action |
|---|---|---|
| S1 | The site or API is down for every user, or customer data may be exposed | Contain first, then tell Teon and the affected operator |
| S2 | A security control has failed, a secret may be exposed, or one role cannot work | Contain the exposure, keep the service up if it is safe |
| S3 | A single journey is wrong or slow, with no data exposure | Record, fix in normal working hours |

A suspected secret exposure is S2 until it is proved otherwise. A leaked key is
never tested against a real system to see whether it still works.

## Detect and record

1. The first signal is an alert from the liveness check, the hourly full-health
   job or an alert policy, where those have been created. A person who notices a
   fault is the second.
2. Open an issue with the time, what was seen, which service and which screen.
   Do not put a secret, a customer's details or a database dump in the issue.
3. Preserve the evidence: the request id, the Cloud Run revision, the time
   window, and the relevant log lines with personal data removed.
4. Decide the severity. If in doubt, treat it as S2.

## Contain, in this order

1. Stop the exposure before restoring convenience. If a secret is exposed,
   disable or rotate it before anything else.
2. If the fault is in a release, shift production traffic to the previous ready
   revision, as the rollback section of
   [OPERATIONS.md](../../infra/OPERATIONS.md#rollback) describes. That is a
   traffic change, so the incident lead records the approval in the issue first.
   A rollback is a manual traffic change. It is not a release, so it does not
   go through the `production` environment approval.
3. If the fault is a bad data change, stop the writing path and preserve the
   database state. Do not restore production over the top of it. Use a new Neon
   branch for any restore and check it before pointing anything at it.
4. If email is the fault, the service keeps running. A missing Resend key turns
   email off with a warning, and the booking flow still works (C-33). The
   `Toolshed Hire: email is switched off` alert is the compensating control, and
   it is defined in
   [create-alert-policies.sh](../../infra/scripts/create-alert-policies.sh).
5. Tell the affected operator through its own support channel when the fault is
   theirs. Do not wait for a root cause to ask for help.

### A failed production deployment

The production workflow shifts traffic to the new API before it deploys the
frontend. If a run fails between those two steps, the site is on the old
frontend and the new API. Re-run the failed run. If that is not possible,
restore the service's previous access setting and roll the API traffic back,
then confirm the rewrite before closing the incident. On 28 October 2026 a
failure at the maintenance job step left production on that gap for six and a
half hours. The job step now runs after the frontend, so that failure cannot
repeat.

## Secret rotation

The application holds these secrets. Each rotation is done in the place that
owns it, then the runtime is redeployed or restarted so it reads the new value.

| Secret | Where it lives | Rotation |
|---|---|---|
| Resend API key | Google Secret Manager, `staging-resend-api-key` and `prod-resend-api-key` | Create a new key in Resend, add a new secret version, redeploy the service, revoke the old key in Resend |
| Vercel token | GitHub environment secret `VERCEL_TOKEN`, in both environments | Create a new token in Vercel, update the secret in both environments, revoke the old token |
| JWT signing secret | Secret Manager, `staging-jwt-secret` and `prod-jwt-secret` | Add a new version and redeploy. The service signs with the new version, the access tokens already issued are refused, and each browser refreshes once. Refresh sessions are not affected. |
| Database URLs | Secret Manager, `staging-database-url` and `prod-database-url` for the pooled string, `staging-database-migration-url` and `prod-database-migration-url` for the direct string | Set a new password with [provision_roles.py](../../backend/scripts/provision_roles.py), add new versions of the pooled and direct secrets, and redeploy. New connections with the old password fail once it changes, so do this in a quiet period. |
| Google service account keys | None stored. Workload Identity Federation is used. | If a key ever appears, delete it and investigate how it was created |
| GitHub token or deploy key | GitHub only | Revoke in GitHub, create a new one, update the holder |

The exact `gcloud secrets versions add` command is run by the incident lead
with the new value piped from its generator or from the provider. The secret is
never pasted into the issue, the chat or the report.

## Restore and verify

- A rollback follows the rollback section of
  [OPERATIONS.md](../../infra/OPERATIONS.md#rollback).
- A database restore starts a new Neon branch from a point in time, points a
  staging deployment at it, runs the smoke test, and only then restores the
  staging configuration.
- After either, run the smoke test. On staging, run the three role journeys.
  Record the revision and the time.
- A rollback pins production traffic to the revision named. The next production
  deployment shifts traffic to the latest revision as its own step and clears
  the pin. On staging, release the pin by hand after the next deployment and
  confirm that the revision in the health answer has changed.

## POPIA notice

If personal information may have been accessed or acquired by an unauthorised
person, the incident lead notifies the Information Regulator and the affected
data subjects as soon as reasonably possible after discovery, as section 22 of
POPIA requires. The notice says what happened, what information was involved,
what has been done, and what the person can do. The incident issue records the
time the decision was made and the time each notice was sent.

A suspected exposure that is proved not to have involved personal information
is recorded with that conclusion and the evidence.

## After the incident

Within two working days, write a short record: the timeline, the cause, what
was contained, what was restored, the customer or operator impact, and one
action with an owner and a date. Add the action to the issue tracker. If the
cause was a missing test, add the test before closing the issue.

## Rehearsal

The tabletop is a discussion, not a live test. It must not leak or rotate a
real key. The rehearsal checks that the order above is usable and that every
command has an owner.
