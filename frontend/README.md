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
| `SC-12` Customer Lookup and Walk-in Registration, `SC-13` New Booking and Asset Allocation, `SC-14` Checkout and Deposit | The API, through the routes described under Booking at the counter |
| `SC-10` Counter Dashboard, `SC-11` Branch Diary, `SC-17` Asset Locator | The API, through the routes described under The counter's day |
| `SC-15` Return and Condition Inspection, `SC-18` Overdue and Late Fee Worklist, and the hire history of `SC-09` | The API, through the routes described under Returns and settlement |
| `SC-16` Damage Report Capture | The API, through the routes described under Damage and quarantine |
| `SC-19` to `SC-24` | The typed sample data in `src/shared/fixtures.ts` |

No customer or counter screen reads `src/shared/fixtures.ts` any more. The
modules that still do are the administration screens and their helpers in
`src/features/admin/`, and `src/shared/format.ts`, whose two overdue helpers
take the fixture date as their default and are used only by those screens.

Every screen has a `live` flag in `src/shared/navigation.ts`. It is true for
the screens that read from the API and false for the rest. While it is false
the shell puts a notice above the screen that says it still shows sample data
and that nothing changed there is saved. The notice is
`src/shared/sample-data-notice.tsx`, and the flag is the only thing that
decides whether it shows. Connecting a screen means changing its flag to true.

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
- The other things in web storage are the hire basket, under
  `toolshed.basket` in `sessionStorage`, and the branch an administrator chose
  to work the counter at, under `toolshed.counter-branch` in `sessionStorage`.
  The basket is described under Hire basket below. It holds dates, a branch
  code, model slugs, quantities and the id of a booking that is under way, and
  no name, address or token. The chosen branch is one branch code and nothing
  else, and counter staff never write it. `src/shared/basket-storage.ts` and
  `src/features/counter/work-branch-storage.ts` are the only files that touch
  `sessionStorage`, one key each.
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
- Which menu item is the current page. An item is current on every address
  that starts with its path, so My Hires stays marked on the detail of one
  hire. The home of a role is the start of every other address of its area,
  so `isHomePath` in `src/shared/navigation.ts` marks a home only on its own
  address. Otherwise Today would be marked on every counter screen.
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
  and says why. It holds the session types itself and passes every other type
  on from the module it is built in.
- The branch and catalogue types, which are the branches, the categories, the
  models, the availability searches and the quote, are in
  `api/contract-catalogue.ts`, built from the generated file the same way, so
  `contract.ts` stays a size that can be read in one sitting.
- The six reservation routes are in the document, and their types are built
  from the generated file like every other. They sit in
  `api/contract-booking.ts` to keep each file short, and `contract.ts` passes
  them on.
- The registration and account routes are in the document too. Their types
  are in `api/contract-account.ts`, built from the generated file the same way.
- The counter routes, which are the customer lookup, the walk in, the checkout
  and the hire, are in the document as well. Their types are in
  `api/contract-counter.ts`, built from the generated file the same way.
- The counter overview routes, which are the dashboard, the diary, the no show
  and the asset locator, are in the document too. Their types are in
  `api/contract-overview.ts`, built from the generated file the same way. The
  generated status of a booking in the diary is any status a reservation has,
  and the diary only lists four, so `contract-overview.ts` narrows it to those
  and the reader checks it. The states of a unit are the backend's own list,
  `INTAKE`, `AVAILABLE`, `ON_HIRE`, `QUARANTINED`, `UNDER_REPAIR`, `LOST` and
  `RETIRED`.
- The document describes both answers of a checkout, the 201 with the new hire
  and the 200 the API sends with the same hire when the booking is already
  out. `Rental` is built from both and from the rental route, and the reader in
  `api/rental-read.ts` reads both answers the same way.
- The returns and settlement routes, which are the return, the loss, the
  balance payment and the two lists of hires, are in the document too. Their
  bodies, queries and pages are in `api/contract-returns.ts`, built from the
  generated file the same way. Every one of those routes answers with the
  `Rental` above, or a page of them.
- The damage and quarantine routes, which are filing a report, the list and
  the read of reports, sending one for repair and resolving it, are in the
  document too. Their types are in `api/contract-damage.ts`, built from the
  generated file the same way. The severities are the backend's own list,
  `MINOR`, `MAJOR` and `WRITE_OFF`, and a severity retires nothing on its own.
  Each unit of a hire also carries `replacementValue` for staff, which is null
  for a customer, as its tag is.

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
- A customer the counter looks up is never fresh, for the same reason. What
  the counter reads to hand a reservation over is kept under the reservation
  segment, so it is never fresh either, and a handover marks everything about
  reservations as out of date.
- The counter's dashboard and diary, under the `counter` segment, and the
  locator, under the `assets` segment, are never fresh. They are left open all
  day, so they are read again whenever the window comes back into focus. A no
  show marks the dashboard and every day of the diary as out of date.
- A hire and the counter's lists of hires, under the `rentals` segment, are
  never fresh, and nor are the customer's own hires, under the `account`
  segment. A return, a loss or a balance payment puts the hire the server
  answered with into the cache under its key and its reference, and marks the
  lists, the counter's day, the reservations and the locator as out of date.
- The damage reports of a unit, under the `damage` segment, are never fresh. A
  damage write puts the report the server answered with into every list that
  holds it, and marks the reports, the locator and the counter's day as out of
  date. Filing a report against a hire drops that hire from the cache
  altogether, so the return screen reads it afresh and never shows the deposit
  still waiting while it does.

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

### Booking at the counter

A counter assistant finds or registers a customer on `SC-12`, books for them
on `SC-13` and hands the equipment over on `SC-14`. The calls are in
`api/customers.ts` and `api/checkout.ts`, the hire is read by
`api/rental-read.ts`, and the cached reads are in `api/counter-queries.ts`.

| Screen | Request | What the screen shows |
|---|---|---|
| `SC-12` | `GET /api/customers?q=&page=&pageSize=` | The customers who match, best match first, ten to a page |
| `SC-12` | `GET /api/customers/{id}` and `GET /api/reservations?customerProfileId=&branchCode=` | The chosen customer and their bookings at this branch, or at every branch without `branchCode` |
| `SC-12` | `POST /api/customers` | The new walk in, chosen |
| `SC-13` | `GET /api/catalogue/availability` with `branch`, and `GET /api/catalogue/models/{slug}/availability` | What is free at the branch for the dates, and whether each line is free for its quantity |
| `SC-13` | `POST /api/reservations`, then `/hold`, then `/confirm` | The server's figures, then the units it set aside, then the reference |
| `SC-14` | `GET /api/reservations/{id}/checkout` | The units to hand over and the deposit to take, or the server's reason why not |
| `SC-14` | `POST /api/reservations/{id}/checkout` | The hire, with its reference, its units, the deposit held and the day it is due back |

#### The branch a member of staff works at

`src/features/counter/work-branch.ts` is the one place every counter screen
reads the branch from. Counter staff work at the branch on their session, as
`branchCode`, and cannot change it. An administrator has none, so
`work-branch-gate.tsx` asks which branch they are working at before the
screen opens, and the choice is kept for the tab by `work-branch-storage.ts`.
A line at the top of the screen says which branch it is and offers to change
it. The dashboard and the diary take their branch from the same place.

#### `SC-12` Customer Lookup and Walk-in Registration

- One search box matches a name, a phone number or an email address. It
  searches from three characters, a moment after the last key, and has the
  loading, failed and empty states and page controls. The search, the page
  and the chosen customer live in the address. The API accepts two
  characters, but it finds a name through a trigram index that cannot narrow
  anything shorter than three, so a shorter search would read every customer.
  The box and the line above the results both say three.
- Each customer says who it is, how the account stands, whether there is a
  login, and offers "New booking". An account on hold or blacklisted says so
  and offers no booking.
- Choosing a customer shows their bookings at this branch, and the server
  does that filtering through `branchCode`, so the page controls count what
  is listed. "At every branch" widens the list, and a confirmed booking
  elsewhere says where it is collected. One that is confirmed, starts today
  or earlier and is collected at this branch has "Check out" beside it.
- The walk in form asks for the last four characters of the identity document
  and never the whole number. It is checked before it is sent, a 422 puts
  each message under its field, and once the server answers the new customer
  is chosen. An administrator's walk in names the branch they chose. The rules
  and the body are in `walkin-form.ts`.

#### `SC-13` New Booking and Asset Allocation

- The customer comes in the address as `?customer=<id>`, so a reload keeps
  them. The booking is collected at the assistant's own branch and may start
  today.
- The tools come from the availability search narrowed to that branch, and
  each line asks the single model route whether its quantity is free there.
  The units are allocated by the server when the booking is held. There is no
  way to pick a unit by hand.
- The booking takes the same three requests as an online one, in
  `use-counter-booking.ts`, one press of a button each, and each button is
  disabled while its request is in flight. Every figure is the server's.
- A 409 on the hold shows the server's `detail` and offers the tools to
  change. Going back cancels the reservation first when the server says it
  can be cancelled, so a hold gives its units back at once and a priced draft
  is not left behind. A 403 for an account on hold shows the server's message
  and offers no way to book. A 409 on the confirmation says the hold ran out.
- The confirmed step shows the reference, the asset tags of the units set
  aside, the totals and the deposit to take at collection, and offers "Check
  out now" when the booking starts today.

#### `SC-14` Checkout and Deposit

- The address is `/counter/checkout/:reservationId`, and the value is the key
  of a reservation or its reference.
- When `canCheckOut` is false the screen shows the server's `refusal` and no
  form. When `rentalId` is set it says the booking is already out and links to
  the hire.
- For each unit the assistant ticks that the tag on the unit matches, and
  records the grade it goes out in, starting at the grade it has now, the
  accessories and the hour meter. The deposit to take is the server's figure.
  The customer signs the agreement, and "Check out the equipment" asks a
  question that says in words what is about to happen. "Yes, hand it over" is
  the one request. The rules and the body are in `checkout-form.ts`.
- The answer shows the hire reference, the units, the deposit held and the day
  it is due back, and links to the return of the hire by its key. A 409 or a
  403 shows the server's message and offers to read the booking again. A 422
  goes back to the form with each message under its control.

#### Accessibility of these screens

Each step change moves focus to the heading of the new step, and a polite
status says what the last request did. Every error is tied to its field with
`aria-describedby`, every target is at least 44 pixels, and all three screens
fit a phone 360 pixels wide with nothing to scroll sideways.

### The counter's day

The dashboard on `SC-10` says what is due today at the branch, the diary on
`SC-11` says what goes out and comes back on any day, and the locator on
`SC-17` finds a unit at any branch. The reads are in
`api/counter-overview.ts` and `api/locator.ts`, the no show is in
`api/reservations.ts`, and the cached reads are in `api/counter-queries.ts`.

| Screen | Request | What the screen shows |
|---|---|---|
| `SC-10` | `GET /api/counter/dashboard?branchCode=` | The five counts, then who collects today, what is due back today and what is overdue |
| `SC-11` | `GET /api/counter/diary?branchCode=&from=&days=` | One day, or a week from Monday, with each booking going out and each hire coming back |
| `SC-11` | `POST /api/reservations/{id}/no-show` | The booking as the server now has it, a no show |
| `SC-17` | `GET /api/assets/locator?q=&page=&pageSize=` | The units whose tag or model matches, twenty to a page, at every branch |

#### `SC-10` Counter Dashboard

- One request for the branch the person works at. It has the loading, failed
  and empty states for the whole screen, and a sentence for each list that is
  empty. The counts are true totals and a list holds at most fifty, so a list
  shorter than its count says how many it shows.
- A collection links to the checkout of its booking. A return and an overdue
  hire link to the return screen of the hire, `/counter/return/:rentalId`, by
  the key of the hire.
- The days overdue and the late fee are shown as the server sends them. The
  browser works out no fee.
- The quarantined figure is a count. The server sends nothing about bookings
  that need a unit swapped, so the screen has no such panel.
- The screen is read again when the window comes back into focus, and on the
  refresh button. The line above the figures says when they were read.

#### `SC-11` Branch Diary

- One day, or seven from the Monday of the week, with previous, next and back
  to today. The day and the view are in the address as `?date=` and
  `?view=week`, so a reload keeps them. Today in day view is the plain
  address, so a tab left open overnight shows the new day after a reload. A
  date in the address that is not a day on the calendar falls back to today.
- Each booking and each hire says its status in words. A confirmed booking
  that starts today or earlier links to its checkout. A collected or returned
  booking links to its hire. The diary does not send the key of that hire, so
  the link goes through the checkout of the booking, which says it is out and
  opens the hire. A hire due back links to its return screen.
- Where `canMarkNoShow` is true the booking offers "Mark as no show". It asks
  for the reason, says that the units go back on the shelf and a strike is
  recorded against the customer, and sends one request. The answer is the
  server's. A 409 shows the server's sentence and reads the diary again, and a
  refused reason shows its message under the box. The question is in
  `SC11-No-Show-Action.tsx` and the request in `use-no-show.ts`.

#### `SC-17` Asset Locator

- One search box for a tag or part of a model name. It searches from two
  characters, a moment after the last key, at every branch, with the loading,
  failed and empty states and page controls. The search and the page are in
  the address.
- Each unit says its tag, its model, its branch, its state in words and its
  condition, and the day it is due back and its hire when it is out. A unit
  that is quarantined or in the workshop links to its damage reports on
  `SC-16`. Nothing on the screen changes anything, and it needs no branch, so
  an administrator can use it straight away.

#### Accessibility of these screens

Every list is a real list, or a table with headers that is drawn as one block
for each unit below the `sm` width. Every status carries words beside its
colour, every target is at least 44 pixels, and all three screens fit a phone
360 pixels wide with nothing to scroll sideways. The no show question takes
focus when it opens, gives it back to its button when it closes, and moves it
to the answer when the server has answered.

### Returns and settlement

The return screen on `SC-15` takes equipment back and shows the deposit
settled, the worklist on `SC-18` lists what is overdue, and the history half
of `SC-09` shows a customer their hires. The routes are in `api/rentals.ts`,
the hire is read by `api/rental-read.ts`, and the cached reads are in
`api/rental-queries.ts`. Every figure is the server's. The browser never works
out a late fee, a settlement or a balance, and never adds money up.

| Screen | Request | What the screen shows |
|---|---|---|
| `SC-15` | `GET /api/rentals/{id}` | Each unit still out with the late fee if it came back today, each unit already back and when, and the settlement once the last one is back |
| `SC-15` | `POST /api/rentals/{id}/returns` | The hire as the server now has it, partially returned or with the deposit settled |
| `SC-15` | `POST /api/rentals/{id}/balance-payment` | The hire, settled |
| `SC-18` | `GET /api/rentals?branchCode=&overdueOnly=true&page=&pageSize=` | The overdue hires at the branch, most overdue first, twenty to a page |
| `SC-18` | `POST /api/rentals/{id}/items/{itemId}/loss` | What the loss charged, from the hire the server answered with |
| `SC-09` | `GET /api/me/rentals?page=&pageSize=` | The customer's own hires, newest first, five to a page |

#### `SC-15` Return and Condition Inspection

- The address is `/counter/return/:rentalId`, and the value is the key of a
  hire or its reference. The dashboard, the diary and the checkout all link to
  it by the key. The diary sends no key for a collected booking, so its link
  goes through the checkout of the booking, which opens the hire.
- Each unit still out can be ticked to come back now. Ticking it opens its
  grade, starting at the grade it went out at, its hour meter when it has one,
  the accessories that came back and a box to flag it for damage. The rules and
  the body are in `SC15-return-model.ts`.
- Each unit still out shows `daysLateToday` and `lateFeeToday` from the server,
  with a sentence that the system worked the fee out, that the counter
  confirms it and cannot change it, and that only the owner can waive a
  charge.
- "Take the ticked units back" asks a question that says in words what will
  happen, including every late fee, and "Yes, take them back" is the one
  request. The answer is the hire as the server now has it. While units are
  still out the screen says the hire is partially returned. Once the last one
  is back it shows the deposit held, what was withheld, what was released and
  the balance due, and under them the charges set against the deposit, each
  with whether it is settled yet. A charge the deposit covered only in part
  stays pending until the balance is paid, so that list can come to more than
  was withheld.
- A unit recorded as lost from `SC-18` comes back from the API closed, with the
  time of the loss and no grade, and with no flag of its own. The screen reads
  a closed unit with no grade as lost, says so, and lists the charges that
  carry its id.
- The hire reads as overdue when the server says so. The read of one hire
  moves it to overdue before it answers, so its status is never behind the
  lists.
- When the deposit is waiting on a balance, a form takes the reference of the
  payment and posts it. When it is waiting on a damage report, each unit that
  needs one links to
  `/counter/damage/<assetTag>?rental=<rentalId>&rentalItem=<id>`. Coming back
  from there, the hire is read afresh and shows the settlement the server made
  when the report was filed.
- A 409 or a 403 shows the server's message and offers to read the hire again.
  A 422 goes back to the form with each message under its control. The writes
  share `use-rental-write.ts`, which sends each one once.

#### `SC-18` Overdue and Late Fee Worklist

- One paged request for the overdue hires at the branch the person works at,
  with the loading, failed and empty states. The page is in the address.
- Each hire shows the customer and their phone number, the day it was due
  back, how many days late it is, and each unit still out with its days late
  and its late fee so far, and links to its return. The days late of the hire
  is the most days late of its units, which is the server's figure for one of
  them and not a sum.
- A unit more than fourteen days late is in the escalation queue, which is
  made from the page on the screen. "Record as lost" asks first and says that
  fourteen days of late fee are charged, the deposit for the unit is
  forfeited, a recovery charge up to the replacement value is raised and the
  unit is marked lost. The answer is shown above the lists with the charges the
  server raised, so it stays when the list is read again. The server works the
  balance out only when it settles the deposit, which waits for the last unit,
  so while another unit is out the answer says that and shows no balance.
- The branch and age filters, the reminder to ring a customer and the list of
  units out with no hire against them are gone, because the server sends
  nothing for them.

#### The hire history on `SC-09`

- The history is read once the profile has loaded, so a member of staff, who
  has no profile, never asks for it. Each hire shows its reference, its
  branch, its dates, its status in words, the models hired with no tag, every
  charge, and the deposit held, kept for charges, returned and still due. A
  deposit given back is written as returned, never with a minus sign.
- It has the shared loading and failed states, an empty state that points at
  My Hires, and page controls. The page is in the address.

#### Accessibility of these screens

A write moves focus to a notice that says what it did. The question before
each write takes focus when it opens. Every status carries words beside its
colour, every target is at least 44 pixels, money is written with the rand
sign and two decimals through `money`, and all three screens fit a phone 360
pixels wide with nothing to scroll sideways.

### Damage and quarantine

The damage screen on `SC-16` records a damage report with an explicit decision
on whether the customer is charged, and lets the owner say how it was
resolved. The routes are in `api/damage-reports.ts`, which also reads a report,
and the cached list of a unit's reports is in `api/damage-queries.ts`. The unit
is found through the locator route.

| Screen | Request | What the screen shows |
|---|---|---|
| `SC-16` | `GET /api/assets/locator?q=<tag>&page=1&pageSize=50` | The unit with that tag, where it is and its state |
| `SC-16` | `GET /api/damage-reports?assetTag=&page=&pageSize=` | The reports already filed against the unit, newest first |
| `SC-16` | `GET /api/rentals/{id}` | The hire the unit came back on, when the address names one, for the replacement value of the unit |
| `SC-16` | `POST /api/damage-reports` | The report, with its reference, and the unit in quarantine |
| `SC-16` | `POST /api/damage-reports/{id}/repair` | The report, for an administrator, in the workshop |
| `SC-16` | `POST /api/damage-reports/{id}/resolution` | The report, for an administrator, resolved or written off |

#### `SC-16` Damage Report Capture

- The address is `/counter/damage/:assetTag`. A link from a return also carries
  the hire and its unit, as `?rental=<rentalId>&rentalItem=<id>`. The screen
  has a loading, a failed and a not found state for the unit, and the reports
  have their own, so the form works while they load.
- The form takes the severity, a description, the repair estimate and the
  decision on whether the customer is charged. The decision has no default.
  Neither answer is chosen when the form opens, the form is not sent without
  one (BR-40), and the group says that fair wear and tear is not charged. When
  the customer is charged on a hire, the form also takes the amount to
  recover, VAT inclusive. The server holds it to the replacement value copied
  onto the booking (BR-39), and when it refuses, its message, which names the
  most it will take, lands under the amount. The screen reads the hire named in
  the address and names the replacement value its unit carries, before any
  report exists. While the hire loads, or when it cannot be read, the box says
  only that the server checks the amount. The rules and the body are in
  `SC16-damage-model.ts`.
- A unit that came back damaged waits for the report of that return, and the
  server refuses a report about it that does not name that unit of the hire
  with a 409. So a report for such a unit is filed from its return, and the
  locator's link shows the server's sentence when it is tried from there. A
  unit already in the workshop stays there when a report is filed, and the
  screen says so instead of saying it is quarantined.
- There is no photograph upload in this release.
- "Record the damage and quarantine the unit" asks a question that says in
  words what is about to happen, that the unit is quarantined and cannot be
  booked until the report is resolved, and what the customer is charged. "Yes,
  file the report" is the one request. The answer gives the reference of the
  report and, when it belongs to a hire, a link back to its return.
- A 422 goes back to the form with each message under its field. A 409 or a
  403 shows the server's message. A counter assistant looking at a unit held at
  another branch is told first that the server refuses a report from there.
- Each open report offers "Send for repair" and "Resolve" to a signed in
  administrator and to nobody else. Resolve asks for the outcome, repaired or
  written off, with neither chosen, the actual repair cost, which a repair
  needs, and notes, says in words what will happen to the unit, and posts to
  the resolution route. Counter staff see the status of each report and a
  sentence that the owner resolves reports. The rules are in
  `SC16-resolve-model.ts`, and the writes share `use-damage-write.ts`, which
  sends each one once.

#### Accessibility of this screen

Each choice is a radio group in a fieldset with a legend, with its help and
its error tied to the group, and each option is the whole target. Every error
is tied to its field and listed above the form with a link to it. The question
takes focus when it opens, and what a write did is said in a notice that takes
focus. Every status carries words beside its colour, every target is at least
44 pixels, and the screen fits a phone 360 pixels wide with nothing to scroll
sideways.

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
  amount is zero, so a line that would only say zero can be left out.
  `isNegativeMoney` and `unsignedMoney` let a screen write a deposit given back
  as released or returned instead of with a minus sign. None of them does a
  sum.
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
failed state. The privacy notice is scanned too. The counter's customer
lookup, new booking, checkout, dashboard, diary, locator, return screen,
overdue worklist and damage screen are scanned loaded, with a signed in
assistant, a customer, a booking, a day, units, hires and damage reports whose
answers the spec gives itself, from `e2e/counter-answers.ts`,
`e2e/overview-answers.ts`, `e2e/return-answers.ts` and
`e2e/damage-answers.ts`. The new booking is scanned again with a tool on it,
the checkout again with every problem of its form on the screen, the diary
again with the no show question open, the return again with its question
open, the worklist again with the question about a lost unit open, and the
damage screen again with every problem of its form showing, then with the
amount to recover and its question open.

`e2e/narrow-screens.spec.ts` also runs with or without the backend. It opens
My Hires, My Account with a hire in its history, and the nine counter screens
at 360 pixels wide and checks that nothing has to be scrolled sideways. It answers the API itself,
like the counter scans, because a layout check should not depend on what a
database holds.

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

`e2e/counter.spec.ts` needs the customer, checkout and returns routes. A
seeded counter assistant signs in, registers a walk in with a name and a number
nobody has used, books one unit for them for today at the assistant's own
branch, checks it out and sees the reference of the hire. Then they open the
hire from the checkout, take the unit back in the condition it went out in,
and see the deposit released in full with nothing due, and the booking listed
as returned. In a second journey the second seeded customer signs in and finds
the hire history on My Account. The model is the last one on the
first page the availability search for that branch lists, so a rerun finds a
unit the last run did not take. The desktop project signs in as the assistant at Cape Town
CBD, `elmarie@toolshedhire.co.za`, and the phone project as the one at
Bellville, `thabo@toolshedhire.co.za`, so the two never compete for a unit.
The password comes from `E2E_STAFF_PASSWORD` and falls back to the development
seed password. The spec asks `GET /api/customers`, a checkout,
`GET /api/rentals` and `GET /api/me/rentals` with no token first. A 404 or a
405 from any of them means the routes are not there, and both journeys skip
themselves. The unit goes back on the shelf at the end of the run.

A third journey in `e2e/counter.spec.ts` needs the damage routes as well. The
assistant books one unit for a new walk in through `e2e/counter-booking.ts`,
which takes the third last model free at the branch, checks it out, takes it
back one grade worse and sees the deposit waiting for a damage report. They
follow the link to `SC-16`, file a report that charges the customer R50.00,
far under any replacement value, and go back to the return, which shows the
deposit settled with the R50.00 withheld. Then the owner,
`marius@toolshedhire.co.za`, signs in on a browser of their own and resolves
the report as repaired, so the unit goes back on the shelf. A repair does not
raise the grade again, so a unit that went out at C is flagged for damage
instead. The steps are in `e2e/damage-journey.ts`. It asks
`GET /api/damage-reports` with no token first, through `e2e/damage-backend.ts`,
and skips itself when that route is not there.

`e2e/counter-overview.spec.ts` needs the dashboard, the diary and the asset
locator. A seeded counter assistant signs in, sees the name of their branch and
the five figures on the dashboard, opens the diary for today and then the
whole of next week, and finds `TSH-DR-0042`, which the seed always makes at
Cape Town CBD, by its tag in the locator. The figures are checked to be whole
numbers and not particular ones, because the other journeys book at the same
branches during the run. In its second journey the assistant registers a new
walk in, books one unit for them for today, sees the booking due out on the
dashboard and not collected in the diary, and marks it as a no show from the
diary with a reason. The answer replaces the question, the diary is read again
and after a reload shows the booking as a no show with nothing left to press,
and the dashboard no longer has it due out. The booking is made through SC-12
and SC-13 by `e2e/counter-booking.ts`, which takes the second last model free
at the branch, because the counter journey takes the last. A new walk in each
run means the strike lands on nobody else. The spec asks the three routes with
no token first. A 404 or a 405 from any of them means the routes are not
there, and both journeys skip themselves.

The API refuses a booking that starts today once the branch has closed for the
day. The pipeline runs the API for the browser tests with a clock pinned
inside business hours, so the counter journey books for today, checks out and
takes the unit back on the same day, and the no show journey always finds its
booking due out. Against a backend on the real clock, run the browser tests
before the seeded branches close at 17:00 in Cape Town.

The customers, the password rule and the sign in are in `e2e/customer.ts`, the
counter assistants in `e2e/staff.ts`, and the dates are counted at the
branches by `e2e/hire-dates.ts`.

One run makes fourteen sign ins. `session.spec.ts` signs the first customer in
four times, twice in each browser project, and the booking journey twice more.
The second customer is signed in six times, twice by each reservation spec and
twice by the hire history journey.
`account.spec.ts` signs in each of the two accounts it registers once, and
those count against addresses of their own. It also makes two registrations
and two reset requests, which the API throttles for one client address. The
API allows ten sign in attempts for one email address in a fixed window of
fifteen minutes, and thirty for one client address, and counts the ones that
succeed. So a second run inside the same window takes the first customer past
ten, is answered 429 and fails. Wait for the next quarter hour, or raise
`LOGIN_ATTEMPTS_PER_EMAIL` on the backend you test against, which is what the
pipeline does.

The two counter journeys and the two counter overview journeys each sign the
two counter assistants in once, so each assistant four times in a run, and the
damage journey signs the owner in once in each browser project, which counts
against their own addresses.

Set `E2E_REQUIRE_BACKEND=1` to turn all eight skips into failures. The pipeline
sets it, because there the backend is started for these tests and a skipped
spec would hide that it did not come up.

The scans use axe against the WCAG 2.2 level AA rules and fail on any serious
or critical violation. An automated scan cannot judge everything, so it
supports manual keyboard and screen reader checks and does not replace them.

After a run, the HTML report is in `playwright-report/`. It does not open by
itself. To read it, run `npx playwright show-report`.
