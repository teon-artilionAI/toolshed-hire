# Toolshed Hire frontend

I built the browser application with React, TypeScript and Vite. It contains
the twenty-four numbered customer, counter-staff and administration screens,
plus one development-only system page.

## Numbered screens

The screens are moving from sample data to the API one group at a time.

| Screens | Where the data comes from |
|---|---|
| `SC-01` Catalogue Home, `SC-02` Availability Search Results, `SC-03` Product Model Detail | The API, through the data layer described below |
| `SC-06` Sign In | The API, through the session described below |
| `SC-04`, `SC-05` and `SC-07` to `SC-24` | The typed sample data in `src/shared/fixtures.ts` |

Every screen has a `live` flag in `src/shared/navigation.ts`. It is true for
the screens that read from the API and false for the rest. While it is false
the shell puts a notice above the screen that says it still shows sample data
and that nothing changed there is saved. The notice is
`src/shared/sample-data-notice.tsx`, and the flag is the only thing that
decides whether it shows. Connecting a screen means changing its flag to true.

Two things are not available yet and say so. `SC-05` Register shows its form
and states that an account cannot be created online yet, before anyone types
and again when the form passes every check. The password reset state of
`SC-06` states that reset is not available and takes no email address.
Neither reports a success that did not happen.

## Session

A person signs in with their own email address and password on `SC-06`. The
session routes are `POST /api/auth/login`, `POST /api/auth/refresh` and
`POST /api/auth/logout`, and `GET /api/me` returns the signed in account.

### Where the tokens live

- The access token is held in memory only, in a variable inside
  `src/shared/session-store.ts`. It is never written to `localStorage`,
  `sessionStorage`, a cookie or a log, and no screen can read it.
- Web storage holds two markers at most and nothing else. Both are the fixed
  word `yes` in `localStorage`, and neither names an account or holds a token.
  `toolshed.session-hint` says this browser may hold a session.
  `toolshed.sign-out-owed` says a sign out never reached the server.
  `src/shared/session-markers.ts` is the only file that touches web storage. A
  test in `session-store.lifecycle.test.ts` proves that only those two keys are
  ever written, and only with that word.
- The refresh token is an HttpOnly cookie the server sets. JavaScript cannot
  read it and does not try. The browser sends it back by itself, because every
  request includes credentials and stays on the same origin as the page.

### What happens when

| Moment | What the application does |
|---|---|
| Start-up, no session hint | Nobody has signed in from this browser, so the person is signed out at once and the API is not asked. A visitor who never signs in costs no request and sees no 401 in the console |
| Start-up, with the session hint | Calls refresh once. Until the answer arrives it shows a neutral loading state and no screen. A good cookie means the person is still signed in after a reload. When the API says the session is over, the hint is removed. When the API could not be reached, the hint stays, so the next load asks again |
| Sign in | Sends what was typed. A refusal shows one generic message whatever the reason. A 429 shows the wait from `Retry-After`. A failure to reach the API shows the shared error state. The button is disabled while the request is in flight |
| A request answered 401 | When the problem type ends `session-expired` or `authentication-failure`, and the person is signed in, the client refreshes once and repeats the request once. Requests refused together share one refresh |
| The refresh fails | The person is signed out, the cache is cleared, and they are sent to sign in with a short message. Signing in takes them back to where they were |
| Sign out | Goes to the catalogue, calls logout, drops the token, removes the session hint and clears the cache |
| The logout call fails | The person is still signed out of the page. The refresh cookie is still set, so the sign out owed marker is left. While it is there, start-up sends logout again and does not call refresh, so a reload cannot sign the person back in |

The pieces are small and each has one job.

- `src/shared/api/auth.ts` has one function for each session route.
- `src/shared/api/session-seam.ts` is where the client and the session meet.
  The session registers a token provider and a refresher there, and the client
  asks it for both. Neither imports the other.
- `src/shared/session-store.ts` holds the session outside React.
- `src/shared/session-markers.ts` keeps the two markers in web storage.
- `src/shared/session.tsx` is the provider. It adds what needs the router and
  the cache, which is the start-up check, signing out and the redirect when a
  session ends.
- `src/shared/use-session.ts` is the `useSession` hook the screens call.

A screen gets `user`, `role`, `signedIn`, `signIn` and `signOut` from
`useSession`. The account is the one the API describes. There is no second
user shape and no way to change role or branch from the browser.

### Guards and the menu

`src/shared/screen-access.ts` reads the screen inventory in
`src/shared/navigation.ts` and decides three things from it.

- Who may open a screen. A screen marked `publicAccess` is open to everyone.
  Any other screen needs a signed in person whose role reaches the area in
  `role`. A customer reaches the customer screens. Counter staff reach the
  counter. An admin reaches the admin area and the counter.
- What the menu offers. The layout and the menu follow the signed in person.
  Counter staff see the name of the branch on their account, which the shell
  looks up from `GET /api/branches`.
- Where a person lands after signing in. They go to the screen they were
  trying to reach, when it is a screen of this application that their role may
  open. Otherwise they go to the home of their role. The address travels in
  `?next=` and is only followed when it names a screen in the inventory.

The guard itself is `ScreenRoute` in `src/App.tsx`. A signed out person who
opens a protected screen is sent to sign in. A signed in person who opens a
screen for another role sees a plain refusal with a link to their own home,
from `src/shared/no-access.tsx`. The screen is not rendered in either case.

The guards decide what the interface offers. The API checks the role on every
request, and that check is what protects the data.

The router moves keyboard focus to the main region whenever the address
changes, so focus is never left on a control that is no longer on the page
after a sign in or a redirect.

### The session types and the origin check

The session types in `src/shared/api/contract.ts` come from the generated
file, like every other wire type. The role and the token type are narrowed
there, because the OpenAPI document types both as a plain `string`.

Refresh and logout are authenticated by the cookie alone, so the API checks
the `Origin` of those two requests against its `CORS_ORIGINS` setting and
answers 403 for any other. The backend default lists `http://localhost:5173`
only. Open the development server by that name and not as `127.0.0.1`, or a
reload will not keep the session. The browser tests run on
`http://127.0.0.1:4173`, so the backend they run against needs that origin in
`CORS_ORIGINS` as well.

## API-connected system page

`/system` is the `DEV-01` development page for checking connectivity. It is
outside the numbered screens and does not appear in a navigation menu. The
page calls `GET /api/health` and displays the origin and path used for the
request. It has no sign in of its own. When somebody is signed in it calls
the protected `GET /api/me` with the token the session holds, and when nobody
is it offers a link to the sign in screen that brings them back.

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
- The bearer token comes from the session through `api/session-seam.ts`. A
  request refused for want of a good token is repeated once after one refresh.
  The Session section above has the rule.

### Failures

Every failure is an `ApiError`. It carries the kind of failure, the status, the
problem document when the API sent one, and the request id. The id comes from
the `requestId` member of the problem document or from the `X-Request-ID`
response header. A response that names a wait in `Retry-After` has it on the
error as `retryAfterSeconds`.

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

A test of the session, the guards, the shell or the sign in screen renders the
whole application with `src/test/render-app.tsx`, because what is under test
is how the router, the session and the cache work together.
`src/test/session-samples.ts` has an account for each role and the answers the
session routes send. The session lives in a module, so `src/test/setup.ts`
puts it back to how it starts after every test.

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

`e2e/session.spec.ts` needs the real backend with the session routes. A seeded
customer signs in, is still signed in after a reload, is refused a counter
screen, signs out, and is then asked to sign in before a protected screen
opens. A healthy backend is not proof that it has the session routes, so this
spec also posts to `/api/auth/refresh`. A 404 or a 405 there means the route
is not there, and the spec skips itself. The customer is
`w.adonis@buildright.co.za`. The password comes from `E2E_CUSTOMER_PASSWORD`
and falls back to the development seed password.

One run signs that customer in four times, twice in each browser project. The
API allows ten sign in attempts for one email address in a fixed window of
fifteen minutes and counts the ones that succeed. A third run inside the same
window is therefore answered 429 and fails. Wait for the next quarter hour, or
start the backend on a fresh database.

Set `E2E_REQUIRE_BACKEND=1` to turn both skips into failures. The pipeline sets
it, because there the backend is started for these tests and a skipped spec
would hide that it did not come up.

The scans use axe against the WCAG 2.2 level AA rules and fail on any serious
or critical violation. An automated scan cannot judge everything, so it
supports manual keyboard and screen reader checks and does not replace them.

After a run, the HTML report is in `playwright-report/`. It does not open by
itself. To read it, run `npx playwright show-report`.
