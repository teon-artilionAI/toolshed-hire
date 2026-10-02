# Toolshed Hire frontend

I built the browser application with React, TypeScript and Vite. It contains
the twenty-four numbered customer, counter-staff and administration screens,
plus a privacy notice and one development-only system page.

## Numbered screens

The screens are moving from sample data to the API one group at a time.

| Screens | Where the data comes from |
|---|---|
| `SC-01` Catalogue Home, `SC-02` Availability Search Results, `SC-03` Product Model Detail | The API, through the data layer described below |
| `SC-04` Hire Basket and Booking Review, `SC-07` My Reservations, `SC-08` Reservation Detail and Cancellation | The API, through the reservation routes described under Booking a hire |
| `SC-06` Sign In and Password Reset | The API, through the session described below and the reset routes described under Registration and account security |
| `SC-05` Register, `SC-09` My Account and Hire History | The API, through the routes described under Registration and account security |
| `SC-10` to `SC-24` | The typed sample data in `src/shared/fixtures.ts` |

Every screen has a `live` flag in `src/shared/navigation.ts`. It is true for
the screens that read from the API and false for the rest. While it is false
the shell puts a notice above the screen that says it still shows sample data
and that nothing changed there is saved. The notice is
`src/shared/sample-data-notice.tsx`, and the flag is the only thing that
decides whether it shows. Connecting a screen means changing its flag to true.

One part of a connected screen has no data yet and says so. The hire history
and charges on `SC-09` wait for a later change, so that card shows no figure
and no sample. It says that hires and charges appear once equipment has been
collected.

The privacy notice at `/privacy` is `INFO-01`. It is a supporting page and not
one of the numbered screens. It is routed and guarded from the same inventory,
through the `supporting` flag, and it is never counted among the twenty-four
and never shown in a menu. The shell links to it from the footer of every
screen.

## Session

A person signs in with their own email address and password on `SC-06`. The
session routes are `POST /api/auth/login`, `POST /api/auth/refresh` and
`POST /api/auth/logout`, and `GET /api/me` returns the signed in account.

### Where the tokens live

- The access token is held in memory only, in a variable inside
  `src/shared/session-store.ts`. It is never written to `localStorage`,
  `sessionStorage`, a cookie or a log, and no screen can read it.
- For the session, web storage holds two markers at most. Both are the fixed
  word `yes` in `localStorage`, and neither names an account or holds a token.
  `toolshed.session-hint` says this browser may hold a session.
  `toolshed.sign-out-owed` says a sign out never reached the server.
  `src/shared/session-markers.ts` is the only file that touches `localStorage`.
- The one other thing in web storage is the hire basket, under
  `toolshed.basket` in `sessionStorage`. It is described under Hire basket
  below. It holds dates, a branch code, model slugs, quantities and the id of a
  booking that is under way, and no name, address or token.
  `src/shared/basket-storage.ts` is the only file that touches
  `sessionStorage`.
- `src/shared/web-storage.test.ts` runs every path that handles a token with a
  basket and a booking beside it. It proves that `localStorage` is only ever
  written under the two marker keys with the fixed word, that `sessionStorage`
  is only ever written under the basket key, and that no write holds a token.
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
| Sign out | Goes to the catalogue, calls logout, drops the token, removes the session hint, clears the cache and empties the hire basket |
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

`useSession` also has `endSessionHere`, which ends the session without leaving
the screen. One screen uses it. A password reset ends every session of the
account on the server, so a person who was signed in while they reset it is
signed out of that page as well.

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
`isRefusal` in the same file says whether a failure was a 422, which a form
puts right by changing a field and not by trying again.

### Wire types

The wire types come from the backend's OpenAPI document, which the backend
commits as `../backend/openapi.json`.

- `api/schema.d.ts` is generated from that document by `openapi-typescript`. I
  commit it and never edit it by hand. It is the one file the 300 line guide
  does not apply to.
- `api/contract-kit.ts` is the only module that imports the generated file. It
  passes the generated shapes on to the contract modules, with the type tools
  that read one operation out of them.
- `api/contract.ts` is the only module the rest of the application imports a
  wire type from. It gives each type the name the screens use. Where the
  generated type says less than the screens rely on, such as money typed as a
  plain `string` or a role typed as any `string`, it keeps a more precise type
  and says why.
- The six reservation routes are in the document, and their types are built
  from the generated file like every other. They sit in
  `api/contract-booking.ts` to keep each file short, and `contract.ts` passes
  them on.
- The registration and account routes are agreed and are not in the document
  yet. Their types are in `api/contract-account.ts`, and they are the only
  wire types written by hand. Every name in them is the one the agreed
  contract uses. Once the routes are in the document, run `npm run api:types`
  and rebuild those types from the generated file, the way
  `contract-booking.ts` does.

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
- A quote is never fresh either, for the same reason. An old price must never
  be read as the price.
- A reservation is never fresh. A hold lapses by itself and the counter can
  move a booking on, so a status read a while ago may no longer be the status.
- The customer's own profile is never fresh either. A branch can put the
  account on hold, and a link opened in another tab can confirm the email
  address.

`api/catalogue.ts` has one function per catalogue route, and
`api/catalogue-queries.ts` wraps each one as a query for `useQuery`. A screen
uses the query and does not call the route function directly.

`api/reservations.ts` has one function per reservation route, and
`api/reservation-queries.ts` wraps the two reads as queries. The four writes
are called directly, one request for each press of a button. After a write the
screen hands the answer to `rememberReservation`, which keeps it in the cache
under its id and its reference and marks every list as out of date.

### Prices

A price is worked out in one place, on the server. The browser never adds,
multiplies or rounds money.

`SC-03` shows what a hire will cost on its booking card. The figures are the
answer of `GET /api/catalogue/models/{slug}/quote` for the dates and the
quantity chosen, and the card asks again whenever one of them changes. It says
how the price is made up in plain words, for example "1 week and 3 days" or
"3 days at the daily rate", then the subtotal, the VAT and the total. The
deposit is shown apart from the total, because it is held when the equipment
is collected and returned afterwards. The panel is
`src/features/customer/SC03-Quote-Panel.tsx`.

While a new quote is on its way the old one is taken down, so a price never
sits beside a quantity it was not worked out for. When the API refuses the
dates or the quantity, each message goes under the field it is about and no
price is shown.

`SC-04` and `SC-08` show what a reservation costs. Those figures are the ones
the reservation routes send. Each line with its rates and what it comes to,
the subtotal, the VAT, the total, and the deposit apart from them. They are
written out by `src/features/customer/reservation-figures.tsx`. The basket
itself shows no price, because nothing has been priced until the server makes
the reservation.

### Hire basket

A reservation is one period at one collection branch with one or more models,
so that is what the basket holds. A period, a branch, and a line for each
model with how many are wanted. A visitor may fill it without an account.

- `src/shared/basket-store.ts` holds the basket in memory, outside React, and
  has every rule about it. `src/shared/use-basket.ts` is the hook a component
  reads it through. The count beside the basket in the header is the number of
  units in it, read from the same place.
- `src/shared/basket-storage.ts` copies the basket to `sessionStorage` on every
  change, so it survives a reload and is gone when the tab closes. What is
  read back is checked by `src/shared/basket-stored-shape.ts` before it is
  believed, because storage can be edited by hand. An empty basket leaves
  nothing in storage.
- `SC-03` adds a model with its "Add to my hire basket" button and says what
  went in. The button works only once the quote and the availability have both
  answered for the dates, the branch and the quantity on the card, and the
  branch is free. A price that failed to load holds the basket back.
- A basket never mixes periods or branches. Adding a model for other dates or
  another branch adds nothing and asks the person which to keep. They can put
  the card on the basket's dates and branch and check the model again, move
  the whole basket to the new dates and branch, or leave it.
- Signing out empties the basket. A session that ends by itself leaves it, so
  the same person can sign in again and carry on.

### Booking a hire

`SC-04` shows the basket and then a booking in three steps on the one screen.
Each step is one request, and the screen shows what the server answered.

| Step | Request | What the screen shows |
|---|---|---|
| Review | `POST /api/reservations` | The draft the server priced. Every line, the subtotal, the VAT and the total, and the deposit apart from them with the sentence that it is held at collection and returned |
| Hold | `POST /api/reservations/{id}/hold` | That the equipment is held and until when, with a countdown |
| Confirm | `POST /api/reservations/{id}/confirm` | The reference, and that a confirmation email is on its way, only when the answer says the reservation is confirmed |

The rules of a reservation are the server's. Every answer carries `canHold`,
`canConfirm` and `canCancel`, and a button is offered from its flag and from
nothing else. The steps are in `src/features/customer/use-booking.ts`.

- Only one request runs at a time. Every button is disabled while one is in
  flight, and a write is never repeated by itself.
- A visitor who wants to review is sent to sign in and brought back to the
  basket. Staff are told to book at the counter.
- A 409 on a hold shows the server's own sentence, which names the model and
  the dates, and offers the basket to change.
- A 403 whose type ends `account-on-hold` shows the server's sentence and takes
  the booking buttons away for as long as the screen is open.
- A 403 whose type ends `email-not-verified` on a confirmation is said plainly,
  and the hold is kept. The same is said when a held reservation cannot be
  confirmed and the account's email address is unverified.
- A 422 puts each message under the date, the branch or the line it is about.
- A hold ends when the countdown reaches zero, when a confirmation is answered
  with a 409, or when a reload finds the reservation expired. The screen says
  the hold has run out and offers to hold again. A lapsed hold cannot be held
  again, so that makes a new reservation from the same basket and holds it.
- Going back to change the basket from a hold cancels the held reservation
  first, when the server says it can be cancelled, so the equipment is free for
  the next attempt.
- The basket remembers the id of the reservation made from it. A reload in the
  middle of a booking reads that reservation back and carries on from where it
  stands, and does not make a second one.
- A review makes a draft on the server, and a draft is not left behind for
  every change of mind. Going back to the basket from the review sets the
  draft aside, and so does any change to the basket while a reservation is
  under way, because the reservation was priced for the basket as it was. The
  next review settles it first, in
  `src/features/customer/booking-set-aside.ts`. A basket that did not change
  carries on with the draft it has. A basket that did change has the old
  reservation cancelled through the cancellation route, and only then is a new
  one made. If the old one was holding equipment, that also frees its units.
  A conflict or a 404 on that cancellation means there was nothing left to
  cancel. Any other failure is shown, and nothing new is made until it works.
- A draft the customer walks away from stays on the server. So does one whose
  basket was emptied or signed out of, because an empty basket remembers
  nothing.

Accessibility is part of each step. When the view changes, focus moves to the
heading of the new view, and a polite status says what the last request did.
The countdown is a `timer` with `aria-live="off"`, so a screen reader can read
it on request and never reads it by itself. What is spoken is a separate
polite status that changes five times in the half hour, at ten, five, two and
one minute and when the hold runs out. Nothing takes focus while the time runs.

### My reservations

`SC-07` lists the signed in customer's own reservations from
`GET /api/reservations`, newest first, with the reference, the dates, the
branch, the status and the total of each. The status filter and the page live
in the address, so a reload brings the same list back, and the server does the
filtering and the paging. It has the shared loading, failed and empty states.

A draft is a basket that was priced and never held, and a customer reads its
status as "Not finished". The list leaves drafts out until the filter asks for
them. The API filters by one status or by none, so with no status chosen the
screen asks for every status and leaves the draft rows of the page out itself.
It also asks for a page of one draft and reads its total, so it can count the
bookings without them and say how many it left out, with a button that shows
them. What this costs is exact paging. The pages are still the server's, so a
page can show fewer than twenty rows, and one that holds only drafts says so
and keeps the page controls. A reservation that was cancelled while it was
still a draft has the status "Cancelled" like any other, and the list shows it.

`SC-08` reads one reservation by the reference in its address. Cancelling is
offered only when `canCancel` is true. It asks first, takes an optional reason
of up to 200 characters, and then shows the reservation the server answered
with. A refusal shows the server's sentence, and the reservation is read again
so the screen stops offering what is no longer possible. A reference that is
not the caller's is a 404 from the API, and the screen shows one plain not
found state for that and for a reference that does not exist. The charges card
shows no figure. It says that charges appear once the equipment has been
collected, because hires and charges are a later change.

On a phone the list is not a table of six columns. Below 640 pixels each
booking is drawn as a block of its own, with every value on its own line and
the name of its column beside it, so nothing has to be scrolled sideways. It
is still one table in the document. `reservation-table.tsx` and
`reservation-row.tsx` change how it is drawn, and each part states its role so
a screen reader hears a table at every width.

### Registration and account security

`SC-05`, the reset states of `SC-06`, and `SC-09` read and write through
`api/account.ts`, which has one function for each route.

| Screen | Request | What the screen shows |
|---|---|---|
| `SC-05` | `POST /api/auth/register` | "Check your email", with one sentence that is the same whoever the address belongs to |
| `SC-05`, from a link | `POST /api/auth/email-verification` | That the address is confirmed, or that the link no longer works |
| `SC-06` | `POST /api/auth/password-reset/request` | One message, the same whoever the address belongs to |
| `SC-06`, from a link | `POST /api/auth/password-reset/complete` | That the password has changed and every device has been signed out, or that the link no longer works |
| `SC-09` | `GET /api/me/profile` | The customer's own profile |
| `SC-09` | `PATCH /api/me/profile` | The profile the server answered with |
| `SC-09` | `POST /api/auth/email-verification/resend` | That the link was sent again |

- The browser does not know which addresses have accounts. Registration and
  the reset request are answered the same way for every address, and the
  screens say the same thing for every address.
- The registration form asks for the last four characters of the identity
  document and never the whole number. It says that the counter checks the
  full document at collection. It sends exactly the members the route asks
  for. The rules and the body are in `register-form.ts`.
- The branches in the registration form are the ones `GET /api/branches`
  lists. The first one stands in until the person chooses another.
- The password rule is twelve characters or more, in the browser and on the
  server. The number is `MIN_PASSWORD_LENGTH` in `api/account.ts`.
- When the API answers `emailDeliverable: false`, the screen says that this
  demonstration only delivers email to one address, so the link cannot reach
  the person, and what they can still do. That note is
  `email-delivery-note.tsx`, and registration, the reset request and the
  resend all use it.
- A 422 puts each message under the field it names, through
  `api/problem-fields.ts`, and lists any message about a field the form has no
  input for. A 429 says how long to wait, from `Retry-After`. Anything else is
  the shared error state. `account-failure.ts` sorts the failure and
  `account-failure-notice.tsx` draws it.
- `SC-09` sends only the fields the customer changed, and checks only those.
  The name, the contact and billing details and the company details can be
  changed. The email address, the identity document, the account standing,
  the discount and the customer type are shown read only, with a sentence
  saying who changes them.
- A 404 from the profile route means the account has no customer profile,
  which is what a member of staff gets. The screen says so plainly.

#### The token in a link

A verification link ends `#verify=<token>` and a reset link ends
`#reset=<token>`. The token is in the fragment, which a browser never sends to
a server, so it reaches no server log and no `Referer` header.

`use-link-token.ts` takes the token out of the address as soon as the screen
is on the page. It replaces the history entry, so the back button does not
bring the token back. From then on the token is in the state of the one screen
that uses it. It is never logged and never put in web storage, and it is
dropped once the API has answered for it. The client logs the method and the
path of a request and never its body.

A reset link is followed even when somebody is signed in. A verification link
is posted once, and that holds in development too, where React runs each
effect twice.

#### Accessibility of these screens

Each change of state is announced. When a form is replaced by its answer,
focus moves to the heading of the new state, through `state-heading.tsx`. On
`SC-06` focus moves to the top of the screen when one state replaces another.
A request in flight is said in a polite status. Every error is tied to its
field with `aria-describedby`, and every link and button is a 44 pixel target.

`SC-09` used to push the whole page wider than a narrow phone. Its grid now
lets each cell shrink, and long names and addresses wrap.

### Model pictures

A model may have no photograph, and every seeded one has none. In place of an
empty block, `src/features/customer/model-picture.tsx` draws the icon of the
model's category on the brand wash, the same icon the category tiles use. The
name of the model stays real text beside it, so it is read once whether there
is a photograph or not. The icons are keyed by category code in
`src/features/customer/category-icons.ts`.

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
  date in. It also writes an instant the API sent as a time of day at the
  branches, which is how the end of a hold is shown.
- `money` in `src/shared/format.ts` accepts the strings the API sends, such as
  `"280.00"`, and never passes them through a float. `percent` writes a rate
  the API sends, such as `"15.00"`, as `15%`. `isNoMoney` says whether an
  amount is zero, so a line that would only say zero can be left out. None of
  them does a sum.
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

`src/test/account-samples.ts` has a customer profile and the answers the
registration and account routes send. `src/test/render-app.tsx` can read the
fragment of the address as well as the path, which is how a test checks that
the token of a link was taken out of it.

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
their failed state, and the registration form with its branch menu in its
failed state. The privacy notice is scanned too.

`e2e/narrow-screens.spec.ts` also runs with or without the backend. It opens
My Hires and My Account at 360 pixels wide and checks that nothing has to be
scrolled sideways. It is the one browser spec that answers the API itself,
because a layout check should not depend on what a database holds.

`e2e/catalogue.spec.ts` needs the real backend with seeded data on port 8000.
It follows a visitor from picking dates on the home screen, through the search
results, to a model's price and its availability per branch. On the model
screen it asks the quote route the question the screen asked, and checks that
the total and the deposit on the screen are the server's, for one unit and
then for two. The helpers for that are in `e2e/quote.ts`. It checks that a
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

`e2e/reservation.spec.ts` has two journeys. In the first a visitor adds a
model to the basket from the catalogue, finds it still there after a reload,
and is sent to sign in when they want to review it. That needs the catalogue
routes and nobody signs in. In the second the seeded customer signs in, adds a
model, reviews the cost, holds the equipment, confirms the hire, finds it
under My Hires, opens it and cancels it. Then the other seeded customer signs
in, opens that reference and is shown the not found state. That needs the
reservation routes, so the spec also asks `GET /api/reservations` with no
token. A 404 or a 405 there means the routes are not there, and the journey
skips itself.

`e2e/reservation-changes.spec.ts` is the basket that changes on the way. The
other seeded customer puts two models in one basket and sees them priced as
one reservation with two lines. Going back and reviewing the same basket makes
no second draft. Asking for ten of a model the branch cannot supply ten of is
refused when the hold is asked for, the screen shows the sentence the API sent,
and the basket is changed and held. A reload in the middle of the hold picks
the same reservation up. The hold is released, a review is left unfinished,
and My Hires leaves that one out until the filter asks for it.

Neither spec names a tool or a branch, and neither needs a clean database.
They narrow the search to the first branch the API lists, which leaves only
the models that are free there for the dates. Each journey books its own dates
in each browser project, so none competes with another for a unit. Each finds
its own reservations by the references the API answered with. Each cancels or
releases what it made, so the units are free for the next run. A journey that
fails half way leaves what it had made, and the next run books whichever model
is still free. What the two specs share is in `e2e/booking.ts`.

`e2e/account.spec.ts` needs the registration and account routes. In its first
journey a visitor registers with an address nobody has used, is told to check
their email, signs in with the new account, opens My Account, is told the
address is not confirmed, and corrects their phone number. In its second a
visitor asks for a password reset and sees the one message the screen has for
that. The spec asks `GET /api/me/profile` with no token first. A 404 or a 405
there means the routes are not there, and both journeys skip themselves. Each
run registers an account of its own in each browser project, with an address
built from the time, and touches no seeded account. It follows no link from an
email, because the address is not one this system delivers to. The component
tests cover where the links land.

The customers, the password rule and the sign in are in `e2e/customer.ts`, and
the dates are counted from today at the branches by `e2e/hire-dates.ts`.

One run makes twelve sign ins. `session.spec.ts` signs the first customer in
four times, twice in each browser project, and the booking journey twice more.
The second customer is signed in four times, twice by each reservation spec.
`account.spec.ts` signs in each of the two accounts it registers once, and
those count against addresses of their own. It also makes two registrations
and two reset requests, which the API throttles for one client address. The
API allows ten sign in attempts for one email address in a fixed window of
fifteen minutes, and thirty for one client address, and counts the ones that
succeed. So a second run inside the same window takes the first customer past
ten, is answered 429 and fails. Wait for the next quarter hour, or raise
`LOGIN_ATTEMPTS_PER_EMAIL` on the backend you test against, which is what the
pipeline does.

Set `E2E_REQUIRE_BACKEND=1` to turn all four skips into failures. The pipeline
sets it, because there the backend is started for these tests and a skipped
spec would hide that it did not come up.

The scans use axe against the WCAG 2.2 level AA rules and fail on any serious
or critical violation. An automated scan cannot judge everything, so it
supports manual keyboard and screen reader checks and does not replace them.

After a run, the HTML report is in `playwright-report/`. It does not open by
itself. To read it, run `npx playwright show-report`.
