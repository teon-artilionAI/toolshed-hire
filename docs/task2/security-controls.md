# Security controls

The Task 1 design document sets out 44 security controls, C-01 to C-44, in seven
layers from the platform to the evidence. This file takes each one in my own
short words and says where it stands on `develop` today. I only mark a control
in place when I can point to the file, test or workflow step that shows it.

<!-- final: recheck every row after branches 015 to 022, and before task2-v1.0 -->

| Status | Controls |
|---|---|
| In place | 28 |
| Partly in place | 7 |
| Replaced by something else | 1 |
| Planned for the final release | 8 |

The ones that are not fully in place are C-01, C-02, C-06, C-09, C-24, C-29 to
C-34, C-37, C-38, C-43 and C-44, and C-03 is replaced. Each row below says what
is missing.

## Layer 1, the platform

| Control | What it means | Status | Evidence |
|---|---|---|---|
| C-01 | Filter traffic at the edge with the rules the hosting plan offers | Planned for the final release | No edge rule is set on the Vercel project yet. The instance cap under C-03 is what bounds a flood today. |
| C-02 | HTTPS only, with one public hostname, so the rewrite is the only way in | Partly in place | The site has one public hostname, and the browser reaches the API only through the rewrite in [vercel.json](../../frontend/vercel.json). The API service still accepts calls on its own platform address, which is kept out of the repository and the logs but is not blocked, as [VERCEL-REWRITE.md](../../infra/VERCEL-REWRITE.md#what-this-does-not-do) says. The API checks every request itself either way. |
| C-03 | Cap the number of API instances so a flood cannot run up a bill | Replaced | Capped at one instance in each environment instead of four in production, through `CLOUD_RUN_MAX_INSTANCES` in [deploy-production.yml](../../.github/workflows/deploy-production.yml) and [deploy-staging.yml](../../.github/workflows/deploy-staging.yml). [deviations.md](deviations.md) says why. |
| C-04 | Throttle in the application as well as at the platform | In place | [throttle.py](../../backend/app/application/throttle.py), with its counters in [rate_limit.py](../../backend/app/infrastructure/rate_limit.py). Tested by [test_throttle.py](../../backend/tests/unit/test_throttle.py) and [test_login_throttle_and_timing.py](../../backend/tests/api/test_login_throttle_and_timing.py). |
| C-05 | Reach the database through its pooled endpoint over TLS, with the credentials in Secret Manager | In place | Steps 5 and 6 of [SETUP.md](../../infra/SETUP.md). The connection verifies the server certificate, and [deploy-api.sh](../../infra/scripts/deploy-api.sh) hands the connection string to the service from Secret Manager. |

## Layer 2, transport and the browser

| Control | What it means | Status | Evidence |
|---|---|---|---|
| C-06 | TLS 1.2 or higher, with plain HTTP redirected | Partly in place | Both public addresses are served over HTTPS by the platforms. A scan of the deployed protocol versions and the redirect is planned in issue [#22](https://github.com/teon-artilionAI/toolshed-hire/issues/22). |
| C-07 | Tell browsers to use HTTPS for six months, subdomains included | In place | `Strict-Transport-Security` in [vercel.json](../../frontend/vercel.json) and in [security_headers.py](../../backend/app/api/security_headers.py), which sends it in staging and production. Tested by [test_security_headers.py](../../backend/tests/api/test_security_headers.py). |
| C-08 | A strict Content Security Policy that allows only this origin | In place | The policy in [vercel.json](../../frontend/vercel.json) starts from `default-src 'none'` and allows scripts, styles and connections from this origin only. The API sends `default-src 'none'`. [vite.config.ts](../../frontend/vite.config.ts) applies the same policy to the browser tests, so every screen is tested under it. |
| C-09 | No inline script, with Trusted Types and a build step to prove it | Partly in place | The policy allows no inline script, so a screen that needed one would fail its browser test. Trusted Types are not switched on, and there is no separate build step for this yet. |
| C-10 | Stop content sniffing and leak no more than the origin as a referrer | In place | `nosniff` and `strict-origin-when-cross-origin` in [vercel.json](../../frontend/vercel.json) and [security_headers.py](../../backend/app/api/security_headers.py). |
| C-11 | Keep other origins out of the window and the resources, and deny location, microphone, camera and payment | In place | The opener, resource and permissions policies in the same two files, checked by [test_security_headers.py](../../backend/tests/api/test_security_headers.py). |
| C-12 | Never let a cache keep a response built for one signed in person | In place | [security_headers.py](../../backend/app/api/security_headers.py) sends `Cache-Control: no-store` whenever a request carried a token or a cookie. Tested by [test_security_headers.py](../../backend/tests/api/test_security_headers.py). |

## Layer 3, sessions

| Control | What it means | Status | Evidence |
|---|---|---|---|
| C-13 | Passwords of twelve characters or more, hashed with bcrypt at work factor 12, never logged or returned | In place | [password_policy.py](../../backend/app/domain/password_policy.py) and [security.py](../../backend/app/infrastructure/security.py). Tested by [test_password_and_profile_rules.py](../../backend/tests/unit/test_password_and_profile_rules.py) and [test_log_redaction.py](../../backend/tests/unit/test_log_redaction.py). |
| C-14 | Lock an account for fifteen minutes after five failures in fifteen minutes, and answer a wrong password and an unknown address the same way in the same time | In place | [sign_in.py](../../backend/app/application/identity/sign_in.py) runs one bcrypt check on every path. Tested by [test_login_lockout_window.py](../../backend/tests/api/test_login_lockout_window.py) and [test_login_throttle_and_timing.py](../../backend/tests/api/test_login_throttle_and_timing.py). |
| C-15 | A fifteen minute access token, held in memory and nowhere else | In place | [security.py](../../backend/app/infrastructure/security.py) issues it, and [session-store.ts](../../frontend/src/shared/session-store.ts) holds it. [web-storage.test.ts](../../frontend/src/shared/web-storage.test.ts) proves no token is ever written to browser storage. |
| C-16 | An opaque refresh token stored only as a hash, living 14 days at most and 7 days idle, replaced on every use, with reuse revoking the whole family and sign out revoking on the server | In place | [session.py](../../backend/app/domain/session.py) and [refresh_session.py](../../backend/app/application/identity/refresh_session.py). The token is 256 bits, more than the design's 128. Tested by [test_sessions.py](../../backend/tests/integration/test_sessions.py) and [test_refresh_and_logout.py](../../backend/tests/api/test_refresh_and_logout.py). |
| C-17 | Throttle sign in, registration, password resets and resends, by address and by client | In place | Nine limits through [throttle.py](../../backend/app/application/throttle.py), listed in [backend/README.md](../../backend/README.md#throttling). Tested by [test_login_throttle_and_timing.py](../../backend/tests/api/test_login_throttle_and_timing.py) and [test_password_reset_throttle.py](../../backend/tests/api/test_password_reset_throttle.py). |
| C-18 | A reset link that works once, is stored as a hash, runs out, ends every session, and is answered the same way for every address | In place | [account_tokens.py](../../backend/app/domain/account_tokens.py) and [password_reset.py](../../backend/app/application/identity/password_reset.py). Tested by [test_password_reset.py](../../backend/tests/api/test_password_reset.py). |
| C-19 | A refresh cookie that scripts cannot read, sent only over HTTPS, only from this site and only to the session routes | In place | [refresh_cookie.py](../../backend/app/api/refresh_cookie.py) sets `HttpOnly`, `Secure`, `SameSite=Strict` and `Path=/api/auth`. Tested by [test_refresh_cookie_and_origin.py](../../backend/tests/api/test_refresh_cookie_and_origin.py). |

## Layer 4, access

| Control | What it means | Status | Evidence |
|---|---|---|---|
| C-20 | Deny by default, with every route declaring who may call it | In place | [access_policy.py](../../backend/app/api/access_policy.py). |
| C-21 | Refuse to start on a route with no policy, and test the route table on every pull request | In place | [access_policy.py](../../backend/app/api/access_policy.py) walks the routes at start-up. [test_route_policies.py](../../backend/tests/api/test_route_policies.py) lists the policy expected of every route. |
| C-22 | Ownership in the query itself, so another customer's record is a 404 and not a 403 | In place | [ownership.py](../../backend/app/application/ownership.py) puts the owner into the repository's WHERE clause. Tested by [test_ownership_and_branch_scope.py](../../backend/tests/api/test_ownership_and_branch_scope.py). |
| C-23 | Counter staff change only their own branch and read all three | In place | `ensure_branch_scope` in [identity.py](../../backend/app/domain/identity.py), and a composite key in the schema that ties an allocation to its unit's branch. Tested by [test_ownership_and_branch_scope.py](../../backend/tests/api/test_ownership_and_branch_scope.py). |
| C-24 | Prices, users, waivers, force release and reports belong to the administrator alone | Planned for the final release | None of these functions exists yet. They arrive with issues [#17](https://github.com/teon-artilionAI/toolshed-hire/issues/17) to [#21](https://github.com/teon-artilionAI/toolshed-hire/issues/21). `FreshAdminUser` in [identity_deps.py](../../backend/app/api/identity_deps.py) is ready for them and reads the account again under a lock. <!-- final: after 017 to 021 --> |
| C-25 | A test of every role against a representative route of every module | In place | The role matrix in [test_route_policies.py](../../backend/tests/api/test_route_policies.py). |

## Layer 5, input

| Control | What it means | Status | Evidence |
|---|---|---|---|
| C-26 | Request bodies are allowlists kept apart from the tables, so a caller cannot set a field they may not | In place | The account routes refuse any field they do not name, through `StrictRequest` in [account_schemas.py](../../backend/app/api/account_schemas.py), and every other body ignores one. Tested by [test_register_refusals.py](../../backend/tests/api/test_register_refusals.py) and [test_profile.py](../../backend/tests/api/test_profile.py). |
| C-27 | Every statement takes its values as parameters, and a lint rule catches SQL built from strings | In place | Ruff rule `S608` in [pyproject.toml](../../backend/pyproject.toml), on every push. |
| C-28 | Sort orders, filters and every identifier in a statement come from a fixed list on the server | In place | `ModelSort` in [read_models.py](../../backend/app/application/catalogue/read_models.py), which the query object maps to columns. |
| C-29 | Accept only JPEG and PNG by their content, cap the size, refuse SVG | Planned for the final release | There is no photograph upload yet. <!-- final: confirm the plan for photographs --> |
| C-30 | Re-encode every image under a random name, which drops its metadata | Planned for the final release | As C-29. |
| C-31 | Keep images in a private bucket and hand them out through short lived signed links as downloads | Planned for the final release | As C-29. |
| C-32 | Escape a cell that starts with a formula character in an export | Planned for the final release | The export arrives with reporting, issue [#17](https://github.com/teon-artilionAI/toolshed-hire/issues/17). <!-- final: after 017 --> |

## Layer 6, data and the supply chain

| Control | What it means | Status | Evidence |
|---|---|---|---|
| C-33 | Secrets live in Secret Manager, and the service refuses to start without them | Partly in place | The database string, the signing key and the email key are in Secret Manager, step 6 of [SETUP.md](../../infra/SETUP.md), and [deploy-api.sh](../../infra/scripts/deploy-api.sh) mounts them. Outside development and test the service refuses to start on the placeholder signing key, a short key or a local database, which [test_configuration.py](../../backend/tests/unit/test_configuration.py) checks. A missing email key turns email off with a warning instead of stopping the service, so a provider problem cannot take bookings down. |
| C-34 | A secret scan on every push that blocks the merge, and the whole history scanned before handover | Partly in place | gitleaks runs on every push in [ci-fast.yml](../../.github/workflows/ci-fast.yml) with [.gitleaks.toml](../../.gitleaks.toml), and its outcome is a required check. The scan of the whole history before handover is still to be run and recorded. <!-- final: record the full history scan --> |
| C-35 | Deploy with Workload Identity Federation, so no long lived key exists | In place | [WORKLOAD-IDENTITY-FEDERATION.md](../../infra/WORKLOAD-IDENTITY-FEDERATION.md), and the authentication step of both deployment workflows. |
| C-36 | Name the signing key in the token header, so the key can change without ending every session | In place | The `kid` header in [security.py](../../backend/app/infrastructure/security.py), tested by [test_access_token.py](../../backend/tests/unit/test_access_token.py). A new key refuses the old access tokens, and a browser refreshes once and carries on. |
| C-37 | Pin every dependency exactly, the base image by digest and every action by commit | Partly in place | The backend's direct dependencies are pinned exactly in [pyproject.toml](../../backend/pyproject.toml), but there is no Python lockfile, so their own dependencies are resolved at install time. The frontend installs exactly what [package-lock.json](../../frontend/package-lock.json) holds. The [Dockerfile](../../backend/Dockerfile) pins its base by digest, and every action is pinned by commit. |
| C-38 | Scan for known vulnerabilities on every pull request and every week, block high and critical findings, and publish a bill of materials with each release | Partly in place | `pip-audit` and the npm audit run on every pull request in [ci-integration.yml](../../.github/workflows/ci-integration.yml) and block a high or critical finding, apart from one reviewed exception in [audit-exceptions.json](../../frontend/audit-exceptions.json). Dependabot raises updates every week, from [dependabot.yml](../../.github/dependabot.yml). A weekly advisory scan and a bill of materials are not in place. |
| C-39 | Give workflows the least permission, keep secrets from forks, and protect production | In place | Every workflow may only read the repository, and the two deployment workflows add the identity token that federation needs. All secrets are environment secrets, which a fork never receives. The `production` environment needs my approval and accepts only `v*` tags, and `staging` accepts only `develop`. |

## Layer 7, evidence

| Control | What it means | Status | Evidence |
|---|---|---|---|
| C-40 | An audit event in the same transaction as every change, with the actor, their role at the time, the entity, the action, the fields before and after, the request id and the address | In place | [audit.py](../../backend/app/infrastructure/audit.py). [test_checkout_transaction.py](../../backend/tests/integration/test_checkout_transaction.py) and [test_return_transaction.py](../../backend/tests/integration/test_return_transaction.py) show a failed audit write fails the change. |
| C-41 | The application's database role can only add and read audit events, tested by trying an update | In place | [role_grants.py](../../backend/alembic/role_grants.py) behind migration `0002`. [test_application_role.py](../../backend/tests/integration/test_application_role.py) has an update, a delete and a truncate refused. |
| C-42 | Structured JSON logs with secrets redacted, and a test that scrubs them | In place | [log_redaction.py](../../backend/app/log_redaction.py) and [logging_config.py](../../backend/app/logging_config.py). Tested by [test_log_redaction.py](../../backend/tests/unit/test_log_redaction.py) and [test_access_log.py](../../backend/tests/api/test_access_log.py). |
| C-43 | Alerts on refresh token reuse, a rise in lockouts, a rise in refusals and unusual constraint violations | Planned for the final release | The events are logged, for example `auth.refresh_reuse_detected` and `auth.login_failed`, but no alert is set on them yet. |
| C-44 | A written incident procedure with the responsible party, the order of containment and the notice the privacy law requires, rehearsed before handover | Planned for the final release | Not written yet. The rollback steps it would use are in [OPERATIONS.md](../../infra/OPERATIONS.md#rollback). |
