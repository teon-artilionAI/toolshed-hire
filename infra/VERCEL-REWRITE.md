# The single origin rewrite

`frontend/vercel.json` rewrites `/api/:path*` to the Cloud Run service. That
file is JSON and JSON permits no comments, so this file is the comment it
cannot carry.

```json
{
  "source": "/api/:path*",
  "destination": "$CLOUD_RUN_API_ORIGIN/api/:path*",
  "env": ["CLOUD_RUN_API_ORIGIN"]
}
```

That is the committed form. `$CLOUD_RUN_API_ORIGIN` is a placeholder. No real
address is ever committed, and the repository is public.

## Setting up the two projects

This is step 8 of `SETUP.md`. There are two projects on the Hobby plan,
`toolshed-hire` for production and `toolshed-hire-staging` for staging, both
with the framework `vite`. They are separate projects because custom
environments need a paid plan and a preview deployment sits behind a login by
default. In the dashboard I do this for each.

- I connect nothing to Git. The workflows build on the runner and upload the
  result, so Vercel never builds from the repository.
- I switch deployment protection off. The sites are meant to be public, and
  with it on a visitor meets the Vercel login wall.
- I read the project id from the project settings, and the team id from the
  team settings. They become `VERCEL_PROJECT_ID` and `VERCEL_ORG_ID` in step 9.

I also create an access token for the workflows. It is stored as the
`VERCEL_TOKEN` secret of each GitHub environment and nowhere else. No setting
on either project names the API. The rest of this file explains why.

## Why it exists

The browser only ever talks to the Vercel domain, and Vercel forwards `/api`
requests to Cloud Run server side. Three things follow, and together they are
why I preferred this to letting the browser call Cloud Run directly.

**The refresh cookie is first party by construction.** It is same origin, so
`SameSite=Strict` is available. Calling Cloud Run directly would have made the
cookie cross site, and the strictest setting would not have been an option.

**No request is ever cross origin.** The browser never has to ask permission
first, so there is no CORS allow list in the request path to get wrong. The API
still sets `CORS_ORIGINS` to the frontend origin of its own environment, as
defence in depth for a request that reaches Cloud Run directly.

**The browser never learns the Cloud Run address.** The Content Security
Policy in the same file says `connect-src 'self'`, so a page could not call
another origin even if it knew one.

## How the target is filled in

`infra/scripts/deploy-frontend.sh` does it, in the same workflow run that
deployed the API.

1. It pulls the settings of the Vercel project named by `VERCEL_ORG_ID` and
   `VERCEL_PROJECT_ID`, which differ between staging and production.
2. It rewrites the runner's copy of `vercel.json`. The placeholder is replaced
   by the address of the API that this run just deployed, and the `env` array
   is removed because nothing is left to interpolate. If it does not find
   exactly one rewrite using the placeholder, it stops the build.
3. It builds on the runner and uploads the finished output.

```bash
vercel pull --yes --environment=production
vercel build --prod
vercel deploy --prebuilt --prod
```

The script runs these through a pinned version of the CLI, so a new major
version cannot change a deployment, and with the access token from the GitHub
environment.

This arrangement gives me four things.

- Nothing is committed. The edit happens on the runner and is thrown away with
  it.
- The address is not in the bundle a browser downloads. It lives only in the
  routing configuration of that deployment on Vercel.
- The frontend cannot be left pointing at the wrong environment by a stale
  setting. Each run writes the address of the API it deployed itself.
- The address stays out of the public workflow logs. The deploy script masks it
  as soon as it is known and filters it out of what `gcloud` prints.

The earlier design read the target from a `CLOUD_RUN_API_ORIGIN` setting on the
Vercel project, which had to be kept in step by hand. Neither project has that
setting now.

The address written is the stable address of the service, not that of one
revision. In production the candidate revision is smoke tested on its own
address, but the frontend is given the service address. So the frontend follows
whichever revision holds the traffic, and rolling back the API needs no
frontend deployment.

## Only the workflows deploy the frontend

A deployment made any other way ships the placeholder, and its `/api` calls
cannot reach anything. Nothing is connected to Git on the Vercel side, so
Vercel never makes one on its own. I do not deploy this directory from my own
machine or from the Vercel dashboard.

## The fallback rule below it

The second rewrite sends everything that is not under `/api/` and is not a real
file to `/index.html`, which is what makes client side routing work on a hard
refresh of a deep link. It is written as a negative lookahead and not as a bare
catch all, so an API path can never fall through to the HTML shell. A request
to a mistyped API route should fail as an API request. It should not return a
page with status 200, which makes a broken client look like a parsing bug.

Static assets are unaffected, because Vercel checks the filesystem before it
applies a rewrite.

## The headers in the same file

`vercel.json` also carries the security headers for every path. They are
`Strict-Transport-Security`, `X-Content-Type-Options`, `Referrer-Policy`,
`Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy`,
`Permissions-Policy` and the Content Security Policy.

There is one copy of them. `frontend/vite.config.ts` reads the same rule out of
`vercel.json` for the preview server, so the browser tests load every screen
under the policy a visitor gets.

## Checking it, and reading the failures

Both workflows end with a smoke test through the frontend domain. It passes
only if the rewrite reaches the API, which is the path every browser request
takes. I can repeat it by hand.

```bash
curl -i https://toolshed-hire-staging.vercel.app/api/health
```

| What I get | What it means |
|---|---|
| 200 with JSON and `"status": "healthy"` | Working |
| 200 with HTML | The request fell through to the fallback rule. The `/api/:path*` rule is missing, misspelled or ordered after the catch all |
| The build stops, saying it expected exactly one rewrite using `$CLOUD_RUN_API_ORIGIN` | Somebody changed the `/api` rule in `vercel.json`. The placeholder has to appear in exactly one rewrite |
| The step stops with `API_ORIGIN is not set` | The API deploy step produced no address, so the frontend has nothing to route to. The cause is earlier in the run |
| Every `/api` call fails on a deployment the workflow did not make | That deployment shipped the placeholder. I promote one the workflow made |
| A Vercel login page instead of the site | Deployment protection is switched on for that project |
| 502 or 504 | The rewrite reached Cloud Run and Cloud Run did not answer. I check the service before I touch this file |
| 503 with `"status": "degraded"` | The rewrite is fine. The API is up and its database is unreachable or is missing `btree_gist` |

## What this does not do

The rewrite is a proxy. It is not a cache and it is not an authorisation
boundary. Every request still reaches the API, and the API authenticates and
authorises it.

Keeping the Cloud Run address out of the logs keeps it unpublished. It does not
protect anything. The service allows public invocation, so anyone who learns
the address can call it directly, which is why the API keeps its own CORS
configuration and its own role checks.
