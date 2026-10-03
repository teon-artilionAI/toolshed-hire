# Toolshed Hire backend

FastAPI and PostgreSQL. This directory is the walking skeleton, which means it
proves the load bearing decisions end to end and nothing else. It is not a
first pass at the whole application.

## What it proves

1. A migration creates the seventeen tables of the documented schema in real
   PostgreSQL, with the `btree_gist`, `citext` and `pg_trgm` extensions, and a
   test reads the catalogue to confirm that what was built is what was
   designed.
2. A `daterange` GiST exclusion constraint rejects an overlapping allocation of
   the same physical asset.
3. Two genuinely concurrent transactions cannot double book one unit, because
   candidates are locked with `SELECT ... FOR UPDATE SKIP LOCKED` and the
   constraint has the last word.
4. A React client can call a role protected endpoint and get a correct answer.
5. A constraint violation surfaces as a clean HTTP 409, never a 500.
6. A session outlives its access token. Signing in, refreshing with rotation,
   reuse detection, signing out, the lockout and the throttles all work against
   real rows, and no route can be added without saying who may call it.
7. A reservation moves through its lifecycle by one set of rules. A customer
   builds a priced draft, holds named units for thirty minutes, confirms, reads
   and cancels, and twenty hold requests at once for five units give exactly
   five holds and fifteen clean refusals.
8. A customer can register, prove their email address, reset a forgotten
   password and edit their own details, and no public account route says
   whether an address has an account.
9. A counter assistant finds or registers a customer, books for them through
   the same reservation path a customer uses, and checks the booking out. In
   one transaction the rental is opened, every unit becomes an item and goes
   on hire, the hire and the deposit are charged, and the reservation is
   collected. Two checkouts at once open one rental.
10. The counter sees what is due today at its branch and the diary of any date,
   finds a unit at any branch, and a confirmed booking nobody collected becomes
   a no show that frees its units and counts a strike. Three strikes in twelve
   months put the customer on hold, and two sweeps at once count each strike
   once.
11. A unit that comes back a grade worse, or flagged, leaves availability in the
   transaction of its return and the deposit waits. A damage report records an
   explicit decision on the charge, recovers at most the replacement value, and
   settles the deposit when it was the last thing waiting. An administrator
   repairs, resolves or writes the unit off, and a written off unit keeps its row.

## Layout

| Path | Layer | Holds |
|---|---|---|
| `app/domain` | Domain | Entities as plain dataclasses, `BookingPeriod`, `Money`, enumerations, errors. No framework, no SQL, no IO. |
| `app/domain/policies` | Domain | The rules that can be swapped. `PricingPolicy` and its two implementations, and the totals of a reservation. |
| `app/domain/states` | Domain | The eight reservation states. The base state refuses every move and each state overrides the ones that are legal from it. |
| `app/application` | Application | Use cases, transaction boundaries and ports. One package per module, plus the unit of work, the clock and the audit log, which every module shares. |
| `app/infrastructure` | Infrastructure | Engine, SQL repositories, the SQL unit of work, the system clock, hashing, tokens. |
| `app/infrastructure/models` | Infrastructure | One SQLModel class per table, one module per subject area. |
| `app/infrastructure/notification` | Infrastructure | The SQL outbox, the Resend adapter and the two gateways that are not Resend. |
| `app/api` | API | Routers, dependencies, middleware, problem responses. `deps.py` is the composition root, `catalogue_deps.py` is its read side half, `identity_deps.py` wires the session use cases, `account_deps.py` wires registration, the two account links and the profile, `pricing_deps.py` chooses the pricing policy, `booking_deps.py` wires the reservation use cases, `customer_deps.py` wires the counter's customer lookup and the walk-in, `hire_deps.py` wires checkout and the rental read, `damage_deps.py` wires the damage reports, `counter_deps.py` wires the dashboard, the diary and the asset locator, and `sweep_deps.py` wires the sweep that lapses expired holds and marks no shows. `access_policy.py` is the deny by default check. `field_messages.py` holds the sentences shown for a query parameter the framework refused. |
| `alembic/versions` | Migrations | Hand written, because autogenerate cannot invent an exclusion constraint. |
| `alembic/baseline` | Migrations | The frozen definitions behind migration `0001`, one module per subject area. |
| `alembic/role_grants.py` | Migrations | What the restricted application role may do, behind migration `0002`. |
| `seed_data` | Tooling | The catalogue and the fleet as plain data. It opens no file and no connection. |
| `seeding`, `seed.py` | Tooling | The loader for that data, and its entry point. |
| `scripts` | Tooling | `provision_roles.py`, which creates the two database roles. |

Dependencies point inward only. The domain imports nothing from the other
layers, the application layer imports the domain and nothing else, and the API
layer is the only one that imports everything, because it is where the pieces
are put together.

The design document describes eight modules. Seven have code so far, and each
keeps the same name in every layer it appears in.

| Module | Domain | Application | Infrastructure |
|---|---|---|---|
| `identity` | `Actor`, `Branch`, `CustomerProfile`, `Account`, `RefreshSession`, `PendingToken`, `NewCustomer`, `CustomerDetails`, `WalkInCustomer` | `BranchRepository`, `CustomerRepository`, `BranchDirectory`, `CustomerDirectory`, `AccountRepository`, `SessionRepository`, `PasswordHasher`, `SignInUseCase`, `RefreshSessionUseCase`, `SignOutUseCase`, `RegisterCustomerUseCase`, `VerifyEmailUseCase`, `ResendVerificationUseCase`, `RequestPasswordResetUseCase`, `CompletePasswordResetUseCase`, `ReadProfileUseCase`, `UpdateProfileUseCase`, `LookUpCustomers`, `RegisterWalkInUseCase`, `AccountMailer` | `SqlBranchRepository`, `SqlCustomerRepository`, `SqlBranchDirectory`, `SqlCustomerDirectory`, `SqlAccountRepository`, `SqlSessionRepository`, `BcryptPasswordHasher` |
| `hire` | `Rental`, `RentalItem`, `Charge`, `check_out`, the asset state model in `asset_lifecycle`, `DamageReport`, the quarantine rule in `quarantine`, `file_damage_report` | `RentalRepository`, `CheckoutRentalUseCase`, `ReadRentals`, `CounterOverviewQuery`, `ReadCounterOverview`, `DamageReportRepository`, `FileDamageReportUseCase`, `SendForRepairUseCase`, `CloseDamageReportUseCase`, `ReadDamageReports` | `SqlRentalRepository`, `SqlRentalReads`, `SqlCheckoutReads`, `SqlCounterOverview`, `SqlDamageReportRepository`, `SqlDamageReportReads` |
| `catalogue` | `ProductModel`, `Asset` | `ProductModelRepository`, `CatalogueQuery`, `BrowseCatalogue`, `AssetLocatorQuery`, `LocateAssets` | `SqlProductModelRepository`, `SqlCatalogueQuery`, `SqlAssetLocator` |
| `availability` | `AssetAllocation` | `AssetRepository`, `allocate_assets`, `AvailabilityQuery`, `SearchAvailability` | `SqlAssetRepository`, `SearchAvailabilityQuery` |
| `booking` | `Reservation`, `ReservationLine`, `ReservationState` and its eight states, the no show rules in `no_show` | `ReservationRepository`, `CreateReservationUseCase`, `HoldReservationUseCase`, `ConfirmReservationUseCase`, `CancelReservationUseCase`, `MarkNoShowUseCase`, `ExpireHoldsAndNoShowsUseCase`, `ReadReservations` | `SqlReservationRepository`, `SqlReservationReads` |
| `notification` | `Notification`, `EmailMessage` | `NotificationOutbox`, `NotificationGateway`, `NotificationDispatcher` | `SqlNotificationOutbox`, `ResendEmailAdapter`, `FakeEmailGateway` |
| `money` | `Money`, `PricingPolicy`, `StandardPricingPolicy`, `FixedRatePricingPolicy`, `LineSnapshot`, `HireQuote`, `HireTotals` | `QuoteHire` | none yet, a quote writes nothing |

`reporting` gains its package when its first use case is built.
The audit trail belongs to no module, because every module writes to
it, so it has a file of its own in each layer. The throttle in
`app/application/throttle.py` and the ownership scope in
`app/application/ownership.py` belong to no module for the same reason.

## The four patterns in place

The design document names four patterns. All four are built.

### Repository with Unit of Work

A hold writes an allocation for every unit of every line, the new status of
the reservation and an audit event. BR-09 and BR-49 need those to commit
together or not at all, so exactly one object owns the transaction.

`UnitOfWork` is a port in the application layer. A use case enters it, works
through the repositories it exposes and calls `commit`. Leaving the block
without a commit rolls everything back. `SqlAlchemyUnitOfWork` implements it
over one `Session`, which it shares with every repository, the audit log and
the outbox.

```python
with self._uow as uow:
    reservation = load_for_change(uow, actor, key)
    reservation.hold(now=now, today=today, models=models, allocator=allocator)
    uow.reservations.save(reservation)
    record_change(uow, actor=actor, reservation=reservation, action="reservation.held", ...)
    uow.commit()
```

Three things live in exactly one place because of it.

- `SqlAssetRepository.lock_allocatable` is the only place that issues
  `SELECT ... FOR UPDATE SKIP LOCKED`. A reservation that is going to change
  is locked with a plain `FOR UPDATE`, which waits, because it is one
  particular row and not any free unit.
- `SqlAssetRepository.translate_integrity_error` is the only place a violation
  of the exclusion constraint becomes `AllocationConflictError`.
- `SqlAuditLog.record` writes the audit event in the same transaction as the
  change. If it cannot be written, the change does not happen (BR-49).

Every state changing use case leaves one audit event. It carries the actor and
the role the actor held at the time, the entity and the action, for example
`reservation.held`, the changed fields before and after, the request id and
the client address when the server knows one.

A use case is a class with one `execute(command)` method. It takes the unit of
work, a clock and anything else it needs through its constructor. The router
never builds one. `app/api/deps.py` does, and it is the only module that knows
which implementation stands behind each port a use case writes through. The
query objects of the read side are chosen the same way in
`app/api/catalogue_deps.py`.

### Adapter

`NotificationGateway` is the port. `ResendEmailAdapter` is the only class that
knows which email provider is in use. It calls the Resend HTTP API with a five
second timeout and returns a `DeliveryReceipt`. A status outside the 2xx
range, a timeout and a transport error each come back as a failed receipt with
a short reason. The adapter never raises for a delivery that did not happen.

The `notification` table is a transactional outbox (BR-19).

1. The use case writes the notification `QUEUED` in the same transaction as
   the confirmation of the reservation.
2. After the commit, with no transaction open, `NotificationDispatcher` sends
   whatever is queued and records `SENT` with the provider's message id, or
   `FAILED` with the reason.
3. A provider failure never rolls the booking back, and the dispatcher never
   raises.

Dispatch runs inside the request, after the commit and before the response.
Cloud Run only gives a container CPU while it is serving a request, so work
left for a background thread might never run. Every message carries an
`Idempotency-Key` derived from the notification id, so a notification that is
dispatched twice is delivered once.

Only a booking confirmation writes a notification row, and
`ConfirmReservationUseCase` is the one place that queues it. Creating a draft
and holding it write none, so nobody is sent a confirmation of a hold they
never confirmed.

### Strategy

BR-21 says a hire price is produced by a pricing policy and not by arithmetic
scattered through the system. `PricingPolicy` is a port in
`app/domain/policies`, and `StandardPricingPolicy` is the one implementation
that runs. `app/api/pricing_deps.py` builds it once at start-up and hands the
same one to every request. `FixedRatePricingPolicy` is its counterpart for
tests. It charges one fixed amount for a unit, so a test of a booking can state
its price in a line.

```python
quote = policy.quote(line, period, discount_percent)
```

`line` is a `LineSnapshot`, which is the daily rate, the weekly rate, the
deposit and the quantity as they were copied (BR-20). The policy never sees the
catalogue, so a price worked out from a snapshot at R280 does not move when the
catalogue goes to R310. The trade discount is an input as well. The policy
never looks one up.

The rule for one unit is the lower of two totals. Complete weeks at the weekly
rate with the days left over at the daily rate, or every day at the daily rate.
A hire shorter than a week has no complete week, so it is charged by the day.
The quantity multiplies that, the discount comes off as a percentage, and VAT
goes on what is left. `BookingPeriod.whole_weeks` and `remainder_days` do the
counting, and the week is seven days, named once as `WEEK_LENGTH_DAYS` on the
policy.

Three things live in exactly one place because of it.

- `StandardPricingPolicy.quote` is the only place a rate is multiplied by a
  number of days. `tests/unit/test_one_place_for_a_price.py` parses every
  module of `app` to keep it so.
- `VAT_RATE_PERCENT` in `app/domain/vat.py` is the only place the VAT rate is
  written, as `Decimal("15.00")`. Hire rates exclude VAT. A deposit carries
  none (BR-23).
- `Money.rounded` is the only place an amount is rounded, half up to the cent.

`Money` holds a `Decimal` and refuses a float wherever one is offered, as an
amount, as a multiplier or in a comparison (BR-22). An amount stays exact while
it is being worked on. The amount charged after the discount and the VAT on it
are each rounded once from the exact figure, because those are the two amounts
a charge is written with. The total is their sum and the discount shown is the
subtotal less the amount charged, so the figures on a quote add up to the cent.

The second Strategy is the late fee (BR-30, BR-31). `LateFeePolicy` is a port
in `app/domain/policies/late_fee.py`, `StandardLateFeePolicy` is the one that
runs, and `FixedLateFeePolicy` is its counterpart for tests, one fixed fee for
a unit that is late at all. `app/api/late_fee_deps.py` builds the standard one
once at start-up and hands it to the returns, the losses, the reads of a
rental and the counter's dashboard, so every late fee the API shows or charges
comes from the one policy.

```python
late = policy.late_fee(due_back_on=due, returned_on=today, fee_per_day=fee)
```

A policy is asked about one unit, because a late fee accrues per asset, with
the late fee per day copied onto its booking. Both days are business days in
Cape Town. It charges each whole day between the due date and the return, so a
return on the due date owes nothing, and it stops after
`ACCRUAL_LIMIT_DAYS`, which is fourteen, named on the policy. It answers with
the days late, the days charged, the fee, and whether the unit is beyond the
limit, which is what a loss is decided by. `StandardLateFeePolicy.late_fee` is
the only place a late fee per day is multiplied by a number of days, and
`tests/unit/test_one_place_for_a_late_fee.py` reads every module of `app` to
keep it so.

A late fee is quoted including VAT, so two days at R120.00 is R240.00 and
nothing is added to it. `split_vat_inclusive` in `app/domain/vat.py`, beside
the rate, is the one place such an amount is taken apart. The part before VAT
is worked back from the amount, rounded half up to the cent, and the VAT is
what is left, so R240.00 is written as R208.70 plus R31.30 and the two always
add back to the amount quoted. The seed's worked example uses the same split
and the same policy.

### State

BR-11 says a reservation changes status only along the permitted transitions.
`ReservationState` in `app/domain/states` declares the seven moves, `hold`,
`confirm`, `cancel`, `collect`, `expire`, `mark_no_show` and `close`, and its
own version of each refuses with `StateTransitionError`. A concrete state
overrides only the moves that are legal from it, and the four terminal states
share `TerminalState`, which overrides nothing. A move nobody thought about is
refused, because allowing it would have taken somebody writing it.

`Reservation` never changes its own status. It hands every move to the state
it is in.

```python
reservation.confirm(now=now, email_verified=verified)   # asks HeldState, or is refused
```

A state checks its guards before it changes anything, so a refused move leaves
the reservation exactly as it was. The thirty minutes of a hold and the 17:00
cutoff for a late cancellation are named constants beside the guards that use
them. Checkout calls `collect`, the no show sweep and the counter call
`mark_no_show`, and the return that brings the last unit back calls `close`.

A tagged unit has a state model of its own, the asset states of the design
document. `PERMITTED_ASSET_MOVES` in `app/domain/asset_lifecycle.py` is its
table, and `moved` refuses any move the table does not hold with
`StateTransitionError`. Checkout moves every unit to `ON_HIRE` through it.

### The clock

Nothing in the domain or the application layer reads the time from the
operating system. A use case is handed a `Clock`. `SystemClock` returns
instants in UTC and works out the business day in `Africa/Johannesburg`, so a
booking made at half past midnight in Cape Town belongs to the new day. The
tests use a clock that stands still, and one test reads the source of both
layers to make sure neither calls `datetime.now()` or `date.today()`.

A test process may set `TEST_BUSINESS_TIME`, for example `10:00`. The clock
the API uses then reads today's real date in Cape Town when the process
starts, starts at that time of day on it, and runs on in real time, which is
`StartedAtBusinessTimeClock` in `app/infrastructure/clock.py`. The browser
tests book for today and check out, and a hire can only start today while the
branch is open, so without it they would fail whenever CI ran after closing
time. The setting is honoured only when `ENVIRONMENT=test`, and every other
environment refuses to start with it set.

## The read side

A visitor with no account browses the catalogue and asks where a model is free
for a period (FR-02, FR-03, FR-04). Nothing is written, so there is no unit of
work, no lock and no audit event. A read goes through a query object.

| Port in the application layer | Query object in the infrastructure layer |
|---|---|
| `BranchDirectory` | `SqlBranchDirectory` |
| `CatalogueQuery` | `SqlCatalogueQuery` |
| `AvailabilityQuery` | `SearchAvailabilityQuery` |

The counter's reads are query objects of the same kind. `SqlCustomerDirectory`
finds a customer, and `SqlRentalReads` and `SqlCheckoutReads` read a rental and
a reservation about to be checked out. They are reached through the unit of
work, because the walk-in and the checkout read back what they have just
written inside the transaction that wrote it.

A query object selects columns and returns small frozen dataclasses that the
application layer defines, in the `read_models.py` of each module. It never
returns a table row. None of those dataclasses has a field for an asset tag, a
serial number or a number of units, so a customer cannot be told stock (US-07).
The single model question counts free units inside the database and returns
only whether there are enough.

Two services hold the rules that are not SQL. `BrowseCatalogue` refuses an
unknown category and answers an unpublished model as not found.
`SearchAvailability` checks the period through
`app/application/availability/hire_request.py`, which builds it as a
`BookingPeriod` and checks it with `ensure_within_booking_window`. `QuoteHire`
goes through the same module, so a search, a quote and a booking agree about
BR-02 to BR-05. The day it is comes from the clock.

A unit is free for a period when its status is `AVAILABLE` and it holds no
active allocation whose half open period overlaps the one asked about (BR-10).
The availability list answers for every model on the page and every active
branch in one statement. The condition is written with the same
`daterange(start_date, end_date, '[)') &&` expression as the exclusion
constraint, under `released_at IS NULL`, so the GiST index behind the
constraint can serve it, and the partial index `ix_asset_available` finds the
hireable units. An availability search issues the count and the page, plus one
lookup for a category and one for a branch when the search names them, whatever
the page holds. `app/infrastructure/availability_search.py` says how the
planner runs the statement and what slows down first as the fleet grows.

The order of a list comes from the `ModelSort` enumeration, which the query
object maps to columns. No part of a request is ever placed in a statement
(C-28).

Every query logs when it starts and when it finishes, with its filters, its row
count and its duration. The text a visitor searched for is logged by its length
only.

## Sessions and authorisation

This is the session model of the security section of the design document
(BR-41 to BR-46, BR-48, C-13 to C-25). Registration, email verification, the
password reset and the profile are in the section after this one.

### The two tokens

Signing in returns two things. The access token is a signed JWT in the
response body. It lives 15 minutes, carries `sub`, `role` and `branch_id`, and
names its signing key in a `kid` header. The `kid` is the first sixteen
characters of the SHA-256 of the key, so it needs no setting, and a token that
names a key the service does not hold is refused. The access token is never
set as a cookie.

The refresh token is opaque, 256 random bits, and only its SHA-256 is stored,
in `refresh_session`. It travels in a cookie and is never returned in a body.

```text
toolshed_refresh=<token>; Max-Age=604800; Path=/api/auth; HttpOnly; Secure; SameSite=Strict
```

`Secure` is dropped in development and test only, so local work over plain
HTTP still functions. `Max-Age` is what the session has left, which is seven
days at most.

A session ends 14 days after the sign in that started it, however often it is
used, and 7 days after it was last used. `expires_at` holds the first and is
copied to every successor. The second is worked out from `issued_at`.

### Rotation and reuse

A refresh token works once. `POST /api/auth/refresh` stamps the session as
rotated, revokes it with the reason `ROTATION` and opens a successor in the
same family with a new token. The account is read again at that moment, so a
deactivated account gets nothing further.

A token that arrives a second time revokes every live session of its family
with the reason `REUSE_DETECTED`, writes the audit event
`auth.refresh_reuse_detected` and is answered 401. The row is read under a row
lock, so of two requests that present one token the second waits and is then
treated as the reuse it is. A client must therefore never send two refreshes
at once.

`POST /api/auth/logout` revokes the family with the reason `LOGOUT` and clears
the cookie. It answers 204 whatever it was handed.

Both routes are authenticated by the cookie alone, so both check the `Origin`
header. When it is present it must be one of `CORS_ORIGINS`, and anything else
is 403. A request with no `Origin` is allowed, because `SameSite=Strict`
already keeps the cookie off every cross site request.

### Sign in failures

A wrong password, an unknown address, a locked account and a deactivated
account are answered with the same 401, byte for byte. Exactly one bcrypt
verification runs on every path, against a dummy hash when there is no account
to check, so the time the answer takes does not give the reason away. The
reason goes to the audit event `auth.login_failed` and to the log. A success
writes `auth.login_succeeded`.

Five failures inside fifteen minutes lock the account for fifteen minutes
(BR-46). The window slides with the clock. Each wrong password is counted in
`rate_limit_counter`, in the second it happened in, under a salted SHA-256 of
the account key, and the account is told how many failures the fifteen minutes
that end now hold. It keeps the smaller of that number and its own
`failed_login_count` plus one, and on the fifth it writes `locked_until`. Its
own count goes back to zero on a success, on a password reset and when a lock
has run out, so a failure from before any of those is never counted again,
even while its fifteen minutes are still running. That needed no new table and
no new column.

A failure is timed to the second. One that is less than a second older than
the window is still counted, which errs towards locking. An attempt refused
because the account is already locked is not a failure of its own, so knocking
on a locked account does not keep it locked. The unknown address and the wrong
password still get the same answer after the same single bcrypt verification.
The failure counters are written for a known account only, which costs two
short statements and no hash.

### Throttling

Every sign in attempt is counted in two fixed windows of fifteen minutes
before any password is looked at. One window is for the address being signed
in to and allows 10 attempts. The other is for the client address and allows
30. Going over either is a 429 with `Retry-After` in seconds.

`LOGIN_ATTEMPTS_PER_EMAIL` and `LOGIN_ATTEMPTS_PER_ADDRESS` set the two limits.
The defaults are 10 and 30, and neither can be set below 1. Development and
test accept any value from 1 up, which is what lets a browser test run sign one
seeded account in more often than a person would. Staging and production
accept only a value at or below the default, and the process refuses to start
on a higher one. The window is not a setting.

The counters are rows in `rate_limit_counter`, because the instances share no
memory. A bucket is keyed by a salted SHA-256 and never by the address. The
salt is derived from `JWT_SECRET`. Counting is one atomic statement, and it is
committed before the password check starts, so the lock on a counter row lasts
one statement and not one bcrypt. Windows older than a day are deleted, at
most once every fifteen minutes by each process.

`Throttle` in `app/application/throttle.py` is the reusable piece. The account
routes use it with seven rules of their own, listed in the next section, and
the lockout uses its sliding count.

Clients whose address the server cannot work out share one window. The limit
of 30 only means what it says when the platform forwards the real client
address, so that is worth checking after the first deployment.

### Deny by default

Every route declares who may call it, by depending on one of three kinds of
policy.

| Policy | Declared by | Admits |
|---|---|---|
| Public | `public_access` | A caller with no account. |
| Roles | `require_roles(...)`, or one of `CustomerUser`, `CounterUser`, `AdminUser`, `AnyRoleUser` | The roles it names. |
| Refresh cookie | `refresh_cookie_access` | The holder of a refresh cookie, from this site. |

The application walks its route table when it is built and again when it
starts serving. A route that depends on none of them stops the process with a
message naming it, and so does a route that declares itself public and names
roles as well. `tests/api/test_route_policies.py` enumerates the same table, so
a missing policy fails the build first. That file also holds the role and
endpoint matrix, one row for a representative endpoint of every module.

The role dependencies read the role from the `user_account` row on every
request and not from the token. That is stricter than the fifteen minutes the
design document allows a claim to be trusted for.

Waivers, user and role management and force release do not exist yet. When
they are added they depend on `FreshAdminUser` from `app/api/identity_deps.py`.
It reads the account again under a shared row lock, so the role that is checked
is the role that holds until the action commits.

### Ownership and branch scope

A read on behalf of a customer takes an `OwnerScope`, and the repository puts
it in the WHERE clause. A reservation that belongs to somebody else is not
found, and the answer is the same 404 as for a key nobody issued (BR-42).
Every lookup of one reservation does it, the read behind
`GET /api/reservations/{id}` and the locked read behind each move alike, so a
customer can neither see nor change a reservation that is not theirs.

`ensure_branch_scope` in `app/domain/identity.py` refuses a write by counter
staff to a branch that is not their own with `BranchScopeError`, which is a 403
(BR-43). Creating a reservation checks the branch it is for, and holding,
confirming and cancelling check the branch of the reservation. Staff reads are
not restricted by branch.

## Registration and account security

This is FR-01 and US-01 to US-05 of the design document, with BR-45 to BR-47,
C-13, C-14, C-17, C-18 and C-26.

### Registering

`POST /api/auth/register` writes a `user_account` with the role `CUSTOMER`
and no verified address, and a `customer_profile` of type `INDIVIDUAL` and
status `ACTIVE` with no discount, registered at the branch the person chose.
The two rows and the audit event `auth.registered` are one transaction, so
there is never an account without its profile. The password has to be twelve
characters or more and is hashed with bcrypt at work factor 12 before the
transaction opens. It is never logged and never returned. The request body
names every field it accepts, so a submitted `accountStatus`, `role` or
`tradeDiscountPercent` is a 422 that names the field and never reaches a row.

### No answer says whether an address has an account

Registration and the reset request answer 202 with the same body for every
address (R-13, C-14). The body is `{"emailDeliverable": ...}`, which says
whether this environment would hand a message for that address to the email
provider at all. It comes from the gateway and depends on the configuration
and the address only.

The work is the same as well. A registration hashes the password and mints a
token on both paths, writes one audit event and sends one message. A new
address is sent the verification link. An address that already has an account
gets no new account, nothing about the old one changes, the attempt is written
as `auth.registration_repeated`, and its holder is sent a short note saying
somebody tried to register with it and that they can sign in or reset their
password there. The note carries no token. What still differs is two inserts,
a millisecond or so beside a hash of a quarter of a second.

A reset request mints and hashes a token for every address and writes one
audit event, `auth.password_reset_requested`. Only an address with an active
account has the token stored and is sent the link. An address with no account
is sent nothing, because writing to strangers is worse than what it would
hide. So one timing difference remains, and I state it plainly. When the
address is unknown no call is made to the email provider, and the answer comes
back sooner by however long that call takes for a known address. That is
usually a few hundred milliseconds and at most the five second timeout of the
adapter. Someone timing reset requests can therefore tell a known address from
an unknown one where mail is delivered. The throttles below limit how fast
anybody can ask. Where mail is not delivered to the address, which is what
`emailDeliverable: false` says, no call is made on either path and the
difference is gone.

### The two links

A verification link is `{FRONTEND_ORIGIN}/register#verify=<token>` and a reset
link is `{FRONTEND_ORIGIN}/signin#reset=<token>`. The token rides in the
fragment, so it never reaches a server log or a `Referer` header. A token is
32 random bytes. It is sent once, in the message, and only its SHA-256 is
stored, in the four columns `user_account` already had. A verification token
lasts 24 hours and a reset token 60 minutes, `EMAIL_VERIFICATION_LIFETIME` and
`PASSWORD_RESET_LIFETIME` in `app/domain/account_tokens.py`. Each works once,
because redeeming it clears it, and a new one replaces the old one. A token
that is unknown, already used or out of time is a 400 with the problem type
`verification-link-invalid` or `reset-link-invalid`, in one sentence for all
three. The reason goes to the log.

`POST /api/auth/email-verification/resend` is for any signed in account. It
sends a new link and does nothing for an account that is already verified,
with the same answer.

### Completing a reset

`POST /api/auth/password-reset/complete` sets the new hash, clears the token,
lifts any lock and revokes every refresh session of the account, in one
transaction with the audit event `auth.password_reset_completed`. A browser
that was signed in with the old password is signed out at its next refresh.
The sessions are revoked with the reason `LOGOUT`. No reason is added to the
enumeration, and of the four it has `LOGOUT` is the nearest, because the
holder of the account ended the sessions and no administrator did. The audit
event says exactly why. A new password under twelve characters is a 422 that
names `newPassword`.

### The messages

The three messages go through the `NotificationGateway` port, so the Resend
adapter and the fake both carry them. None of them writes a `notification`
row, because that table records the booking confirmation and nothing else.
Each is sent inside the request, after the commit and with no transaction
open, with the five second timeout the adapter already has. A message that
cannot be sent never fails the request. It is logged as
`account_mail.send_finished` or `account_mail.gateway_fault`, with the kind of
message and never the address or the token.

### The throttles of the account routes

Every account route is counted before it does any work, in `rate_limit_counter`
through the same `Throttle` as signing in. One attempt over a limit is a 429
with `Retry-After`.

| Variable | Default | Counted for | Window |
|---|---|---|---|
| `REGISTER_ATTEMPTS_PER_EMAIL` | 5 | the address being registered | 1 hour |
| `REGISTER_ATTEMPTS_PER_ADDRESS` | 10 | the client address | 15 minutes |
| `VERIFICATION_ATTEMPTS_PER_ADDRESS` | 20 | the client address | 15 minutes |
| `VERIFICATION_RESENDS_PER_ACCOUNT` | 5 | the signed in account | 1 hour |
| `RESET_REQUESTS_PER_EMAIL` | 5 | the address a link is asked for | 1 hour |
| `RESET_REQUESTS_PER_ADDRESS` | 10 | the client address | 15 minutes |
| `RESET_COMPLETIONS_PER_ADDRESS` | 10 | the client address | 15 minutes |

The two that send a message to an address somebody typed are counted for that
address in an hour, so one mailbox cannot be filled by asking again and again.
The limits follow the rules of the two sign in limits. None may be below 1,
development and test accept any value from 1 up, and staging and production
accept a value at or below the default only. The windows are not settings. The
design document sets no numbers for these seven, so the defaults are mine.

### The profile

`GET /api/me/profile` and `PATCH /api/me/profile` are for a customer and for
nobody else. The profile is found by the account that is signed in, so there
is no key to guess, and an account with no profile is a 404. An edit takes any
of `fullName`, `phone`, `billingAddressLine1`, `billingSuburb`, `billingCity`,
`billingPostalCode`, `companyName` and `vatNumber`, all of them or none, and
refuses any other field with a 422 that names it. `fullName` changes the name
on the account and the display name on the profile, and `phone` changes the
phone on the account and the contact phone on the profile. A trade customer
cannot clear the company name. An edit that changes something writes
`customer.profile_updated`, whose `after_state` names the fields that changed
and not their values, because a log that can never be rewritten is the wrong
place to keep every address a customer has had.

## The reservation lifecycle

A customer puts one or more models into a reservation for one period at one
branch, sees what it will cost, holds named units for thirty minutes, confirms,
looks at their reservations and cancels one (FR-05 to FR-11).

| From | To | Move | Guards and effects |
|---|---|---|---|
| DRAFT | HELD | `hold` | The start is not before today and not more than 90 days ahead, and not today once the collection branch has closed. The hire is within the limits of every model. Every line is given all of its units at the collection branch. The hold expires thirty minutes later. |
| DRAFT | CANCELLED | `cancel` | Nothing is held, so nothing is released. |
| HELD | CONFIRMED | `confirm` | The hold has not run out. A hire for today is refused once the collection branch has closed. Every line holds its quantity. The customer has a verified email address, or staff are confirming for them. The expiry is cleared and the confirmation is queued. |
| HELD | CANCELLED | `cancel` | The caller owns it or is staff. The units are released with the reason `CANCELLED`. |
| HELD | EXPIRED | `expire` | The hold has run out. The units are released with the reason `EXPIRED`. |
| CONFIRMED | COLLECTED | `collect` | On or after the first day of the hire, by staff at the collection branch. `CheckoutRentalUseCase` makes the move in the transaction that opens the rental. |
| CONFIRMED | CANCELLED | `cancel` | The caller owns it or is staff, and no rental exists. The units are released. After 17:00 on the day before collection it is counted as a late cancellation. |
| CONFIRMED | NO_SHOW | `mark_no_show` | The sweep, once the collection branch has closed on the first day of the hire, or staff at the counter from the start of that day. The units are released with the reason `NO_SHOW` and the strike is counted. |
| COLLECTED | RETURNED | `close` | The last unit of its rental is back or recorded as lost. `ReturnRentalItemsUseCase` or `RecordLossUseCase` makes the move in the transaction that closes the hire. |

Any other move is a `StateTransitionError`, which is a 409.

**Today closes with the branch (BR-04).** A hire may start today only while
the collection branch is open. Once it has closed nobody can collect, and the
sweep would call a confirmed booking for today a no show at once, with a
strike against the customer. So `ensure_branch_open_for_start` in
`app/domain/period.py`, beside the booking window, refuses today as a start
date from the moment after closing time by the clock in Cape Town. The branch
is still open at the very instant it closes, the instant the sweep counts
from, so the two rules meet without a gap. Creating a draft is refused with a
422 naming `from`, "The branch has closed for today. The earliest a hire can
start is tomorrow." Putting a draft on hold and confirming a hold ask again,
because a draft made before closing can be acted on after it.

**A draft is a basket.** `CreateReservationUseCase` creates it with its totals
and allocates nothing. The rates, the deposit, the late fee and the replacement
value of each model are copied onto its line (BR-20), the pricing policy prices
each line from that copy with the trade discount on the customer's profile, and
`totals_of` adds the answers up. The subtotal is the hire after the discount,
so the subtotal and the VAT add up to the total. A later change to the
catalogue never alters a reservation that exists.

**A hold is all or nothing.** `HoldReservationUseCase` gives every line named
units through the allocation algorithm, in one unit of work (BR-07, BR-09). A
line that cannot be given all of its units fails the whole hold, and the answer
is a 409 whose sentence names the model and the dates. It never says how many
units are left. The counts go to the log.

**A hold lapses lazily.** There is no scheduler. `ExpireHoldsAndNoShowsUseCase`
lapses the holds that have run out before a hold, before a confirmation, before
a reservation or a list of them is read, and before an availability search is
answered (BR-13). One call takes at most 25 reservations, oldest expiry first.
It locks the due rows, checks each again and lapses it, so two sweeps at once
take turns and the second finds nothing left to do. Its query reads through the
partial index `ix_reservation_hold_expiry`. Every use case that is about to
decide something about one reservation also lapses that one itself, so the
bound on the batch never lets an expired hold be confirmed. The other half of
the same sweep marks the bookings nobody collected, which is described under
the counter overview below. Each half runs in a transaction of its own.

**A confirmation is where the customer is told.** `ConfirmReservationUseCase`
queues the booking confirmation in its own transaction and sends it after the
commit, inside the request (BR-19).

**A cancellation deletes nothing.** `CancelReservationUseCase` releases every
unit in the same transaction as the change of status (BR-14), and nothing is
charged. A late cancellation raises `late_cancellation_count` on the customer
profile by one. There is no route that deletes anything (BR-51).

**A customer on hold cannot book.** A profile whose `account_status` is not
`ACTIVE` is refused when a draft is created and again when it is put on hold,
with `AccountOnHoldError`, which is a 403 (BR-18). For an account on hold the
`detail` says why, which is three bookings in the last twelve months that were
not collected, and that an administrator lifts the hold.

Every change of status writes one audit event in the same transaction (BR-49),
`reservation.created`, `reservation.held`, `reservation.confirmed`,
`reservation.cancelled`, `reservation.expired`, `reservation.collected` or
`reservation.no_show`. A lapse and a no show the sweep marked have no actor,
because nobody asks for a sweep. Putting a customer on hold writes
`customer.put_on_hold` as well.

**A customer's list leaves out abandoned baskets.** A draft that was replaced
by a changed basket, or thrown away, is cancelled without ever holding a unit.
That is not a cancelled booking, so a customer's own list leaves it out. The
condition is in the statement, an `EXISTS` over the allocations of its lines,
so the count and the page agree. Staff still list every reservation, and an
abandoned one can still be read by its key.

Two things here get worse with volume and are worth naming. The list is found
with OFFSET and counted in full. A customer's own list is short and indexed, so
the first query to slow down is the list staff ask for with no filter, which
sorts every reservation by its creation time. The sweep runs on the request
path, one bounded batch a call, so if holds ran out faster than requests
arrived to sweep them, expired holds would wait and their units would look
taken for longer. At a hundred times the volume the list wants a keyed page and
the sweep wants a scheduled job.

Holding a line of more than one unit under heavy contention has one more
property worth knowing. `SKIP LOCKED` lets several requests each lock some of
the free units, and a request that locked fewer than it needs is refused and
lets them go. Nobody is ever left half held, but two requests that each wanted
two of the last three units can both be refused and have to try again.

## Counter bookings and checkout

A counter assistant finds or registers a customer, books for them and hands the
equipment over with the deposit taken (FR-13, FR-14, FR-17, US-20 to US-22).

**Finding a customer.** `LookUpCustomers` searches by part of a name, by a
phone number or by the email address of an account, two to eighty characters,
a page of at most fifty, best match first. An exact phone number or address
comes first, then a name that starts with the text, then a name with a word
that starts with it, then any other. Each way of matching stands on an index.
The name has the trigram index of the baseline. The email reaches its profile
through the unique index on the address and the unique index on
`customer_profile.user_account_id`. The phone had only a btree, which finds a
number typed exactly as it was stored, and a number is stored as the customer
typed it, for example `082 441 7719`. Revision `0003` adds a trigram index over
the digits of the number, with the spaces, hyphens, brackets and plus sign
taken out, and the search writes the same expression, so `0824417719`,
`082 441` and `7719` all find it. `tests/integration/test_customer_search_index.py`
asks the planner to prove each of the three is used. The two LIKE wildcards
are taken out of the text, so a search for `%` finds nobody. The text is logged
by its length only.

**Registering a walk-in.** `RegisterWalkInUseCase` writes a customer profile
with no account, so no password exists and nothing is mailed. The details are
checked by the rules a person registering online is held to, and a trade
customer needs a company name. Counter staff register at their own branch and
are refused with 403 for naming another. An administrator belongs to no branch
and has to name one. The audit event `customer.walk_in_registered` says what
kind of customer was registered and where, and none of their details.

**Booking at the counter.** There is no second path (FR-14). Staff use the
reservation routes a customer uses and name the customer in
`customerProfileId`. Counter staff are held to their own branch on every
write. Anybody may book for today. A confirmation by staff satisfies the
verified email rule (BR-47), so a walk-in with no address can be confirmed.
Staff list reservations at any branch and narrow them with `customerProfileId`,
`branchCode` and `status`. The branch filter was called `branch` before, and
that name is still accepted.

**Checking out.** `CheckoutRentalUseCase` does it all in one unit of work. It
locks the reservation, refuses one at another branch (403), finds any rental
already opened from it, refuses a reservation that is not confirmed or whose
hire has not started (409, with a sentence that says which), locks the units
it holds in tag order, draws the next reference from `rental_reference_seq`,
and hands the rest to `check_out` in `app/domain/checkout.py`. The domain
checks that every active allocation is listed exactly once and that the
agreement is signed (422, naming the field), turns each allocation into one
rental item with its condition, accessories and meter reading (BR-28), moves
each unit to `ON_HIRE` through the asset state model with the condition and
the reading it went out with, and raises two charges from
`app/domain/checkout_charges.py`.

| Charge | Amount | VAT | Belongs to |
|---|---|---|---|
| `HIRE` | The subtotal and the VAT stored on the reservation, never worked out again (BR-20). | 15.00 percent, as stored. | The one unit on a hire of one unit, as in the worked example. The hire as a whole otherwise. |
| `DEPOSIT_HOLD` | The deposit copied onto each line, added once for every unit collected (BR-27). | None (BR-23). | The hire as a whole. |

Both are written `SETTLED` with a simulated reference such as
`SIM-TSH-H-26-000099-01` (BR-33). The reservation moves to `COLLECTED` last,
through its own state. The use case writes `reservation.collected`,
`rental.checked_out` and one `asset.status_changed` for every unit, and
commits once. A checkout asked for again finds the rental the first one opened
and answers 200 with it, writing nothing. Two at once take turns on the lock
of the reservation, and the unique key on `rental.reservation_id` would refuse
a second rental if anything got past it.

**Reading a rental.** `ReadRentals` returns a rental by its key or its
reference, with its items and its charges, in three statements however many
units it has. The checkout read is two. `daysLateToday` and `lateFeeToday` are
what the late fee policy says a unit still out would owe if it came back
today, and `settlementWaitingOn` is the domain's `settlement_wait`, the same
rule the return asks before it settles, both worked out in
`app/application/hire/progress.py`. `damageAssessment` is `NOT_NEEDED` until
damage and quarantine arrive, and `damage_assessment_of` is the one function
that change replaces. A customer is never shown a tag.

What degrades first as the data grows is the customer search on a short text.
A trigram index cannot narrow a name pattern of two characters, so a search
for `al` reads the whole index and sorts every match to find the first page,
and the page is found with OFFSET. Three characters or more stay cheap, so the
counter screen should ask for three before it searches. A checkout writes one
audit event and one update for every unit, which is linear in the units of one
booking and bounded by the twenty lines of ten units a reservation can carry.
At a hundred times the volume the lock on the reservation still only makes two
assistants checking out the same booking wait for each other. Two different
bookings never wait on one another, unless they share a unit, which the
exclusion constraint already rules out.

## The counter overview

Counter staff see what is due today at their branch, open the diary of any
date, find a unit at any branch, and a confirmed booking nobody collected
becomes a no show that frees its units (FR-12, FR-15, FR-16, US-10, US-18,
US-19, US-37, BR-17, BR-18, BR-43).

**The no show half of the sweep.** `ExpireHoldsAndNoShowsUseCase` now has both
halves, each in a transaction of its own. The second takes at most 25
confirmed reservations whose collection branch has closed on the first day of
the hire, by the clock in Cape Town, earliest first day first. Its query joins
the branch for its closing time, writes the status as the literal the partial
index `ix_reservation_confirmed_start` is filtered on, and locks the
reservations with `FOR UPDATE`, waiting and never skipping. Each one is checked
again under the lock and then goes through `mark_as_no_show` in
`app/application/booking/no_show.py`. That moves it through its state, releases
every unit with the reason `NO_SHOW`, writes `reservation.no_show` with no
actor, locks the customer profile, raises `no_show_count` by one in the
database and counts the strike. Two sweeps at once take turns on the rows, and
the second finds them already marked.

**Three strikes.** The strike is counted from the reservations, as the no
shows of the customer whose hire started after the same day a year ago, through
`ix_reservation_customer_start`, and not from `no_show_count`, which only ever
goes up. At the third an account in good standing goes `ON_HOLD` in the same
transaction and `customer.put_on_hold` is written. An account already on hold
or blacklisted keeps its standing. The profile is locked before the count, so
two no shows of one customer at once take turns and the second counts the
first. The rules are in `app/domain/no_show.py`.

**A no show by hand.** `POST /api/reservations/{id}/no-show` with a `reason` is
`MarkNoShowUseCase`. It is the same move and the same strike, for counter staff
of the collection branch and administrators, from the start of the first day
of the hire. Staff can see that nobody came, so they need not wait for closing
time. The reason is kept in the audit event, which names the member of staff.
There is no column for it, and a no show is not a cancellation, so it is not
written to `cancellation_reason`. A booking that is not confirmed or whose
hire has not started is a 409 whose sentence says which.

**The dashboard and the diary.** `ReadCounterOverview` checks the branch, runs
the sweep and reads through `SqlCounterOverview`. Counter staff read their own
branch and naming another is a 403. An administrator names one, and leaving it
out is a 422 naming `branchCode`. The dashboard lists the confirmed bookings
whose hire has started, the hires due back today with a unit still out and the
hires due back before today with a unit still out, fifty rows each at most,
with the true totals and the units on hire and in quarantine at the branch. The
diary lists, for one to seven days from any date, the bookings starting each
day in `CONFIRMED`, `COLLECTED`, `RETURNED` or `NO_SHOW`, and the hires due
back each day. `canMarkNoShow` comes from `no_show_refusal`, the rule the route
enforces. `lateFeeAccrued` is what the late fee policy says each unit still
out would owe if it came back today, added up, so the dashboard shows what the
counter would charge.

**The asset locator.** `GET /api/assets/locator` is `LocateAssets` over
`SqlAssetLocator`, for staff at every branch. It matches part of the tag or of
the model name, two to eighty characters, a page of at most fifty in tag
order, and a unit on hire carries the day it is due back and its rental.

| Read | Statements | Indexes |
|---|---|---|
| Dashboard | 6, and the route adds the account, the branch and the sweep for 10 | `ix_reservation_confirmed_start`, `ix_rental_open_due_back`, `ix_asset_branch_status`, the unique key on a line's reservation and model, `ix_rental_item_rental` |
| Diary | 4, and 8 through the route | `ix_reservation_branch_start`, `ix_rental_branch_due_back`, and the same two for lines and units |
| Locator | 2, the count and the page | `ix_asset_tag_trgm`, `ix_asset_product_model`, `ix_rental_item_asset` |

`tests/integration/test_counter_reads.py` counts the statements with few rows
and with many, and `tests/integration/test_counter_read_indexes.py` asks the
planner to prove each index is used.

**What the sweep costs a request.** Three statements when nothing is due, one
for each part, each read through a partial index that holds only rows that
could be due. The third part, which marks hires overdue, is described under
Returns and settlement. When something is due, each reservation of a batch is loaded
with its lines and allocations and written by its own statements, and a no
show adds the lock, the count and the update of its customer. Twenty five of
each is the most a request ever pays for.

**What degrades first as the data grows.** The backlog of the sweep. It clears
one batch of each half a request, so if bookings were missed faster than
requests arrived to sweep them, their units would look taken for longer, and
at a hundred times the volume the sweep belongs in a scheduled job. After that
comes the diary of a busy branch, whose lists are not capped because the
contract shows every booking of a day, so seven days of a branch with
hundreds of hires a day are a few thousand rows held at once. The locator on a
two character text is the third, because a trigram index cannot narrow a
pattern that short, so the counter screen should ask for three.

## Returns and settlement

Units come back, the late fee is charged, the deposit is settled and what it
cannot cover is paid at the counter (FR-18, FR-19, FR-21, US-23, US-25, US-26,
US-29, BR-24, BR-29 to BR-33, BR-52, BR-53). There is no new table and no new
column.

**Taking units back.** `ReturnRentalItemsUseCase` does it all in one unit of
work, for counter staff of the branch the hire went out from and
administrators. It locks the rental, then the reservation, then the units
coming back, always in that order, and hands the rest to `return_items` in
`app/domain/returns.py`. The domain refuses a unit listed twice, one that is
not on the rental and a meter reading below the one it went out with (422,
naming the field), and then a unit already back (409), so a refused return
changes nothing. For each unit it records the condition, the meter, the
accessories, the notes and the time, asks the late fee policy for the days
late and the fee, raises a `LATE_FEE` charge when there is one, lets the
allocation go with the reason `RETURNED` and moves the unit to `AVAILABLE`
through the asset state model, so it can be booked from that day. The rental
moves to the status `Rental.status_on` gives it, and when the last unit is
back it records when and by whom and the reservation is closed through its
state. The use case writes `rental.items_returned`, an `asset.status_changed`
for every unit and `reservation.returned`, and commits once. Two returns of
one unit at once take turns on the lock of the rental, and the second is
answered 409. A unit back in a worse grade, or with `flaggedForDamage`, goes
to `QUARANTINED` instead of `AVAILABLE`, which is the next section.

**Settling the deposit (BR-32, BR-53).** `settle_when_nothing_waits` in
`app/application/hire/settle.py` asks `settlement_wait` what the rental still
waits on, the units, then any damage assessment, then a balance. When the
answer is nothing it calls `settle_deposit` in `app/domain/settlement.py` in
the same unit of work. `deposit_settlement_of` is the calculation, with no
database. What is owed is the late fees and recovery charges still pending.
The deposit pays what it can, so what is withheld is never more than what is
held, the rest is released as a `DEPOSIT_RELEASE` charge with a negative
amount, and what the deposit cannot cover is `balanceDue`. Each pending charge
the deposit covers in full, in the order they were raised, becomes `SETTLED`
with a simulated reference that numbers it on the rental. With nothing due
every charge is settled, the rental is `SETTLED` and `settled_at` is stamped.
With a balance due the rental stays `RETURNED` and `settlementWaitingOn` is
`BALANCE_PAYMENT`. A unit waiting for its damage report makes
`assessments_due_on` answer more than nought, so the rental waits on
`DAMAGE_ASSESSMENT`, and the report that completes the last assessment calls
the same function.

| Charge | Amount | VAT | Status when raised |
|---|---|---|---|
| `LATE_FEE` | What the policy says, split by `split_vat_inclusive`. | Included in the amount. | `PENDING` until the deposit or a payment covers it. |
| `DEPOSIT_RELEASE` | What is left of the deposit, negative. | None (BR-23). | `SETTLED`. |
| `DEPOSIT_FORFEIT` | The deposit of a lost unit. | None. | `SETTLED`, from the deposit held. |
| `DAMAGE_RECOVERY` | The replacement value of a lost unit less its deposit kept, or the amount a chargeable damage report recovers, split for VAT. | Included in the amount. | `PENDING`, like a late fee. |

The worked example holds. R1,200.00 held, two days late at R120.00, R240.00
withheld as R208.70 plus R31.30 VAT, R960.00 released, R0.00 due, `SETTLED`.
`tests/api/test_returns.py` follows it through the routes.

**A settled charge is never edited (BR-24).** `Charge.settled` is the one way
a charge moves on, and it refuses a charge that is no longer `PENDING`. The
repository writes a charge's status only from `PENDING` to `SETTLED`, and
refuses to write over a stored charge that is settled, waived or reversed, so
no path in the application edits one.

**A lost unit (BR-31).** `POST /api/rentals/{id}/items/{itemId}/loss` is
`RecordLossUseCase`, for a unit more than fourteen days past its due date. I
read the rule as four things done together, in `app/domain/loss.py`. The unit
is charged the fourteen days of late fee the policy charges. Its allocation is
let go first, because a unit may not be marked lost while it holds one
(BR-37), with the reason `RETURNED`, since there is no reason for a loss, and
the unit moves from `ON_HIRE` to `LOST`. The deposit copied onto its booking
line is kept as `DEPOSIT_FORFEIT`. The rest of its replacement value is
recovered as `DAMAGE_RECOVERY`, the replacement value less the deposit kept,
never below nothing and so never above the replacement value. The unit is
closed on the rental with the time it was recorded and no condition, which is
how a lost unit is told from one that came back, and the rental moves on as
though it had. At settlement the forfeit counts as withheld and is not
available to pay anything else.

**The balance payment (BR-33).** `POST /api/rentals/{id}/balance-payment` with
a `paymentReference` of 1 to 40 characters is `RecordBalancePaymentUseCase`.
It settles every pending charge with that reference, brings the balance to
nothing and settles the rental. A rental with nothing due is a 409. No gateway
is called.

**Overdue (BR-52).** The lazy sweep has a third part,
`mark_overdue_rentals` in `app/application/hire/overdue.py`. It locks at most
25 rentals with a unit out past their due date that do not already read
`OVERDUE`, earliest due date first, through `ix_rental_open_due_back`, asks
`Rental.status_on` again under the lock, moves each one and writes
`rental.overdue` with no actor. I read BR-52 as the status a rental reads as,
so a partial return of an overdue hire with a unit still out leaves it
`OVERDUE`, a partial return before the due date makes it
`PARTIALLY_RETURNED`, and the last unit back makes it `RETURNED`. The batch is
bounded, so `GET /api/rentals/{id}` makes sure of the one rental it is about to
show with `mark_overdue_rental`. A rental with a unit out past its due date
that is not yet stored as `OVERDUE` is locked, moved, recorded and committed,
and read again, so its detail never reads `OPEN` while the list reads
`OVERDUE`. A rental already up to date is read with no lock and no write.

**The lists.** `GET /api/rentals` is `ListRentals.for_staff`. It runs the sweep
first and lists rentals at any branch, the overdue first, the most overdue
first, and then the rest newest first, narrowed by `branchCode`, `status`,
`overdueOnly` and `customerProfileId`. `GET /api/me/rentals` lists the caller's
own rentals newest first, with `assetTag` null on every item. Each is four
statements however long the page is, the count, the page and then the items
and the charges of every rental on it, in `app/infrastructure/rental_list_query.py`.

| Operation | Statements | Locks |
|---|---|---|
| Return | The rental, its items and its charges, the reservation and its lines, the units, then the writes and the read of the answer | The rental, the reservation, the units, in that order |
| Loss | As a return, for one unit | As a return |
| Balance payment | The rental, its items and its charges, the writes and the read | The rental |
| Overdue sweep | One when nothing is due, and three to load a batch | The rentals of the batch |
| A list | Four | None |

**What degrades first as the data grows.** The staff list with no filter. Its
order puts the overdue first and then the newest, which no index holds, so
every rental is sorted to find one page, and the page is found with OFFSET. A
branch, a customer or the overdue filter narrows it first through an index.
At ten times today's hires that is still quick. At a hundred times it wants a
page keyed on when the hire went out, with an index behind it, and the overdue
hires as a list of their own. A return writes one update and one audit event
for every unit, which is linear in the units of one hire and bounded by what
one reservation can carry. The overdue part of the sweep clears one batch a
request, so a backlog of hires gone overdue would read `OPEN` for a while,
which costs a status on a screen and never a late fee, because the fee is
worked out from the dates.

## Damage and quarantine

A unit that comes back damaged leaves availability at once, and whether the
customer is charged for the damage is an explicit decision (FR-20, US-24,
US-38, BR-35 to BR-40). There is no new table and no new column. Revision
`0005` adds two indexes.

**Quarantine at return (BR-35).** `status_on_return` in
`app/domain/quarantine.py` decides from the two grades and the counter's flag.
A unit back in a worse grade than it went out in, or flagged, moves to
`QUARANTINED` instead of `AVAILABLE` in the transaction of its return, so the
availability search stops offering it from that moment (BR-10). Its allocation
is still let go, because the hire is over. Its `damageAssessment` reads
`REQUIRED`, `settlementWaitingOn` reads `DAMAGE_ASSESSMENT` and the deposit is
not settled. Once a damage report names the unit the assessment reads `DONE`.
`damage_assessment_of` is the one rule the read and the settlement both ask.
The schema has no column for the flag, so I keep it where the schema keeps
what the counter says about a unit, at the head of the rental item's notes,
which no client is shown. `was_flagged` reads it back. A column on
`rental_item` would be the durable home for it, and it is a one statement
migration when the schema may change.

**Filing a report.** `POST /api/damage-reports` is `FileDamageReportUseCase`,
for counter staff of the branch that holds the unit and administrators. In one
unit of work it locks the rental of the named rental item first, the way every
change to a rental does, and then the unit. `ensure_may_file` in
`app/domain/damage_filing.py` decides every refusal before anything changes,
the fields first and the standing of the unit and the hire after, and only
then is a reference drawn from `damage_report_reference_seq`, in the form
`TSH-D-26-00031`, so a refused report uses no number. The report is written
`OPEN`, the unit goes to `QUARANTINED` unless it is already out of service, and
the audit trail gains `damage_report.filed`, an `asset.status_changed` when the
unit moved and `rental.damage_assessed` when the report names a hire.

| Refusal | Answer |
|---|---|
| No `chargeableToCustomer`, or one that is not a JSON boolean. There is no default (BR-40). | 422 naming it. |
| An amount to recover missing when the customer is charged on a hire, given when not charged or outside a hire, or not above nothing. | 422 naming `recoveryAmount`. |
| An amount above the replacement value copied onto the booking, less what was already recovered for that unit on that hire (BR-39). The sentence names the most that may be recovered. | 422 naming `recoveryAmount`. |
| An unknown tag, or a rental item that is not a hire of that unit. | 422 naming `assetTag` or `rentalItemId`. |
| A unit out on hire. Its damage is reported once it is back. | 409. |
| A retired unit, through the asset state model. | 409. |
| A unit that waits for the report of its own return, and a report that does not name that rental item. The sentence names the rental. | 409. |
| A chargeable report on a hire whose deposit was already settled. | 409. |
| Counter staff of another branch. | 403. |

The rule about a unit waiting for the report of its own return is mine. The
locator links a quarantined unit to the report screen with no rental item, and
a report filed that way would leave the hire waiting for an assessment that
never comes.

**Recovery and settlement (BR-39, BR-32).** A chargeable report that names a
rental item raises a `DAMAGE_RECOVERY` charge for `recoveryAmount`, a VAT
inclusive amount split by `split_vat_inclusive` the way a late fee is, which
points back at the report through `damage_report_id`. The cap is
`ensure_recovery_within_cap` in `app/domain/damage_recovery.py`. It counts the
recoveries and the deposit kept for the same unit on the same hire, so a lost
unit, already charged its full value, can recover nothing more. Each item of
a `Rental` read by staff carries that `replacementValue`, so the counter sees
the cap before it files. When the
report completes the last assessment and every unit is back,
`settle_when_nothing_waits` settles the deposit in the same unit of work, with
the recovery among what is withheld. A report that is not chargeable raises no
charge and lets the deposit go just the same.

**A report outside a hire.** It names no rental item, raises no charge, takes
no amount and still quarantines the unit. Its `replacementValue` is the
model's own, because there is no booking line, and its `recoveryCharged` is
null, as it is for any report that raised no charge.

**Repair and closing, an administrator alone (BR-37, BR-38, US-38).**
`POST /api/damage-reports/{id}/repair` moves an `OPEN` report to
`UNDER_REPAIR` and its unit with it. `POST /api/damage-reports/{id}/resolution`
closes it. `RESOLVED` needs `actualRepairCost` and puts the unit back to
`AVAILABLE` once no other report of it is open. `WRITTEN_OFF` moves the unit to
`RETIRED`, stamps `retired_on`, keeps the row, and is refused with 409 while a
booking still holds the unit. Each locks the report and then the unit, and the
moves of a report are listed once, in `PERMITTED_REPORT_MOVES`. Counter staff
are answered 403 by both routes.

**The reads.** `GET /api/damage-reports` lists reports at every branch, newest
first, narrowed by `assetTag`, `status` and `branchCode`, and
`GET /api/damage-reports/{id}` reads one by its key or its reference. Both are
query objects in `app/infrastructure/damage_report_query.py`. The recovery
charged is summed through the rental item, so it stands on
`ix_charge_rental_item` rather than on a scan of every charge.

| Operation | Statements | Locks |
|---|---|---|
| File a report | The tag, the rental and its items and charges when an item is named, the unit, the unit's last hire, the reference, the writes, the settlement when it may, the read of the answer | The rental, then the unit |
| Repair or close | The report, the unit, one count or one test of the allocations, the writes and the read | The report, then the unit |
| One report | One | None |
| A list | The branch when named, the count and the page | None |
| One rental | Three, plus the move and a second read the first time it is seen overdue | The rental, only then |

Revision `0005` adds `ix_damage_report_rental_item`, a partial btree on
`damage_report.rental_item_id`, because every read of a rental now asks, for
each unit, whether a report names it, and `ix_damage_report_asset`, a btree on
`damage_report.asset_id`, through which a list by tag, the count of a unit's
open reports and a write off reach the reports of one unit. The question of a
rental read is a correlated EXISTS inside the statement that reads the items,
so a rental read is still three statements.

**What degrades first as the data grows.** The list of reports with no tag. It
is sorted by when a report was filed, which no index holds, so every report
that matches is sorted to find one page, the way the list of rentals is. A few
hundred reports a year make that nothing for a long time. At a hundred times
that it wants an index on `reported_at` and a page keyed on it.

## The schema

Migration `0001` is the baseline. It creates seventeen tables with singular
snake_case names, which are the sixteen domain tables and `rate_limit_counter`.

| Subject area | Tables |
|---|---|
| Identity and access | `branch`, `user_account`, `customer_profile`, `refresh_session` |
| Catalogue and fleet | `category`, `product_model`, `asset` |
| Booking and allocation | `reservation`, `reservation_line`, `asset_allocation` |
| Hire and money | `rental`, `rental_item`, `damage_report`, `charge` |
| Evidence and supporting | `audit_event`, `notification`, `rate_limit_counter` |

The same five subject areas name the modules in `app/infrastructure/models`
and in `alembic/baseline`. The two are kept apart on purpose. The models change
as the application grows. The baseline is a snapshot that imports nothing from
`app`, so an edit to a model can never change what an already released
migration creates. A later change to the schema is a new revision.

The migration is the one authoritative listing of the check constraints, the
exclusion constraint and the indexes. The models declare columns and keys and
do not repeat them.

Revision `0003` adds one index and nothing else,
`ix_customer_profile_phone_digits_trgm`, a trigram index over the digits of
`customer_profile.contact_phone`, which the counter's customer search reads.
It is built inside the migration's transaction, which blocks writes to the
profiles for the moments it takes. A table a hundred times larger would want
`CREATE INDEX CONCURRENTLY` outside a transaction instead.

Revision `0004` adds three indexes and nothing else. `ix_asset_tag_trgm` is a
trigram index on `asset.asset_tag`, which the asset locator matches part of a
tag through. `ix_asset_product_model` is a btree on `asset.product_model_id`,
through which the locator reaches the units of a model whatever their status.
`ix_rental_branch_due_back` is a btree on `rental (branch_id, due_back_on)`,
through which the diary finds the hires due back on a day in the past, which
the partial index on open hires does not hold.

Revision `0005` adds two indexes and nothing else, both on `damage_report`.
`ix_damage_report_rental_item` is a partial btree on `rental_item_id`, which
every read of a rental asks through, and `ix_damage_report_asset` is a btree
on `asset_id`, which the reports of one unit are reached through. The table is
empty when the revision first runs, so building them blocks nothing.

## The seed and the two database roles

`python seed.py` gives a database a fleet worth looking at, so the system has
real data from its first deployment. In one transaction it loads the three
branches, fourteen categories, 120 published product models, 400 physical
units (171 at CBD, 125 at BLV, 104 at SMW), five accounts with verified email
addresses and a profile for each of the two customers, and the worked example
from the design document as a hire that is already closed.

Thirty four units keep the tags the prototype showed. The other 366 are tagged
`TSH-<prefix>-<number>`, numbered upward within each prefix in SKU order and
then branch order, stepping over any number a pinned unit carries, so the same
data always gives the same tags. Stock bought after the first load belongs in
`seed_data/pinned_assets.py` with the tag it was given, because a new product
model can renumber the generated units that sort after it.

Every row is matched on its natural key, and a row that is already there is
left exactly as it is. A second run changes nothing and logs
`seed.nothing_to_do`, and a run against a database in use never resets a
status, a price or a password. Every account the seed creates gets the
password in `SEED_PASSWORD`. Outside development and test the script refuses to
run without it. If `SEED_CUSTOMER_PASSWORD` is set as well, the customer
accounts get that password instead, so a demonstration customer login can be
published without exposing the staff and admin logins. The data lives in
`seed_data` and the loading in `seeding`.

The design document splits database authority between two roles, so the
running application can neither change the schema nor rewrite its audit trail.

| Role | Used by | May do |
|---|---|---|
| `toolshed_migrate` | `alembic upgrade head` | Create objects in this database and in the `public` schema. |
| `toolshed_app` | The running API | Select, insert and update on every table. On `audit_event`, select and insert only. Delete on `rate_limit_counter` alone, where expired windows are removed. |

The owner of the database creates the roles once, before the first migration.
Revision `0002` then gives `toolshed_app` its privileges on the tables.

```bash
DATABASE_OWNER_URL=postgresql://owner:...@host:5432/toolshed APP_ROLE_PASSWORD=... MIGRATE_ROLE_PASSWORD=...   python scripts/provision_roles.py

DATABASE_URL=postgresql+psycopg://toolshed_migrate:...@host:5432/toolshed alembic upgrade head
DATABASE_URL=postgresql+psycopg://toolshed_migrate:...@host:5432/toolshed python seed.py
```

The API is then started with a `DATABASE_URL` that names `toolshed_app`. The
script is safe to run again, which is also how a password is rotated, and it
never logs a password.

A plain local database with one owner needs none of this. If `toolshed_app`
does not exist when revision `0002` runs, the revision logs that it skipped the
grants and the migration still succeeds. To restrict a database migrated that
way, I provision the roles and run `alembic downgrade 0001` and then
`alembic upgrade head`. The downgrade only revokes, so no data is touched.

Any later migration that creates a table or a sequence has to grant on it in
the same revision. A new object inherits no privileges, so a table added
without its grant is one the application cannot read.

## Running it locally

```bash
python -m venv .venv
.venv/Scripts/activate          # PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
cp .env.example .env            # then edit DATABASE_URL

alembic upgrade head
python seed.py
uvicorn app.main:app --reload --port 8000
```

`GET http://localhost:8000/api/health` should report
`{"status": "healthy", "databaseReachable": true, "btreeGistInstalled": true, "revision": "local"}`.

## Endpoints

| Method | Path | Roles admitted |
|---|---|---|
| GET | `/api/health` | Public by declaration, for the uptime check. |
| POST | `/api/auth/login` | Public by declaration, it issues the credentials. |
| POST | `/api/auth/refresh` | The holder of the refresh cookie. |
| POST | `/api/auth/logout` | The holder of the refresh cookie. Always 204. |
| POST | `/api/auth/register` | Public by declaration. Always 202. |
| POST | `/api/auth/email-verification` | Public by declaration, the token is the credential. |
| POST | `/api/auth/email-verification/resend` | Any active account. |
| POST | `/api/auth/password-reset/request` | Public by declaration. Always 202. |
| POST | `/api/auth/password-reset/complete` | Public by declaration, the token is the credential. |
| GET | `/api/me` | Any active account. |
| GET | `/api/me/profile` | A customer. |
| PATCH | `/api/me/profile` | A customer. |
| POST | `/api/reservations` | Any active account. A customer books for themselves, staff name the customer. |
| POST | `/api/reservations/{id}/hold` | Any active account. The owner, an administrator, or counter staff of the branch. |
| POST | `/api/reservations/{id}/confirm` | Any active account, as above. |
| POST | `/api/reservations/{id}/cancellation` | Any active account, as above. |
| POST | `/api/reservations/{id}/no-show` | Counter staff of the collection branch, and administrators. |
| GET | `/api/reservations` | Any active account. A customer sees their own. |
| GET | `/api/reservations/{id}` | Any active account. Somebody else's is a 404 for a customer. |
| GET | `/api/reservations/{id}/checkout` | Counter staff and administrators. |
| POST | `/api/reservations/{id}/checkout` | Counter staff of the collection branch, and administrators. |
| GET | `/api/rentals` | Counter staff and administrators, every branch. |
| GET | `/api/rentals/{id}` | Counter staff and administrators. |
| POST | `/api/rentals/{id}/returns` | Counter staff of the rental's branch, and administrators. |
| POST | `/api/rentals/{id}/items/{itemId}/loss` | Counter staff of the rental's branch, and administrators. |
| POST | `/api/rentals/{id}/balance-payment` | Counter staff of the rental's branch, and administrators. |
| GET | `/api/me/rentals` | A customer. |
| POST | `/api/damage-reports` | Counter staff of the branch that holds the unit, and administrators. |
| GET | `/api/damage-reports` | Counter staff and administrators, every branch. |
| GET | `/api/damage-reports/{id}` | Counter staff and administrators. |
| POST | `/api/damage-reports/{id}/repair` | An administrator. |
| POST | `/api/damage-reports/{id}/resolution` | An administrator. |
| GET | `/api/counter/dashboard` | Counter staff for their own branch, and administrators for the branch they name. |
| GET | `/api/counter/diary` | Counter staff for their own branch, and administrators for the branch they name. |
| GET | `/api/assets/locator` | Counter staff and administrators, every branch. |
| GET | `/api/customers` | Counter staff and administrators. |
| POST | `/api/customers` | Counter staff and administrators. Counter staff register at their own branch. |
| GET | `/api/customers/{id}` | Counter staff and administrators. |
| GET | `/api/branches` | Public by declaration. |
| GET | `/api/catalogue/categories` | Public by declaration. |
| GET | `/api/catalogue/models` | Public by declaration. |
| GET | `/api/catalogue/models/{slug}` | Public by declaration. |
| GET | `/api/catalogue/availability` | Public by declaration. |
| GET | `/api/catalogue/models/{slug}/availability` | Public by declaration. |
| GET | `/api/catalogue/models/{slug}/quote` | Public by declaration. |

Every endpoint added later must declare its policy. The default is deny
(BR-41), the application refuses to start on a route that declares nothing, and
`tests/api/test_route_policies.py` lists the policy expected of every route.

### The session routes

All three are under `/api/auth`, take and return JSON with camelCase names and
answer errors as `application/problem+json`.

| Route | Body | Answers |
|---|---|---|
| `POST /api/auth/login` | `email`, `password` | 200 with `accessToken`, `tokenType` of `Bearer`, `expiresIn` and `user`, and a `Set-Cookie` for the refresh token. 401 `invalid-credentials`. 429 `too-many-attempts` with `Retry-After`. |
| `POST /api/auth/refresh` | none | 200 with the same body and a `Set-Cookie` that replaces the refresh token. 401 `session-expired`, with the cookie cleared. 403 `origin-not-allowed`. |
| `POST /api/auth/logout` | none | 204 with the cookie cleared. 403 `origin-not-allowed`. |

`user` is `id`, `email`, `fullName`, `role`, `branchCode` and `emailVerified`,
and `GET /api/me` returns the same object. `role` is `customer`, `counter` or
`admin`. `branchCode` is null unless the account is counter staff.

### The account routes

| Route | Body | Answers |
|---|---|---|
| `POST /api/auth/register` | `email`, `password`, `fullName`, `phone`, `idDocumentType`, `idDocumentLast4`, `billingAddressLine1`, `billingSuburb`, `billingCity`, `billingPostalCode`, `homeBranchCode`, `acceptsPrivacyNotice` | 202 with `emailDeliverable`. 422 naming the field. 429 `too-many-attempts`. |
| `POST /api/auth/email-verification` | `token` | 204. 400 `verification-link-invalid`. 429. |
| `POST /api/auth/email-verification/resend` | none | 202 with `emailDeliverable`. 401 with no credential. 429. |
| `POST /api/auth/password-reset/request` | `email` | 202 with `emailDeliverable`. 429. |
| `POST /api/auth/password-reset/complete` | `token`, `newPassword` | 204. 400 `reset-link-invalid`. 422 naming `newPassword`. 429. |
| `GET /api/me/profile` | none | 200 with the profile. 404 with no profile. 403 for staff. |
| `PATCH /api/me/profile` | any of the eight editable fields | 200 with the profile. 422 naming the field. 404 with no profile. |

`idDocumentType` is `SA_ID`, `PASSPORT` or `DRIVING_LICENCE`, and
`idDocumentLast4` is exactly four letters or digits. The full document number
is never sent. The profile carries `fullName`, `email`, `emailVerified`,
`phone`, `customerType`, `companyName`, `vatNumber`, `idDocumentType`,
`idDocumentLast4`, the four billing fields, `accountStatus`,
`tradeDiscountPercent` as a string with two decimals, `noShowCount`,
`homeBranchCode` and `memberSince`, which is the day the profile was opened.

### The reservation routes

All six take and return JSON with camelCase names. Money is a string with two
decimals, a date is `YYYY-MM-DD`, and an instant is ISO 8601 with the offset of
Cape Town, for example `2026-10-02T15:30:00+02:00`. `{id}` is the key of the
reservation or its reference.

| Route | Body or query | Answers |
|---|---|---|
| `POST /api/reservations` | `branchCode`, `from`, `to`, `lines` of `modelSlug` and `quantity`, and optionally `customerProfileId` and `notes` | 201 with the reservation as a `DRAFT` and a `Location` header. 422 naming the field. 403 when a customer names a profile, when counter staff book at another branch, or when the customer is on hold. |
| `POST /api/reservations/{id}/hold` | none | 200 with the reservation, now `HELD`. 409 `asset-unavailable` when a line cannot be fully allocated. 409 `state-transition` when it is not a draft. |
| `POST /api/reservations/{id}/confirm` | none | 200 with the reservation, now `CONFIRMED`. 409 `state-transition` when the hold has run out or the move is not permitted. 403 `email-not-verified`. |
| `POST /api/reservations/{id}/cancellation` | `reason`, optional, at most 200 characters | 200 with the reservation, now `CANCELLED`. 409 `state-transition` when it can no longer be cancelled. |
| `GET /api/reservations` | `status`, `page`, `pageSize` from 1 to 50 and 20 by default. Staff may add `customerProfileId` or `branchCode`, and `branch` is still accepted for `branchCode` | 200 with `items`, `page`, `pageSize` and `total`, newest first. A customer's list leaves out abandoned baskets. |
| `GET /api/reservations/{id}` | none | 200 with the reservation. 404 when it does not exist or is not the caller's. |

A reservation carries `id`, `reference`, `status`, `branchCode`, `branchName`,
`from`, `to`, `hireDays`, `lines`, `subtotalExVat`, `discountPercent`,
`vatAmount`, `estimatedTotalIncVat`, `depositTotal`, `holdExpiresAt`,
`confirmedAt`, `cancelledAt`, `cancellationReason`, `canHold`, `canConfirm`,
`canCancel`, `customerName` and `createdAt`. A line carries `modelSlug`,
`modelName`, `quantity`, `dailyRate`, `weeklyRate`, `depositPerUnit`,
`lineSubtotalExVat`, `allocatedCount` and `assetTags`.

`canHold`, `canConfirm` and `canCancel` say what the caller may do right now.
They are worked out on the server from the state of the reservation and from
who is asking, so a screen never repeats the rules of the lifecycle.
`assetTags` is filled for counter staff and administrators and is an empty list
for a customer, who never learns which unit they were given (US-07).

A refused field is named under `errors.fields` by where it travelled and its
name on the wire, for example `body.to` or `body.lines.0.modelSlug`. A value a
rule refused carries a plain sentence. A value the framework refused for its
type carries the framework's own wording, as every request body does. No
sentence names a business rule. The rule goes to the log.

### The counter routes

| Route | Body or query | Answers |
|---|---|---|
| `GET /api/customers` | `q` of 2 to 80 characters, `page`, `pageSize` | 200 with `items` of `CustomerSummary`, `page`, `pageSize` and `total`, best match first. 422 naming `query.q`. |
| `POST /api/customers` | `displayName`, `phone`, `idDocumentType`, `idDocumentLast4`, the four billing fields, `customerType`, `companyName`, `vatNumber`, `branchCode` | 201 with the `CustomerSummary` and a `Location` header. 422 naming the field, and `branchCode` when an administrator names none. 403 `branch-scope` when counter staff name another branch. |
| `GET /api/customers/{id}` | none | 200 with the `CustomerSummary`. 404 when there is no such customer. |
| `GET /api/reservations/{id}/checkout` | none | 200 with the reservation, its customer, its units, `hireTotalIncVat`, `depositTotal`, `canCheckOut`, `refusal` and `rentalId`. 404. |
| `POST /api/reservations/{id}/checkout` | `items` of `allocationId`, `conditionOut`, `accessoriesOut` and `hourMeterOut`, and `agreementSigned` | 201 with the `Rental` and a `Location` header. 200 with the existing rental when it was already checked out. 409 `state-transition` when it is not confirmed or its hire has not started. 403 `branch-scope`. 422 naming the field. |
| `GET /api/rentals/{id}` | none | 200 with the `Rental`. 404 when there is no such rental. |
| `GET /api/rentals` | `branchCode`, `status`, `overdueOnly`, `customerProfileId`, `page`, `pageSize` | 200 with `items` of `Rental`, `page`, `pageSize` and `total`, the overdue first. 422 naming `query.branchCode`. |
| `POST /api/rentals/{id}/returns` | `items` of `rentalItemId`, `conditionIn`, `hourMeterIn`, `accessoriesIn`, `notes` and `flaggedForDamage` | 200 with the `Rental`. 409 `state-transition` for a unit already back. 403 `branch-scope`. 404. 422 naming the field. |
| `POST /api/rentals/{id}/items/{itemId}/loss` | none | 200 with the `Rental`. 409 `state-transition` when the unit is back or not yet more than fourteen days late. 403 `branch-scope`. 404 for a rental or a unit that is not there. |
| `POST /api/rentals/{id}/balance-payment` | `paymentReference`, 1 to 40 characters | 200 with the `Rental`, now `SETTLED`. 409 `state-transition` when nothing is due. 403 `branch-scope`. 404. 422 naming `body.paymentReference`. |
| `GET /api/me/rentals` | `page`, `pageSize` | 200 with the caller's own rentals, newest first, `assetTag` null on every item. 403 for staff. |
| `POST /api/damage-reports` | `assetTag`, `rentalItemId`, `severity`, `description`, `repairEstimate`, `chargeableToCustomer`, `recoveryAmount` | 201 with the `DamageReport` and a `Location` header. 422 naming the field. 409 `state-transition` for a unit on hire, retired or waiting for its return's report, and a charge on a settled hire. 403 `branch-scope`. |
| `GET /api/damage-reports` | `assetTag`, `status`, `branchCode`, `page`, `pageSize` | 200 with `items` of `DamageReport`, `page`, `pageSize` and `total`, newest first. 422 naming `query.branchCode`. |
| `GET /api/damage-reports/{id}` | none | 200 with the `DamageReport`. 404 when there is no such report. |
| `POST /api/damage-reports/{id}/repair` | none | 200 with the `DamageReport`, now `UNDER_REPAIR`. 409 `state-transition` when it is not `OPEN`. 403 for counter staff. 404. |
| `POST /api/damage-reports/{id}/resolution` | `outcome` of `RESOLVED` or `WRITTEN_OFF`, `actualRepairCost`, `resolutionNotes` | 200 with the `DamageReport`. 422 naming `body.actualRepairCost` when a resolution has none. 409 `state-transition` for a closed report, or a write off while a booking holds the unit. 403 for counter staff. 404. |
| `POST /api/reservations/{id}/no-show` | `reason`, 1 to 200 characters | 200 with the reservation, now `NO_SHOW`. 409 `state-transition` when it is not confirmed or its hire has not started. 403 `branch-scope`. 422 naming `body.reason`. |
| `GET /api/counter/dashboard` | `branchCode`, which an administrator must send | 200 with `branchCode`, `branchName`, `date`, `counts` and the three lists. 403 `branch-scope` when counter staff name another branch. 422 naming `query.branchCode`. |
| `GET /api/counter/diary` | `branchCode`, `from` which is today by default, `days` from 1 to 7 and 1 by default | 200 with `branchCode`, `branchName` and one entry of `days` for each day. 403 and 422 as for the dashboard, and 422 naming `query.days` or `query.from`. |
| `GET /api/assets/locator` | `q` of 2 to 80 characters, `page`, `pageSize` | 200 with `items`, `page`, `pageSize` and `total`, in tag order. 422 naming `query.q`. |

`CustomerSummary` carries `id`, `displayName`, `email`, `phone`, `hasLogin`,
`emailVerified`, `customerType`, `companyName`, `idDocumentType`,
`idDocumentLast4`, `billingSuburb`, `billingCity`, `accountStatus`,
`tradeDiscountPercent`, `noShowCount` and `homeBranchCode`. A walk-in has a
null `email` and `hasLogin` false. A `Rental` carries what the contract gives
it, with its `items` and its `charges`, and `{id}` of a rental is its key or
its reference. Each item of a `Rental` also carries `replacementValue`, the
value copied onto its booking line, which is the most a damage report may
recover, so the report screen can show the cap before a report exists. It is
null for a customer, as `assetTag` is. A `DamageReport` carries what the
contract gives it, and `{id}` of a report is its key or its reference too.

### The public catalogue, availability and quote routes

All seven return JSON with camelCase member names. Money is a string with two
decimals, for example `"280.00"`, and never a number. A date is `YYYY-MM-DD`
and a time of day is `HH:MM`.

| Path | Query | Returns |
|---|---|---|
| `/api/branches` | none | `items`, the active branches ordered by name. |
| `/api/catalogue/categories` | none | `items`, the active categories, each parent followed by its children. `modelCount` counts published models and a parent includes its children. |
| `/api/catalogue/models` | `category`, `q`, `sort`, `page`, `pageSize` | `items`, `page`, `pageSize`, `total`, for published models only. |
| `/api/catalogue/models/{slug}` | none | One published model, with `longDescription` and `lateFeePerDay`. 404 for an unknown or unpublished slug. |
| `/api/catalogue/availability` | `from`, `to`, the five above, `branch` | `from`, `to`, `hireDays`, `items`, `page`, `pageSize`, `total`. Each item is a `model` and one `available` boolean for every active branch. |
| `/api/catalogue/models/{slug}/availability` | `from`, `to`, `quantity` | `from`, `to`, `hireDays`, `quantity`, `branches`. A branch is available when at least `quantity` units are free. |
| `/api/catalogue/models/{slug}/quote` | `from`, `to`, `quantity` | What the hire will cost, described below. 404 for an unknown or unpublished slug. |

`category` is a category slug and a parent includes its children. `q` is at
least 2 characters and is matched against the name, the manufacturer and the
model number in any case. `sort` is `name`, `dailyRateAsc` or `dailyRateDesc`.
`page` counts from 1 and `pageSize` is 1 to 50, 24 when left out. `branch` is a
branch code and keeps only the models free at that branch. `quantity` is 1 to
10. `from` and `to` are half open, so `to` is the day the equipment comes back
and is free again.

A refused parameter is a 422 problem document. The type ends in
`request-validation-failure` and `errors.fields` holds one sentence for each
refused field, keyed by where the value came from and its name in the query,
for example `query.to` or `query.pageSize`. The shape is the same whether the
value could not be read or a rule refused it. The rules are that `to` is after
`from`, the period is at most 28 days and within the hire limits of the model
on the single model route, `from` is not in the past and not more than 90 days
ahead, and the category, the branch and the sort order are known.

A sentence in `detail` or under `errors.fields` is put on a customer's screen
as it is written. So it says what to do, for example "The hire has to start
today or later." or "A hire can be at most 28 days.", and it names no business
rule and repeats no raw value (NFR-12). That holds for a value the framework
refused as well. `app/api/field_messages.py` replaces the framework's sentence
for a query parameter with a plain one, chosen by the kind of refusal. The
rule and the values that were tried go to the log instead, on the
`api.request_validation_failed` and `api.domain_error` lines, as `rule`,
`detail` and `refused_as`. `tests/api/test_plain_refusals.py` asks every one
of these routes for every refusal it can give and fails if a sentence contains
`BR-`, `NFR-`, `start=` or `end=`.

The quote route answers what a hire of `quantity` units will cost (FR-05).

```json
{
  "from": "2026-10-09", "to": "2026-10-19", "hireDays": 10, "quantity": 2,
  "perUnit": {
    "dailyRate": "280.00", "weeklyRate": "1120.00",
    "wholeWeeks": 1, "remainderDays": 3,
    "basis": "weekly",
    "amountExVat": "1960.00"
  },
  "subtotalExVat": "3920.00",
  "discountPercent": "0.00",
  "discountAmount": "0.00",
  "vatRate": "15.00",
  "vatAmount": "588.00",
  "totalIncVat": "4508.00",
  "depositPerUnit": "1200.00",
  "depositTotal": "2400.00",
  "lateFeePerDay": "120.00"
}
```

`basis` is `weekly` when the weeks and the days left over came to less than
every day at the daily rate, and `daily` when the daily total was lower or the
same. `vatAmount` is worked out on the subtotal after the discount.
`totalIncVat` leaves the deposit out, because a deposit is held and returned
and not charged. The period and the quantity are held to the same limits as on
the single model availability route, so a quote is never given for a hire that
could not then be booked.

The route applies no trade discount. It is public, so it does not know who is
asking. The dependencies that read an account are the role policies, and a
route that is public and depends on one of them as well is refused at
start-up. Reading the account some other way would step around that check, so
the route does not. `QuoteHire` takes the discount as an input, and the booking
flow, which knows the customer, passes the one on their profile.

The four catalogue routes answer `Cache-Control: public, max-age=60`. The two
availability routes and the quote route answer `no-store`, because the answer
can be wrong a second after it is given. A request that carried a credential
is always answered `no-store`.

`openapi.json` in this directory is the OpenAPI document of the API, kept so
the frontend can generate its types from it. I write it from Python and not by
redirecting standard output, because the application logs to standard output.

```bash
ENVIRONMENT=test python -c "import json, pathlib; from app.main import create_app; pathlib.Path('openapi.json').write_text(json.dumps(create_app().openapi(), indent=2) + '\\n', encoding='utf-8')"
```

`tests/api/test_openapi_document.py` fails when the committed file differs
from what the application generates, and its message carries the command
above.

`/docs`, `/redoc` and `/openapi.json` are served in development and test only.
In staging and production they answer 404.

## Request ids, logs and headers

Every request has an id. A valid UUID sent in `X-Request-ID` is kept, and
anything else is replaced by a new UUID4. The same value comes back in the
`X-Request-ID` response header, as `requestId` in every problem document and
as `request_id` on every log line written while the request was served. To
trace a failure I ask for the `requestId` and search the log for it.

Each request writes one access log line, `http.request_completed`, when its
response is finished.

| Field | Holds |
|---|---|
| `method` | The HTTP method. |
| `route` | The route template, for example `/api/reservations/{reservation_id}`, and `unmatched` when no route matched. Never the requested path. |
| `status` | The status code that was sent. |
| `duration_ms` | How long the request took, in milliseconds. |
| `actor_role` | The stored role of the authenticated caller, or `anonymous`. |
| `outcome` | `success`, `client_error` or `server_error`. |
| `request_id` | The id above. |

The line is written at `INFO`, at `WARNING` for a 4xx and at `ERROR` for a 5xx.

Secrets are removed from every log line before it is written (C-42). The value
of any `extra` key whose name contains `password`, `secret`, `token`,
`authorization`, `cookie`, `api_key` or `database_url` becomes `[REDACTED]`,
and the password in any `scheme://user:password@host` address is replaced the
same way. A harmless key that happens to contain one of those words is redacted
too, so I name such keys differently.

Every response carries the security headers of C-06 to C-12, which are listed
in `app/api/security_headers.py`. `Strict-Transport-Security` is sent in
staging and production only, and `Cache-Control: no-store` whenever the request
carried an `Authorization` header or a cookie.

`GET /api/health` also reports `revision`. Cloud Run sets `K_REVISION` on every
instance, so the field names the revision that answered. Anywhere else it is
`local`.

## The constraint

```sql
ALTER TABLE asset_allocation
ADD CONSTRAINT asset_allocation_no_overlap
EXCLUDE USING gist (
    asset_id WITH =,
    daterange(start_date, end_date, '[)') WITH &&
) WHERE (released_at IS NULL);
```

Periods are half open. A return on the twelfth frees the twelfth. The same rule
is implemented once in the domain, in `BookingPeriod`, and once in the
database, here. The two must never drift apart.

An allocation is active exactly while `released_at` is null. Releasing one
stamps `released_at` and `release_reason` together, which a check constraint
enforces, and the row drops out of the constraint without being deleted.

A violation arrives as SQLSTATE `23P01`. `SqlAssetRepository` matches on the
code and on the constraint name, both read from the driver diagnostics and
never from the error message text, and raises `AllocationConflictError`, which
the API maps to a 409 problem document. An integrity error that is not this
constraint is re-raised unchanged.

## Configuration

Every value comes from the environment. See `.env.example`. Outside
development and test the process refuses to start while `JWT_SECRET` is still
the placeholder or `DATABASE_URL` still points at localhost, because a
deployment that boots on a known secret is a hole nobody notices.

`ENVIRONMENT` is `development`, `test`, `staging` or `production`. Staging is
held to every check production is.

`CORS_ORIGINS` does two jobs. It is the list the CORS middleware allows, and it
is the list the refresh and sign out routes compare the `Origin` header with.
A browser sends `Origin` on a same origin POST, so in a deployment the list has
to hold the public address of the site itself. Without it every refresh from a
browser is answered 403.

`JWT_SECRET` signs the access tokens, and the `kid` and the salt of the
throttle are both derived from it. Changing it refuses every access token
already issued and starts every throttle window again. The refresh sessions are
not affected, so a client refreshes once and carries on.

`LOGIN_ATTEMPTS_PER_EMAIL` and `LOGIN_ATTEMPTS_PER_ADDRESS` are the two sign
in limits, 10 and 30 by default and never below 1. Outside development and
test they can only be lowered. See Throttling above. The seven limits of the
account routes follow the same rules and are listed under Registration and
account security.

`FRONTEND_ORIGIN` is where the links in the account messages point, for
example `https://www.example.co.za`, with no path. Left unset it is the one
origin in `CORS_ORIGINS`, and in development, when that list holds more than
one, it is `http://localhost:5173`. Staging and production refuse to start
when it cannot be worked out, when it is not `https` or when it names this
machine. The deploy script sets the address of the site as `CORS_ORIGINS` on
the service and does not pass `FRONTEND_ORIGIN` itself, so the deployed
services use that fallback today. Passing `FRONTEND_ORIGIN` to the service as
well would make the setting explicit. The start-up log shows the origin in use
as `frontend_origin`.

Three settings control email.

| Variable | Default | Meaning |
|---|---|---|
| `RESEND_API_KEY` | unset | The Resend API key. Unset, blank or the literal `not-configured-yet` means email is off. |
| `EMAIL_FROM` | `Toolshed Hire <onboarding@resend.dev>` | The From header of every email. |
| `EMAIL_ALLOWED_RECIPIENT` | unset | When set, the only address the service will send to. |

With email off the application still starts. It logs one warning,
`notification.email_not_configured`, and every confirmation is recorded as
`FAILED` with the reason that email is not configured in this environment.

`EMAIL_ALLOWED_RECIPIENT` is how the demonstration environment runs without a
verified sending domain. It is enforced inside the adapter, on the server. A
message for any other address is refused before the provider is called, and it
is never redirected to the allowed address, because that would deliver one
customer's booking to somebody else.

The key is never logged and never appears in a receipt or an error message.

`TEST_BUSINESS_TIME`, for example `10:00`, starts the clock of a test process
at that time of day in Cape Town on today's real date, and lets it run on in
real time from there (see The clock). It is honoured only when
`ENVIRONMENT=test`. Development, staging and production refuse to start with
it set, so no deployed service can run on a clock that lies. The start-up log
shows it as `test_business_time`, or `off`.

## Checks

I run these from this directory before I publish a change. The pipeline runs
the same commands.

```bash
ruff check .                     # lint, including S608 and C901 at complexity 10
mypy app                         # strict type check
lint-imports                     # the layer contract
pytest tests -m "not postgres"   # unit, component and API tests, no database
pip-audit                        # known vulnerabilities in the installed packages
```

`lint-imports` reads five contracts from `pyproject.toml`.

1. `app.domain` imports nothing from the other three layers.
2. `app.application` does not import `app.api`.
3. `app.application` does not import `app.infrastructure`. The use cases depend
   on ports, and `app.api` is the composition root that wires the
   implementations in.
4. `app.infrastructure` does not import `app.api`.
5. Neither `app.domain` nor `app.application` imports SQLAlchemy, SQLModel,
   FastAPI, Starlette, pydantic, httpx or psycopg.

The full run needs a real PostgreSQL 16. I start the one described by
`docker-compose.yml` at the repository root, which holds a single disposable
database called `toolshed_test`, and I stop it afterwards.

```bash
docker compose up -d --wait

ENVIRONMENT=test DATABASE_URL=postgresql+psycopg://toolshed:toolshed_local_only@localhost:5432/toolshed_test \
  pytest tests --cov --cov-report=term-missing --cov-report=xml

docker compose stop
```

That run is the only one gated on coverage. It measures `app/domain` and
`app/application` and fails below 70 percent. The run without PostgreSQL
carries no `--cov` flag, so it is never held to the threshold. The password in
the compose file is a local throwaway and the port is bound to 127.0.0.1. I set
`TOOLSHED_DB_PORT` when 5432 is already taken.

## Tests

The suite is split in two by the `postgres` marker, and the pipeline runs the
two halves as separate jobs.

```bash
pytest tests -m "not postgres"   # unit, component and API tests, no database
pytest tests -m postgres         # the schema, the constraint, concurrency, the seed and the roles
```

The tests without the marker come in three kinds. `tests/unit` uses no database
at all, and it runs the use cases against an in memory unit of work and a fake
email gateway, which is what depending on ports makes possible. `tests/component`
runs the real repositories and the real unit of work on in memory SQLite.
`tests/api` goes through HTTP on the same SQLite engine. None of them may open
a network connection, and every test client is given the fake email gateway. The marked tests need a real PostgreSQL 16
reached through `DATABASE_URL`, because the things they prove, `btree_gist`, a
`daterange` exclusion constraint and two genuinely concurrent transactions, have
no SQLite equivalent. With `DATABASE_URL` unset they skip with a message saying
what to set rather than failing.

The marked tests migrate the database to head themselves and truncate every
table between cases, so point them at a database you are willing to lose. They
refuse to run at all unless `ENVIRONMENT` is `development` or `test`.

The reservation lifecycle is tested at every level. `tests/unit` turns the
table of moves into tests, one for each legal move with its guards and its
effects and one for every pairing of a status and a move the table does not
allow, and runs each use case against the in memory unit of work on a clock
that stands still. `tests/api` asks the six routes for every answer and every
refusal they can give, and reads `canHold`, `canConfirm` and `canCancel` for
every status as every kind of caller. `tests/integration` proves what needs a
real database. `test_concurrent_holds.py` sends twenty hold requests for five
units to the real application from twenty threads at once, each on a
connection of its own, and asserts exactly five holds, fifteen 409 answers, no
500 and no unit held twice. `test_hold_expiry_sweep.py` holds one sweep at its
commit until PostgreSQL reports the second one blocked behind it, and
`test_cancellation_transaction.py` shows that a cancellation and its releases
are one commit.

Registration and account security are tested the same way. `tests/unit` holds
the token rules, the lockout window with the clock moved between attempts, the
password rule, the profile rules and every use case against the in memory
stores, with a hasher that counts so the two registration paths can be shown
to do the same work. `tests/api` asks every account route for every answer it
can give and reads the link out of the message the fake gateway was handed.
`tests/integration/test_account_security.py` and `test_account_storage.py`
prove on PostgreSQL that the account and the profile commit together or not at
all, that the token columns hold only hashes, that every step writes its audit
event, and that registration and the lockout work within the grants of the
application role.

Counter bookings and checkout are tested at every level too. `tests/unit`
holds the rules of a checkout, the deposit, the hire charge, the asset state
model, the rental and a walk-in's details with no database at all, and the
views with read models built by hand. `tests/api` asks the checkout routes for
every refusal in `reservation_checkout_refusals.py`, pins the shapes of the
rental, the checkout read and `CustomerSummary`, and counts the statements of
both reads for one unit and for two. On PostgreSQL,
`test_checkout_transaction.py` makes a checkout fail at the audit write, at the
commit and on a quarantined unit and finds nothing kept,
`test_checkout_race.py` posts two checkouts of one reservation at once from two
threads and finds one rental, `test_rental_schema_keys.py` proves the keys
behind them, `test_abandoned_baskets.py` reads the customer's list, and
`test_rental_reads_like_the_worked_example.py` compares a rental opened at the
counter with the seeded worked example.

The counter overview is tested the same way. `tests/unit` holds the moment a
booking becomes a no show, before, at and after closing time and for staff
from the start of the first day, the strike window and the hold, the no show
half of the sweep and the manual move against
the in memory stores, and the dashboard and the diary against fakes of their
ports. `tests/api` pins the shapes of the dashboard, the diary and the locator,
the branch rule for both roles, the limits of the diary and of a search, and
every refusal of the no show route in `reservation_no_show_refusals.py`. On
PostgreSQL, `test_no_show_sweep.py` shows what the sweep keeps and the index it
reads, `test_no_show_races.py` runs two sweeps at once, staged and unstaged,
and two no shows of one customer at once, and `test_counter_reads.py` and
`test_counter_read_indexes.py` read rows built by `tests/support/hire_factories.py`
and count the statements and the indexes.

Returns and settlement are tested the same way. `tests/unit` holds the late
fee policy at the due date, one, two, fourteen and fifteen days, an early
return and a line of two units, the split of an amount that includes VAT and
its rounding, the settlement with nothing owed, the worked example, owed equal
to held, owed above held and a release that is never negative, the guard on a
settled charge, the moves of the rental's status, the refusals of a return and
a loss, and the overdue part of the sweep against the in memory stores.
`test_one_place_for_a_late_fee.py` reads every module to prove no other one
works out a late fee. `tests/api` follows the worked example through the
routes, pins a partial and a last return, the loss, the balance payment and
both lists, and asks every rental route for every refusal in
`rental_return_refusals.py` and `rental_settlement_refusals.py`. On PostgreSQL,
`test_return_transaction.py` makes a return fail at the audit write and at the
commit and finds nothing kept, holds a unit that came back early for days its
old hire still covered, records a loss within the checks of the schema and
proves the repository refuses an edit of a settled charge, and
`test_return_races_and_overdue.py` posts two returns of one unit at once and
runs the overdue sweep a batch at a time.

Damage and quarantine are tested the same way. `tests/unit` holds the
quarantine decision for A to A, A to B, A to C, B to A and the flag alone, the
flag in the notes, the moves of a report's status on their own, what each move
does to the unit, the recovery cap below, at and above the replacement value
and after an earlier recovery, the rules of the chargeable decision, and a
hire taken back a grade worse whose settlement waits and then resumes with the
recovery withheld. `tests/api` follows the whole path through HTTP in
`test_damage_journey.py`, files, reads, repairs and closes reports, and asks
every route for every refusal in `test_damage_report_refusals.py` and
`test_damage_close_refusals.py`. `test_rental_detail_status.py` reads a rental
past its due date as `OVERDUE` with no list read first. On PostgreSQL,
`test_damage_and_quarantine.py` proves the search never offers a quarantined
unit and offers it again once its report is resolved, that the report, its
charge and the settlement are one transaction, that a write off keeps the row
and its history, and that the two reads of revision `0005` stand on its
indexes.

The role tests need no setup. They create `toolshed_app` and `toolshed_migrate`
through `scripts/provision_roles.py`, using the connection in `DATABASE_URL` as
the owner, and apply the grants through the function revision `0002` calls. The
passwords they set are throwaway values in `tests/support/roles.py`. Roles
belong to the cluster and not to one database, so the two roles stay behind
after the run.

`tests/integration/test_schema_baseline.py` runs before every other test. It
reads the PostgreSQL catalogue and asserts that the three extensions, the
seventeen tables, the seventeen enumerated types, the exclusion constraint with
its exact definition and the partial indexes all exist. Every other integration
test assumes that schema, so a broken migration is reported once at the top
instead of as a page of unrelated failures. The order is set by the collection
hook in `tests/integration/conftest.py`, which needs no plugin.

### The postgres suite and your seed data cannot share a database

`pytest -m postgres` truncates every table in the schema before and after each
test case. It is not selective, and it does not restore anything afterwards. If
`DATABASE_URL` points at the database you ran `python seed.py` against, the
branches, the catalogue, the assets and the seeded accounts are gone the moment
the suite runs, and the next sign in from the running application fails with
credentials that were correct five minutes earlier. That has already happened
twice. It is not a bug in the tests. Emptying the tables is what makes a
concurrency test repeatable.

Use two databases. One holds seed data and serves the application, the other is
disposable and belongs to the suite.

```bash
# The seeded one, which serves the running application.
docker run --name tsh-pg -e POSTGRES_USER=toolshed -e POSTGRES_PASSWORD=toolshed \
  -e POSTGRES_DB=toolshed -p 5432:5432 -d postgres:16

# The disposable one, from docker-compose.yml at the repository root. I move it
# to 5433 here because the seeded database already holds 5432.
TOOLSHED_DB_PORT=5433 docker compose up -d --wait

# The suite. Note the port and the database name, and note that it is not the
# seeded one.
ENVIRONMENT=test DATABASE_URL=postgresql+psycopg://toolshed:toolshed_local_only@localhost:5433/toolshed_test \
  pytest tests -m postgres
```

If the seed does disappear, `python seed.py` puts it back. The script is
idempotent and matches on natural keys, so running it again costs nothing.
