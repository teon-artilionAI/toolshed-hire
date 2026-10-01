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
npm run typecheck
npm run build
```

## Tests

I test the frontend at two levels. Both run with no backend, because the
numbered screens draw from fixtures.

```bash
npm run test          # unit and component tests, one pass
npm run test:watch    # the same tests, rerun as files change
npm run test:e2e      # browser and accessibility tests
```

### Unit and component tests

Vitest runs every `src/**/*.test.ts` and `src/**/*.test.tsx` file in a jsdom
environment. I keep each test file beside the module it covers. Component
tests use Testing Library and find elements by role, label and visible text,
the way a person or a screen reader would. `src/test/setup.ts` registers the
jest-dom matchers and unmounts each rendered component after its test.

I pin the time zone to `Africa/Johannesburg` in `vitest.config.ts`, so dates
format the same way on any machine.

### Browser and accessibility tests

Playwright runs the files in `e2e/` against the production build. It builds
the bundle, serves it with `vite preview` on `http://127.0.0.1:4173`, and runs
every test twice. One pass uses desktop Chromium and the other uses a phone
viewport 390 pixels wide. Port 4173 must be free when the run starts.

The browser is a separate download. Install it once before the first run.

```bash
npx playwright install chromium
```

`e2e/accessibility.spec.ts` scans the public screens with axe against the WCAG
2.2 level AA rules and fails on any serious or critical violation. An automated
scan cannot judge everything, so it supports manual keyboard and screen reader
checks and does not replace them.

After a run, the HTML report is in `playwright-report/`. It does not open by
itself. To read it, run `npx playwright show-report`.
