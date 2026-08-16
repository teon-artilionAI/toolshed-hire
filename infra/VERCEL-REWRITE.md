# The single origin rewrite

`frontend/vercel.json` rewrites `/api/:path*` to the Cloud Run service. This
file is the comment that configuration cannot carry, because `vercel.json` is
JSON, JSON permits no comments, and Vercel rejects unknown top-level keys, so
even a `//` key would fail the deployment outright.

```json
{
  "source": "/api/:path*",
  "destination": "$CLOUD_RUN_API_ORIGIN/api/:path*",
  "env": ["CLOUD_RUN_API_ORIGIN"]
}
```

## Why it exists

The browser only ever addresses the Vercel origin, and Vercel proxies to Cloud
Run server side. Three consequences follow, and together they are why this was
preferred to letting the browser call Cloud Run directly.

**The refresh cookie is first party by construction.** It is same-origin, so
`SameSite=Strict` is available. Calling Cloud Run directly would have made the
cookie cross-site, and the strictest setting would not have been an option at
all. This is the operational payoff of the decision and the reason the
arrangement is described as a backend-for-frontend rather than a convenience.

**No request is ever cross-origin.** There is no preflight to misconfigure and
no second origin whose compromise would expose the first. The CORS middleware
on the API is retained as defence in depth for the case where the Cloud Run URL
is reached directly, and in production it is doing nothing.

**The browser never learns the Cloud Run URL.** The API is not independently
addressable from a page the user is on.

## Why the destination is an environment variable

The destination is read from `CLOUD_RUN_API_ORIGIN` rather than hardcoded, so
one committed file serves preview and production, and no service URL is baked
into the repository. Vercel substitutes the value at request time from the
project's environment variables, which is what the `env` array declares. It is
a plain variable and not a secret: the value is a public URL, and it is not
prefixed `VITE_` because it is consumed by the routing layer rather than
compiled into the bundle.

Set it once per environment:

```bash
cd frontend
vercel env add CLOUD_RUN_API_ORIGIN production
vercel env add CLOUD_RUN_API_ORIGIN preview
```

Changing it requires a redeploy. The values are resolved per deployment and do
not change under a deployment that has already been built.

## The SPA fallback below it

The second rewrite sends everything that is not `/api/` and not a real file to
`/index.html`, which is what makes client side routing work on a hard refresh
of a deep link. It is written as a negative lookahead rather than a bare
catch-all so that an API path can never fall through to the HTML shell. A
request to a mistyped API route should fail as an API request, not return a
page with HTTP 200, which is the failure that makes a broken client look like a
parsing bug.

Static assets are unaffected because Vercel checks the filesystem before
applying a rewrite.

## Verifying it, and reading the failures

```bash
curl -i https://YOUR-VERCEL-DOMAIN/api/health
```

| What you get | What it means |
|---|---|
| 200 with the same JSON as the Cloud Run URL | Working |
| 200 with HTML | The API request fell through to the SPA fallback. The `/api/:path*` rule is missing, misspelled or ordered after the catch-all |
| 404 | `CLOUD_RUN_API_ORIGIN` is not set for that environment, or the deployment predates it being set |
| A body or error containing the literal `$CLOUD_RUN_API_ORIGIN` | The variable was not interpolated. Confirm the name appears in the `env` array exactly as it appears in the destination |
| 502 or 504 | The rewrite reached Cloud Run and Cloud Run did not answer. Check the service directly before touching this file |
| 503 with `"status": "degraded"` | The rewrite is fine. The API is up and its database is unreachable or is missing `btree_gist` |

If runtime interpolation turns out to be unavailable on the plan in use, the
fallback is to put the Cloud Run URL into `destination` directly and drop the
`env` array. That costs the environment independence described above and
nothing else, and it must then be updated by hand whenever the service URL
changes.

## What this does not do

The rewrite is a proxy, not a cache and not an authorisation boundary. Every
request still reaches the API, and the API is still responsible for
authenticating it. Nothing here should ever be relied on to hide an endpoint,
because the Cloud Run URL is reachable by anyone who learns it, which is why the
service keeps its own CORS configuration and its own role checks.
