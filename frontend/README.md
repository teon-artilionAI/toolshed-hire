# Toolshed Hire frontend

I built the browser application with React, TypeScript and Vite. It contains
the twenty-four numbered customer, counter-staff and administration screens,
plus one development-only system page.

## Numbered screens

The screens are moving from fixtures to the API one group at a time.

| Screens | Where the data comes from |
|---|---|
| `SC-01` Catalogue Home, `SC-02` Availability Search Results, `SC-03` Product Model Detail | The API, through the data layer described below |
| `SC-04` to `SC-24` | The typed fixtures in `src/shared/fixtures.ts` |

A screen on fixtures demonstrates its interface and its interactions without
pretending that an unfinished endpoint is live. A screen on the API imports
nothing from the fixtures.

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

## Data layer

Every screen that reads from the API goes through the same four pieces. They
live in `src/shared/api/`, with the error model beside them in
`src/shared/api-problem.ts`.

### The client

`api/client.ts` is the only file that calls `fetch`. It offers `api.get`,
`api.post`, `api.put` and `api.patch`. There is no delete, because this system
never deletes a record.

- The base path stays relative as `/api`. An absolute API origin would recreate
  the cross-origin session problem this setup avoids, and the Content Security
  Policy would refuse it, because it only allows `connect-src 'self'`.
- Each call hands over a reader that checks the body and returns a typed value.
  The helpers for writing a reader are in `api/read.ts`.
- `buildQueryString` in `api/query-string.ts` writes a typed query object as a
  query string and leaves out anything undefined, null or empty.
- A request is abandoned after eight seconds, and cookies are always sent.
- The bearer token comes from a provider function. Nothing is registered yet,
  so no token is sent. The session will call `registerAccessTokenProvider`
  once, and the client needs no change.

### Failures

Every failure is an `ApiError`. It carries the kind of failure, the status, the
problem document when the API sent one, and the request id. The id comes from
the `requestId` member of the problem document or from the `X-Request-ID`
response header.

`api/problem-fields.ts` turns the `errors` of a 422 into one message per field,
for a form to show under each input. The API names each refused value by where
it came from and then the field, for example `query.to`. The helper strips
that prefix, so a form looks a message up by the bare name of its field.

### Wire types

The wire types come from the backend's OpenAPI document, which the backend
commits as `../backend/openapi.json`.

- `api/schema.d.ts` is generated from that document by `openapi-typescript`. I
  commit it and never edit it by hand. It is the one file the 300 line guide
  does not apply to.
- `api/contract.ts` is the only module that imports the generated file, and the
  only module the rest of the application imports a wire type from. It gives
  each type the name the screens use. Where the generated type says less than
  the screens rely on, such as money typed as a plain `string` or a role typed
  as any `string`, it keeps a more precise type and says why.

```bash
npm run api:types          # write api/schema.d.ts from ../backend/openapi.json
npm run api:types:check    # fail if the committed file is not what the document generates
```

When the backend changes a route, a field or a query parameter, run
`npm run api:types`. Whatever in the application no longer fits then fails
`npm run typecheck`, which is the point. The pipeline runs
`npm run api:types:check`, so a document that changed without the types being
generated again is caught there. The check generates into a temporary folder
and compares, and it changes nothing in the working tree.

`openapi-typescript` declares TypeScript 5 as its peer and this project is on
TypeScript 6. The `overrides` entry in `package.json` tells npm to give the
generator the project's own TypeScript. The schema check is what would show it
if a later release of either one changed the output.

### Server state

I use `@tanstack/react-query` for server state. `main.tsx` makes one
`QueryClient` from `api/query-client.ts`, which is also where the rules are.

- A failed read is tried again at most twice, with a wait that doubles, and
  only when the API was never reached. An answer from the API is never retried,
  so a 4xx is asked once.
- A write is never retried.
- Catalogue data is fresh for 60 seconds.
- Availability is never fresh. A cached answer is always refetched when it is
  used, and a failed refetch is shown as a failure.

`api/catalogue.ts` has one function per catalogue route, and
`api/catalogue-queries.ts` wraps each one as a query for `useQuery`. A screen
uses the query and does not call the route function directly.

### Shared states

A screen on the API has four states, and three of them are shared components.

| State | Component | What it does |
|---|---|---|
| Loading | `LoadingState` in `src/shared/async-states.tsx` | A skeleton in the shape of the content, with `aria-busy` and an announced label |
| Failed | `ErrorState` in `src/shared/async-states.tsx` | Says what failed in plain words, offers a retry and shows the request id. It never shows the raw error, a status code or a stack |
| Empty | `EmptyState` in `src/shared/ui.tsx` | Says what is missing and offers the way forward |
| Loaded | The screen itself | |

`src/shared/error-boundary.tsx` wraps every routed screen, so a screen that
throws while rendering shows the error state and the navigation stays up.

### Small helpers

- `src/shared/today.ts` returns today's date in `Africa/Johannesburg` as
  `YYYY-MM-DD`. A screen on the API uses it for "today". A test passes its own
  date in.
- `money` in `src/shared/format.ts` accepts the strings the API sends, such as
  `"280.00"`, and never passes them through a float. `moneyTimes` multiplies
  one by a whole number in whole cents.
- `src/shared/pagination.tsx` is the page control for a list the server pages.

## Commands

```bash
npm install
npm run dev
npm run lint
npm run typecheck
npm run build
npm run api:types
npm run api:types:check
```

## Tests

I test the frontend at two levels.

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

These tests need no backend. A test for a screen on the API replaces `fetch`
with a table of routes from `src/test/api-mock.ts`, and renders the screen with
`src/test/render-screen.tsx` inside a router and a fresh cache. The real client
and the real cache rules run in every such test.

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

`e2e/smoke.spec.ts` and `e2e/accessibility.spec.ts` run with or without the
backend. With no backend, the catalogue home and the search are scanned in
their failed state.

`e2e/catalogue.spec.ts` needs the real backend with seeded data on port 8000.
It follows a visitor from picking dates on the home screen, through the search
results, to a model's price and its availability per branch. It checks that a
refusal from the API lands under the right field, that the home screen offers
each top level category once, and that choosing a branch lists only what is
free there. It also scans the three loaded screens. It asks `/api/health`
first. When that does not answer OK, every spec in the file skips itself and
the run still passes.

Set `E2E_REQUIRE_BACKEND=1` to turn that skip into a failure. The pipeline sets
it, because there the backend is started for these tests and a skipped spec
would hide that it did not come up.

The scans use axe against the WCAG 2.2 level AA rules and fail on any serious
or critical violation. An automated scan cannot judge everything, so it
supports manual keyboard and screen reader checks and does not replace them.

After a run, the HTML report is in `playwright-report/`. It does not open by
itself. To read it, run `npx playwright show-report`.
