# Toolshed Hire frontend

I built the browser application with React, TypeScript and Vite. It contains
the twenty-four numbered customer, counter-staff and administration screens,
plus one development-only system page.

## Numbered screens

Screens `SC-01` to `SC-24` use the typed fixtures in
`src/shared/fixtures.ts`. They demonstrate the complete interface and its
interactions without pretending that unfinished endpoints are live.

## API-connected system page

`/system` is the `DEV-01` development and demonstration page. It is outside
the numbered screen inventory and does not appear in a navigation menu. The
page calls `GET /api/health`, signs in through `POST /api/auth/sign-in`, calls
the protected `GET /api/me`, and displays the origin and path used for each
request.

The page needs the backend described in `../backend/README.md`. During local
development, Vite proxies `/api` to `http://localhost:8000`. Production uses
the equivalent Vercel rewrite, so the browser communicates with one origin in
both environments. If the backend is unavailable, the system page displays a
clear diagnostic state.

## API client

New API calls go through `src/shared/api.ts`. The base path stays relative as
`/api`; introducing an absolute API origin would recreate the cross-origin
session problem this setup avoids. Failures use the typed `ApiError`, allowing
the interface to distinguish expected conflicts from server failures.

## Commands

```bash
npm install
npm run dev
npm run lint
npm run build
```
