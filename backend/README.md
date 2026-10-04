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
12. The owner sees who did what in the audit log and every confirmation in the
   notification log, sends a failed confirmation again without changing the
   failure, waives, reverses or adjusts a charge without editing a settled
   row, and releases a unit of a booking by hand, after which the booking
   cannot be collected until it is given a replacement.
13. The owner keeps the categories and the product models once for all three
   branches, sets each rate, deposit, late fee and replacement value, and
   publishes or hides a model. A rate raised from R280 to R310 reaches the next
   quote and booking, while a booking already made, its lines and the rental
   checked out from it stay at R280.
14. Every physical unit is in a register the owner can search by tag, serial
   number or model name. A unit is registered at INTAKE with a tag that never
   changes, moves through its lifecycle by hand along the moves the asset state
   model permits, and is never retired while a booking holds it. A retired
   unit keeps its row, its history and its figures in the report, and is never
   offered for hire again.

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
| `app/api` | API | Routers, dependencies, middleware, problem responses. `deps.py` is the composition root, `catalogue_deps.py` is its read side half, `identity_deps.py` wires the session use cases, `account_deps.py` wires registration, the two account links and the profile, `pricing_deps.py` chooses the pricing policy, `booking_deps.py` wires the reservation use cases, `customer_deps.py` wires the counter's customer lookup and the walk-in, `hire_deps.py` wires checkout and the rental read, `damage_deps.py` wires the damage reports, `counter_deps.py` wires the dashboard, the diary and the asset locator, `report_deps.py` wires the utilisation report and the admin dashboard, `admin_deps.py` wires the two logs, the re-send, the charge corrections and the force release, `admin_catalogue_deps.py` wires the categories and product models of the admin catalogue, `admin_asset_deps.py` wires the reads and writes of the asset register, and `sweep_deps.py` wires the sweep that lapses expired holds and marks no shows. `access_policy.py` is the deny by default check. `field_messages.py` holds the sentences shown for a query parameter the framework refused. |
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

The design document describes eight modules. All eight have code now, and each
keeps the same name in every layer it appears in.

| Module | Domain | Application | Infrastructure |
|---|---|---|---|
| `identity` | `Actor`, `Branch`, `CustomerProfile`, `Account`, `RefreshSession`, `PendingToken`, `NewCustomer`, `CustomerDetails`, `WalkInCustomer` | `BranchRepository`, `CustomerRepository`, `BranchDirectory`, `CustomerDirectory`, `AccountRepository`, `SessionRepository`, `PasswordHasher`, `SignInUseCase`, `RefreshSessionUseCase`, `SignOutUseCase`, `RegisterCustomerUseCase`, `VerifyEmailUseCase`, `ResendVerificationUseCase`, `RequestPasswordResetUseCase`, `CompletePasswordResetUseCase`, `ReadProfileUseCase`, `UpdateProfileUseCase`, `LookUpCustomers`, `RegisterWalkInUseCase`, `AccountMailer` | `SqlBranchRepository`, `SqlCustomerRepository`, `SqlBranchDirectory`, `SqlCustomerDirectory`, `SqlAccountRepository`, `SqlSessionRepository`, `BcryptPasswordHasher` |
| `hire` | `Rental`, `RentalItem`, `Charge`, `check_out`, the asset state model in `asset_lifecycle`, `DamageReport`, the quarantine rule in `quarantine`, `file_damage_report`, the corrections in `charge_corrections` and their rework in `resettlement` | `RentalRepository`, `CheckoutRentalUseCase`, `ReadRentals`, `CounterOverviewQuery`, `ReadCounterOverview`, `DamageReportRepository`, `FileDamageReportUseCase`, `SendForRepairUseCase`, `CloseDamageReportUseCase`, `ReadDamageReports`, `WaiveChargeUseCase`, `ReverseChargeUseCase`, `AdjustRentalUseCase` | `SqlRentalRepository`, `SqlRentalReads`, `SqlCheckoutReads`, `SqlCounterOverview`, `SqlDamageReportRepository`, `SqlDamageReportReads` |
| `catalogue` | `ProductModel`, `Asset`, the forms of a code and a slug in `catalogue_forms`, `CategoryTerms` and `CatalogueCategory` with the nesting rule in `category_rules`, `ModelTerms` and `CatalogueEntry` with the money and hire day rules in `catalogue_entry_rules`, `RegisteredUnit` and `UnitDetails` with the rules of a tag and its paperwork in `asset_register`, the moves by hand in `asset_transitions` | `ProductModelRepository`, `CatalogueQuery`, `BrowseCatalogue`, `AssetLocatorQuery`, `LocateAssets`, `CategoryRepository`, `CatalogueEntryRepository`, `AdminCatalogueQuery`, `ReadAdminCatalogue`, `CreateCategoryUseCase`, `EditCategoryUseCase`, `CreateModelUseCase`, `EditModelUseCase`, `PublishModelUseCase`, `AssetRegisterRepository`, `AssetRegisterQuery`, `ReadAssetRegister`, `RegisterUnitUseCase`, `EditUnitUseCase`, `MoveUnitUseCase` | `SqlProductModelRepository`, `SqlCatalogueQuery`, `SqlAssetLocator`, `SqlCategoryRepository`, `SqlCatalogueEntryRepository`, `SqlAdminCatalogue`, `SqlAssetRegisterRepository`, `SqlAssetRegister` |
| `availability` | `AssetAllocation` | `AssetRepository`, `allocate_assets`, `AvailabilityQuery`, `SearchAvailability` | `SqlAssetRepository`, `SearchAvailabilityQuery` |
| `booking` | `Reservation`, `ReservationLine`, `ReservationState` and its eight states, the no show rules in `no_show`, the force release and the top up in `reallocation` | `ReservationRepository`, `CreateReservationUseCase`, `HoldReservationUseCase`, `ConfirmReservationUseCase`, `CancelReservationUseCase`, `MarkNoShowUseCase`, `ExpireHoldsAndNoShowsUseCase`, `ReadReservations`, `ForceReleaseUseCase`, `ReallocateUseCase` | `SqlReservationRepository`, `SqlReservationReads` |
| `notification` | `Notification`, `EmailMessage` | `NotificationOutbox`, `NotificationGateway`, `NotificationDispatcher`, `NotificationLogQuery`, `ReadNotificationLog`, `ResendNotificationUseCase` | `SqlNotificationOutbox`, `ResendEmailAdapter`, `FakeEmailGateway`, `SqlNotificationLog` |
| `money` | `Money`, `PricingPolicy`, `StandardPricingPolicy`, `FixedRatePricingPolicy`, `LineSnapshot`, `HireQuote`, `HireTotals` | `QuoteHire` | none yet, a quote writes nothing |
| `reporting` | The day counting in `report_days` and `unit_days`, `utilisation_percent`, `Contribution`, `shares_of_hire_charge` | `FleetReportQuery`, `AdminDashboardQuery`, `FleetFigures`, `ReadUtilisationReport`, `ReadAdminDashboard` | `SqlFleetReport`, `SqlAdminDashboard` |

The audit trail belongs to no module, because every module writes to
it, so it has a file of its own in each layer. Its read is a port of its own,
`AuditEventQuery` in `app/application/audit_reads.py` behind `ReadAuditLog`,
with `SqlAuditEventReads` in `app/infrastructure/audit_query.py`, so nothing
that writes the log can read it and nothing that reads it can write it. The throttle in
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
`ConfirmReservationUseCase` is the one place that queues one for a booking.
`ResendNotificationUseCase` queues a new row when an administrator sends a
failed one again, through the same outbox and the same dispatcher. Creating a
draft and holding it write none, so nobody is sent a confirmation of a hold
they never confirmed.

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

- `StandardPricingPolicy` is the only class that multiplies a rate by a
  number of days. `quote` prices a hire, and `week_at_the_daily_rate` tells
  the admin catalogue what seven days at a daily rate come to, which is the
  most a weekly rate may be. `tests/unit/test_one_place_for_a_price.py` parses
  every module of `app` to keep it so.
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
`StateTransitionError`. Checkout moves every unit to `ON_HIRE` through it, and
an administrator's move by hand goes through it as well, with the guards of
`app/domain/asset_transitions.py` on top.

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

The charge corrections, the re-send, the force release, the five writes of
the admin catalogue and the three writes of the asset register depend on
`FreshAdminUser` from
`app/api/identity_deps.py`, and user and role management will when it is
added. It reads the account again under a shared row lock, so
the role that is checked is the role that holds until the action commits.

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
accessories, the notes, the counter's damage flag and the time, asks the late
fee policy for the days
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

**A settled charge is never edited (BR-24).** `Charge.settled` and the waiver
of an administrator are the only two ways a charge moves on, and both ask
`Charge.ensure_may_change` first, which refuses a charge that is no longer
`PENDING`. The repository writes a charge's status only from `PENDING` to
`SETTLED` or `WAIVED`, and refuses to write over a stored charge that is
settled, waived or reversed, so no path in the application edits one. A
correction of a settled charge is a new charge, described under Admin
operations.

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
US-38, BR-35 to BR-40). There is no new table. Revision `0005` adds two
indexes and revision `0006` adds one column, `rental_item.flagged_for_damage`.

**Quarantine at return (BR-35).** `status_on_return` in
`app/domain/quarantine.py` decides from the two grades and the counter's flag.
A unit back in a worse grade than it went out in, or flagged, moves to
`QUARANTINED` instead of `AVAILABLE` in the transaction of its return, so the
availability search stops offering it from that moment (BR-10). Its allocation
is still let go, because the hire is over. Its `damageAssessment` reads
`REQUIRED`, `settlementWaitingOn` reads `DAMAGE_ASSESSMENT` and the deposit is
not settled. Once a damage report names the unit the assessment reads `DONE`.
`damage_assessment_of` is the one rule the read and the settlement both ask.
The return stores the flag in `rental_item.flagged_for_damage`, and the read
of a rental, the settlement and the check on a unit's last hire when a report
is filed all read it from there. The notes are stored as the counter wrote
them, trimmed of surrounding space, and nothing is ever decided from them. The
design document lists no column for the flag. I added one on purpose, because
the only other place the schema offers is the free text of the notes, and the
deposit should not depend on matching words in free text. Revision `0006` says
the same.

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

## The utilisation report and the admin dashboard

The owner can see which equipment earns its keep, for any period, per unit,
model, category and branch, and can take it away as CSV (FR-24, US-33, US-34,
NFR-04, C-32). The admin dashboard shows the business across every branch
today (SC-19). There is no new table. Revision `0007` adds five indexes.

**The two definitions.** They are written once, in
`app/application/reporting/definitions.py`. Every page of the report carries
them, the first line of the CSV repeats them, and they read as follows.

- Utilisation, per asset, for a period. The days the asset was on an active
  allocation within the period, divided by the days it was in the fleet and
  serviceable within the period. Days quarantined, under repair, lost or
  retired are left out of the denominator. Days are half open, [from, to).
- Gross contribution, per asset, for a period. Hire revenue excluding VAT
  attributed to that asset, plus late fees and damage recovery charged on it
  (excluding VAT), less the actual repair costs recorded against it. It
  excludes acquisition cost, depreciation, finance, staff and premises costs
  and all overheads. It is labelled gross contribution everywhere, never
  profit.

**One module for each rule.** Each piece of the arithmetic is a pure function
in the domain with no database, and nothing else works it out.

| Rule | Module |
|---|---|
| The overlap, the union and the difference of half open spans of days | `app/domain/report_days.py` |
| The serviceable days and the days on hire of one unit | `app/domain/unit_days.py` |
| Utilisation as a percentage, two decimals, half up, None with no serviceable day | `app/domain/utilisation.py` |
| The share of a hire charge raised on a whole hire | `app/domain/policies/hire_charge_share.py` |
| Gross contribution and the sum of its parts | `app/domain/contribution.py` |

The share scales an amount, so it uses `Money.in_proportion`, which is new. It
multiplies before it divides, so an exact share such as R212.625 stays exact
until it is rounded half up to R212.63. Every method that scales an amount is
called only from the policies and the VAT module, and
`tests/unit/test_one_place_for_a_price.py` now holds this one to that as well,
which is why the share lives among the policies.

**How the out of service spans are built.** Every day is a business day in
Cape Town, and an instant becomes the day it falls on there. A unit is in the
fleet from `acquired_on` up to `retired_on` when that is set. Within that it is
out of service on every day any of these says so.

1. A damage report, in any status, runs from the day it was reported up to the
   day it was resolved, or on to the end of the period while it is open.
2. A lost unit, which is a rental item closed with no condition, is out from
   the day the loss was recorded up to the day of the next recorded change of
   the unit's status, or on to the end of the period.
3. The recorded changes of status are the `asset.status_changed` audit events
   that checkout, a return, a loss and every move of a damage report write.
   After a change the unit holds the status that change gave it, and before
   its first change it holds the status that change moved it from. The last
   change before the period and the first after it are read too, so a unit
   already quarantined when the period began is out from its first day. This
   is what makes a unit quarantined at its return out of service from that
   day and not only from the day its report is filed. A day in INTAKE,
   QUARANTINED, UNDER_REPAIR, LOST or RETIRED is out of service.
4. A unit whose status has never been recorded as changing holds its present
   status since it was acquired, when that is INTAKE, QUARANTINED or
   UNDER_REPAIR. So an asset still at INTAKE is never serviceable. A present
   status of LOST or RETIRED is never stretched back that way, because each
   carries a date of its own.

The spans of a unit are joined into one union before anything is counted, so
a day a quarantine and a report both name comes off once.

**What that misses.** First, a status set without an audit event, which only
the seed does. Its quarantined and under repair units have no history, so they
are out of service on every day of any period, including one long before they
were damaged. Second, a day is counted whole. A unit quarantined at four in
the afternoon is out of service all that day, one back on the shelf at nine in
the morning is serviceable all that day, and a move and its undoing on the
same day take no day off. Third, a unit moved out of service and back with no
event for either move would count as serviceable throughout. Every route that
moves a unit writes its event in the same transaction (BR-49), so that can
only come from rows written outside the application. Fourth, damage nobody has
reported yet does not exist for the report. A unit sitting damaged on the
shelf counts as serviceable until its report or its change of status.

**Days on hire.** A rental item is on hire from the day it went out up to the
day it came back, or up to tomorrow while it is still out, and always for at
least the day it went out, which is how the prototype counts a hire collected
today. A booking that is confirmed, or held by a hold that has not run out,
and not yet collected counts its own dates. An allocation released without
going out counts nothing. The spans of a unit are joined, so a unit that ran
late into a booking already made for it is counted once, and only a day the
unit was serviceable counts, so utilisation never passes a hundred percent.
The one case that changes today is a booking that still holds a unit put into
quarantine, whose booked days are left out until the unit is back.

**Money.** Everything excludes VAT. A charge counts in the period its business
day of `raised_at` falls in. A HIRE, LATE_FEE or DAMAGE_RECOVERY charge with a
rental item belongs to that unit. The DEPOSIT_FORFEIT of a lost unit counts as
damage recovery, because with the recovery it makes up the replacement value
the customer paid, which is how `app/domain/damage_recovery.py` already counts
what was recovered for a unit. A HIRE charge raised on a whole hire is shared
between its units. Each unit weighs the amount of its booking line divided by
the units the line books, its share is the charge in that proportion rounded
half up to the cent, and the last unit, in line order and then tag order,
takes whatever the rounding left, so the shares add up to the charge. A waived
charge counts nothing. A reversal is a negative row of the same type, so it
nets off. Deposit movements, ADJUSTMENT and CLEANING are no part of the
definition and are left out. Repair costs are the `actual_repair_cost` of the
reports resolved within the period, against their unit, whatever the outcome.

**Grouping and paging.** A line for a model, a category or a branch adds up
the day counts and the four parts of its units and works its utilisation and
gross contribution out from the sums, so it is never an average of
percentages. Lines are ranked by gross contribution, highest first, and then
by key. The totals are over every line. A unit is in the report when it was in
the fleet during the period, or when money was charged or a repair cost was
recorded on it within the period after it had left, so the totals keep every
rand of the period. A category includes its children, active or not. A unit's
share of a whole hire is the same whatever the report is narrowed to, because
every unit of such a hire is read to weigh it.

| Route | Query | Answers |
|---|---|---|
| `GET /api/admin/reports/utilisation` | `from` and `to` required, `groupBy` of `asset`, `model`, `category` or `branch`, `branchCode`, `categorySlug`, `page`, `pageSize` from 1 to 100 and 20 by default | 200 with `from`, `to`, `groupBy`, `definitions`, `totals`, `items`, `page`, `pageSize` and `total`. 422 naming `query.from`, `query.to`, `query.groupBy`, `query.page`, `query.pageSize`, `query.branchCode` or `query.categorySlug`. 403 for anybody but an administrator. |
| `GET /api/admin/reports/utilisation.csv` | the same but the page | 200, `text/csv; charset=utf-8`, an attachment named `toolshed-gross-contribution-<groupBy>-<from>-<to>.csv`. The same refusals as problem documents. |
| `GET /api/admin/dashboard` | none | 200 with `date`, `branches`, `totals`, `monthToDate`, `openDamageReports`, `customersOnHold` and `failedNotifications`. 403 for anybody but an administrator. |

`to` has to be after `from` and at most 366 days later. A line carries `key`,
`label`, `branchCode`, `categoryName`, `modelName`, `assetTag`, `status` and
the nine figures. `assetTag` and `status` are set on a line for a unit,
`branchCode` on a line for a unit or a branch, `categoryName` on a line for a
unit, a model or a category and `modelName` on a line for a unit or a model.
`utilisationPercent` is null when there was no serviceable day.

**The CSV.** It is worked out before the response starts, so a refusal is
still a problem document, and then written a line at a time by a generator.
The first line is a comment cell that says these are gross contribution
figures and not profit, names the period and repeats both definitions. The
second names the columns of the screen. A line for a unit begins with its tag,
model, category, branch and status, a line for a model with its model and
category, a line for a category with its category and a line for a branch with
its code and name, and every line ends with the nine figures, money with two
decimals and no currency sign. Every cell that begins with `=`, `+`, `-`, `@`,
a tab or a carriage return is written with a single quote in front (C-32).
The one exception is a cell that is a plain decimal number, such as a negative
gross contribution of `-180.00`, which no spreadsheet can read as a formula and
which the owner needs to add up, so it is written as it is. `-1+2` is still
escaped. `escaped_cell` in `app/api/csv_cells.py` is the rule and has tests of
its own.

**The admin dashboard.** For each trading branch it counts the collections
due, the returns due today and the overdue hires with the very conditions the
counter's dashboard uses, `due_for_collection` and `still_out`, so the two can
never disagree, and the units on hire, in quarantine, under repair and on the
shelf. The totals add the branches up. `monthToDate` runs from the first of the
month up to tomorrow, so today counts in full, and is worked out by the same
`FleetFigures` as the report. The three counts that wait for an administrator
are the reports open or under repair, the customers on hold and the
notifications that failed.

**The sweep runs first.** Both the report and the dashboard run it before they
read anything. The contract asks it of the dashboard, and I run it before the
report as well, because the report counts the days of bookings not yet
collected, and a booking nobody collected or a hold that ran out would
otherwise count days nobody has booked. The report's statement also leaves out
a hold whose time has run out, so a backlog the sweep has not reached yet
changes nothing.

| Read | Statements | Indexes |
|---|---|---|
| Report and CSV | 3, which are the units in scope with their money of the period, every dated fact about them as one `UNION ALL`, and the units of every hire charge on a whole hire. 4 when a category is named, which is checked first. The route adds the account, the branch when one is named and the sweep, which is 3 when nothing is due | `ix_charge_raised_at`, `ix_damage_report_resolved_at`, `ix_audit_event_asset_status`, `ix_rental_item_returned_at`, `ix_rental_item_lost`, `ix_reservation_confirmed_start`, `ix_reservation_hold_expiry`, `ix_audit_event_occurred_at`, `ix_asset_allocation_line`, `ix_rental_item_rental`, `ix_asset_branch_status` with a branch, and the primary keys |
| Dashboard | 2, every branch in one and the three counts in the other, and the 3 of the report for the month. The route adds the account and the sweep | `ix_reservation_confirmed_start`, `ix_rental_open_due_back`, `ix_asset_branch_status`, `ix_notification_failed` |

`tests/integration/test_report_reads.py` counts the statements with the
worked dataset and again with twenty more units hired, and asks the planner to
prove each condition of a period uses the index revision `0007` built for it.

**What degrades first as the data grows.** The report reads every unit in
scope and every dated fact of the period into memory on each request, works
the days out in Python and then groups, ranks and pages there. That is linear
in the units and in the hires, reports and changes of the period. At four
hundred units it is a few thousand rows and a few milliseconds. At a hundred
times the fleet, forty thousand units, one request would hold a few hundred
thousand rows and take seconds, and every page of the screen and every
dashboard would pay for the whole report again. That is what degrades first.
The way out is into PostgreSQL in two steps. First the day counting, which
`daterange` and `datemultirange` can do in one statement, `range_agg` for the
union of a unit's spans, `-` to take the out of service days away and `*` to
keep the days on hire that were serviceable, with the length of each range
summed, so the statement returns finished figures and the grouping, the
ranking and the page become `GROUP BY`, `ORDER BY` and a keyed page. Second, at
that size, a table of each unit's figures for each day, written as hires,
returns, reports and charges happen, so a report of any period is a sum over
an index. The share of a whole hire stays the policy in the domain and is
written into that table when the charge is raised. After the report come the
two counts of the dashboard that stand on no index, the open damage reports
and the customers on hold, a few hundred and a few thousand rows today, which
would want partial indexes. The audit log grows fastest of all, and revision
`0007` keeps what the report reads of it to two short index lookups a unit and
the changes of the period.

## Admin operations

The owner sees who did what, sends a failed confirmation again, corrects the
money of a hire without editing anything that was settled, and releases a
unit of a booking by hand (FR-26, FR-27, US-28, US-32, US-36, BR-24, BR-25,
BR-49, BR-50). There is no new table and no new column. Revision `0008` adds
four indexes. Every route under `/api/admin/` is for an administrator alone,
and every write reads the account again under a row lock (`FreshAdminUser`).

**The audit log.** `GET /api/admin/audit-events` is `ReadAuditLog` over
`SqlAuditEventReads`. It lists events newest first, by `occurred_at` and then
by the event's number, narrowed by `entityType`, `entityId`, `action`,
`actorUserId` and a span of business days, `from` and `to`, both included, so
a search from a day to the same day finds everything that happened on it. A
`to` before `from` is a 422 naming `query.to`. Each event carries the key, the
name and the role of the account that acted, the role as it was then, and an
event the sweep wrote carries null for all three. `beforeState` and
`afterState` are the fields the change named, and an empty object when it
named none. There is no write path, and the role the application connects as
may insert into `audit_event` and read it and nothing else, which
`tests/integration/test_application_role.py` proves for an update and a delete
of one event as well as of the whole table.

| Filter | Index |
|---|---|
| `entityType` and `entityId` | `ix_audit_event_entity`, of the baseline |
| `entityType` alone | `ix_audit_event_entity`, its leading column |
| `entityId` alone | `ix_audit_event_entity_id`, revision 0008 |
| `action` | `ix_audit_event_action`, revision 0008, partial on every action but `asset.status_changed` |
| `action` of `asset.status_changed` | `ix_audit_event_occurred_at`, read backwards |
| `actorUserId` | `ix_audit_event_actor`, revision 0008, partial on an event with an actor |
| `from` and `to` | `ix_audit_event_occurred_at`, of the baseline |
| none | `ix_audit_event_occurred_at`, read backwards |

**The notification log and the re-send.** `GET /api/admin/notifications` is
`ReadNotificationLog` over `SqlNotificationLog`, every booking confirmation
newest first by `queued_at`, narrowed by `status`. A status is written into
the statement as the literal it is stored as, so the failed sends are read
through the partial index `ix_notification_failed` and the rest through
`ix_notification_queued_at`. `POST /api/admin/notifications/{id}/resend` is
`ResendNotificationUseCase`. A notification that has not failed is a 409. For
one that failed it writes a new row for the same booking, address and subject
through the outbox a confirmation uses, with the audit event
`notification.resent` in the same transaction, and after the commit the
dispatcher sends it the way it sends a confirmation. So the email gateway
decides as it always does, and `EMAIL_ALLOWED_RECIPIENT` still applies. The
answer is 201 with the new notification as the log shows it once the
dispatch has recorded what became of it. The failed row is never changed, so
the failure and the re-send are both in the log. The table has nowhere to
store `resendOf`, so the log reads it from the after state of that audit
event, through a correlated subquery that is one probe of
`ix_audit_event_entity` for each row of the page. A failed row that was sent
again still counts among `failedNotifications` on the admin dashboard, because
it is still a failure that happened.

**Correcting a charge.** The three corrections are use cases of the hire
module, and their rules are in `app/domain/charge_corrections.py`. Each takes
a reason of 5 to 200 characters, kept on the charge in `waiver_reason` and
written to the audit event with the administrator (BR-25), and answers 200
with the `Rental`. A waiver needs a `PENDING` charge and moves it to `WAIVED`
through `Charge.ensure_may_change`, the guard a settlement goes through. A
reversal needs a `SETTLED` charge that is not a deposit movement, is not itself
a reversal and has not been reversed, and writes a new charge of the same type
with every amount negated, `reverses_charge_id` set to the original and the
reason. The original row is never touched, so it stays `SETTLED` and the
status `REVERSED` is never written. An adjustment is a new `ADJUSTMENT` charge
for an amount that includes VAT, positive or negative and never nothing, split
by `split_vat_inclusive` the way a late fee is, so R150.00 is R130.43 plus
R19.57. A reversal and an adjustment are raised `PENDING`, a debit owed like a
late fee or a credit the customer is owed. The rental's charges carry
`reversesChargeId` and `reason`.

After each correction the deposit, the balance and the status are worked out
again through the settlement. Before the deposit is settled nothing more
happens, because `settle_deposit` counts every charge pending at that moment,
credits included, and a credit larger than everything owed and the deposit
together is paid back by settling the credit itself. Once the deposit is
settled, `rework_settlement` in `app/domain/resettlement.py` runs
`deposit_settlement_of` again over the part of the deposit still paying for
charges not yet settled, which is what is pending less what is due. Nothing
already paid or given back is taken back. What that part no longer needs is
released as a new `DEPOSIT_RELEASE`, what it cannot cover is the balance due,
and the rework writes `rental.settlement_reworked`.

What this does to a rental that is already `SETTLED` is exact. A correction
that gives money back, a reversal or a negative adjustment, leaves it
`SETTLED` with `settledAt` as it was, and the credit is settled at once with a
simulated reference, which is the refund. A settled rental is never edited and
a later correction is a reversing charge (BR-53), so a positive adjustment of
a `SETTLED` rental is refused with 409 and changes nothing, and money found
owed afterwards is a matter for the office and not for the rental. A positive
adjustment of a rental not yet settled is owed like a late fee. A rental
waiting on a balance is `SETTLED` the moment a correction leaves
nothing due, with what of the deposit was paying for the waived charge
released. The worked example, reversed, keeps R240.00 withheld and R960.00
released and adds a settled charge of minus R240.00.

**The force release and the reallocation.**
`POST /api/admin/allocations/{id}/release` is `ForceReleaseUseCase`. It finds
the allocation through the asset repository, locks the booking that holds it,
lets it go with the reason `REALLOCATED` through `force_release` in
`app/domain/reallocation.py`, writes the release through the same repository
and records `reservation.unit_released` with the unit's tag, the reason and how
many units the booking is now short of. An allocation already released, or a
unit out on hire on its booking, is a 409. A unit on hire with another
customer is exactly the case the release is for, so that is not refused. The
answer is the `Reservation`, which now holds one unit fewer than it asks for.
A booking short of a unit cannot be confirmed (BR-08) or collected. The
checkout read carries `unitsShort`, its `refusal` says how many units are
missing and `canCheckOut` is false, and the checkout answers 409 with the same
sentence. `POST /api/reservations/{id}/reallocation` is `ReallocateUseCase`,
for counter staff of the collection branch and administrators. It runs the
sweep, refuses a booking that is neither on hold nor confirmed, and tops up
every short line through `RepositoryAllocator`, the allocator a hold uses, so
the units come from `lock_allocatable` at the collection branch, the exclusion
constraint has the last word and a conflict is a 409 naming the model and the
dates. It is all or nothing, and a booking short of nothing is answered as it
stands with nothing written.

| Route | Body or query | Answers |
|---|---|---|
| `GET /api/admin/audit-events` | `entityType`, `entityId`, `action`, `actorUserId`, `from`, `to`, `page`, `pageSize` | 200 with `items` of `AuditEventView`, `page`, `pageSize` and `total`. 422 naming the parameter. |
| `GET /api/admin/notifications` | `status`, `page`, `pageSize` | 200 with `items` of `NotificationView`. 422 naming the parameter. |
| `POST /api/admin/notifications/{id}/resend` | none | 201 with the new `NotificationView`. 404. 409 `state-transition` when it has not failed. |
| `POST /api/admin/charges/{id}/waiver` | `reason` | 200 with the `Rental`. 404. 409 `state-transition` when the charge is not pending. 422 naming `body.reason`. |
| `POST /api/admin/charges/{id}/reversal` | `reason` | 200 with the `Rental`. 404. 409 `state-transition` when it is not settled, is a deposit movement, is a reversal or was reversed. 422. |
| `POST /api/admin/rentals/{id}/adjustments` | `amountIncVat`, `reason` | 200 with the `Rental`. 404. 409 `state-transition` for an amount owed on a `SETTLED` rental. 422 naming `body.amountIncVat` for nothing or an amount that is not a string with at most two decimals. |
| `POST /api/admin/allocations/{id}/release` | `reason` | 200 with the `Reservation`. 404. 409 `state-transition` when it is not active or its unit is on hire on the booking. 422. |
| `POST /api/reservations/{id}/reallocation` | none | 200 with the `Reservation`. 403 `branch-scope`. 404. 409 `state-transition` or `asset-unavailable`. |

Every admin route answers 403 to counter staff and customers.

| Read or write | Statements | Indexes |
|---|---|---|
| Audit log | 2, the count and the page, which joins the account that acted | the table above |
| Notification log | 2, the count and the page, with one index probe a row for `resendOf` | `ix_notification_failed`, `ix_notification_queued_at`, `ix_audit_event_entity` |
| Re-send | The failed row, the insert, the audit event, then the dispatch and one read of the new row | the primary key |
| A correction | The charge's rental, the rental with its items and charges under its lock, the writes, the read of the answer | `ix_charge_rental`, `ix_rental_item_rental` |
| Force release | The allocation with its booking and tag, the booking under its lock, the update, the audit event, the read | the primary keys |
| Reallocation | The sweep, the booking under its lock, then for each short line the locking query and the insert | `ix_asset_available`, the exclusion constraint's GiST index |

**What degrades first as the data grows.** The count of the audit log. Every
page counts every event that matches, so the log with no filter is counted in
full on each page, and `audit_event` grows fastest of all, by every change
the business makes. A few hundred events a day is nothing for years. At a
hundred times that, a year holds tens of millions of rows and the count takes
seconds, so the screen would want an estimate from the planner or no total,
and a page keyed on the event's number rather than OFFSET. The four new
indexes cost every insert into the log a little, which is the price of a log
that can be searched. The notification log holds a row a confirmation and
stays small. A correction is linear in the charges of one hire. The
reallocation takes one locking query a short line, bounded by the twenty lines
a booking can carry.

## The admin catalogue

The owner keeps the categories and the product models once for all three
branches, and sets each rate, deposit, late fee and replacement value there
(FR-22, US-30, BR-44). There is no new table and no new column. Revision
`0009` adds one index. Every route is for an administrator alone, and every
write reads the account again under a row lock (`FreshAdminUser`). Each write
is a use case on the unit of work that commits the change with its audit
event, and answers what it wrote as the list shows it, read once it has
committed.

**Categories.** `app/domain/category_rules.py` holds a category to its forms
and to the cap of two levels. A code is capital letters and digits and a slug
small letters and digits, each in words joined by single hyphens, for example
`BREAK-DRILL` and `breaking-drilling`, which is the form every seeded category
already has. A parent has to be a top level category, a category is never its
own parent, and a category that has children cannot be put under another one,
because they would end up three levels down. Each is a 422 naming
`parentCategoryId`, and so is a parent nobody can find. A category leaves the
catalogue by being switched off with `isActive`, because nothing is deleted
(BR-51). The list answers every category, switched off or not, each top level
category followed by its children by sort order and then name, on one page of
up to a hundred unless another page is asked for. `modelCount` counts the
models the category classifies itself, published or not. The visitor's list
rolls a child's models up into its parent, and this one does not, so the
counts of a parent and its children never count one model twice. I allow a
parent that is switched off, and switching off a category that still holds
models, because the contract refuses neither. The visitor's list already
shows such a child at the top level.

**Product models.** `app/domain/catalogue_entry_rules.py` holds the rules of
the contract, each a 422 naming its field. Every amount is zero or more, in
whole cents and within its NUMERIC(12,2) column (BR-22). The weekly rate is
at most seven days at the daily rate, because the pricing policy charges the
lower of the two totals (BR-21) and would never charge a weekly rate above
that. What seven days cost is asked of `StandardPricingPolicy`, which stays
the one place a rate is multiplied by days. The shortest hire is at least one
day, the longest at most 28, and the shortest never longer than the longest
(BR-03). The SKU takes the form of a code, as the design document's
`DR-BOSCH-GBH226` does, and the slug the form of a slug. A model is only
classified under an active category, which is checked when a model is created
and when its category changes, so the rate of a model whose category was
switched off since can still be changed. A new model starts unpublished, and a
creation that asks to be published is refused naming `isPublished`. An edit
never changes the SKU, so an edit that sends one is refused naming `sku`. The
contract lets an edit carry every other field, `isPublished` among them, and a
change of it there is recorded with the other changed fields.

**Duplicates.** A code, a SKU or a slug that another row holds is looked for
first, in one statement through the unique indexes, so the answer is a
sentence naming the field. Two administrators can still pass that check at
once. The unique constraints `category_code_key`, `category_slug_key`,
`product_model_sku_key` and `product_model_slug_key` then refuse the second
row, and `app/infrastructure/catalogue_uniques.py` recognises each by SQLSTATE
`23505` and its name, read from the driver and never from the message. The
answer is the same 422 the check would have given.
`tests/integration/test_admin_catalogue_race.py` stages that race for real.

**The snapshot.** A reservation line copies the rates, the deposit, the late
fee and the replacement value when it is made, and the rental is checked out
from the line (BR-20). Nothing in the admin catalogue reads or writes either
table, so a change reaches the next quote and the next booking and nothing
else. `tests/integration/test_rate_change_snapshot.py` books a hammer at R280
a day through HTTP, raises the rate to R310, and shows the booking, its line
and the rental checked out from it after the raise all at R280, while a new
quote and a new booking take R310.

**Publishing.** `POST /api/admin/models/{id}/publication` writes
`product_model.published` or `product_model.unpublished`, and asking for the
state a model is already in writes nothing. A hidden model leaves the
catalogue, the availability search and the quote the moment the change
commits, because each asks for published models only. The counter books
through the path a customer books through, and `models_of` in
`app/application/booking/reservation_request.py` asks for a published model,
so a hidden model cannot be booked at the counter either, which is a 422
naming `lines.0.modelSlug`. That was already decided in the code and I kept
it. A booking made before the model was hidden reads its model by key when it
is held, confirmed and checked out, so it carries on as it was.

**The audit events.** `category.created`, `category.updated`,
`product_model.created`, `product_model.updated`, `product_model.published`
and `product_model.unpublished`. A creation records every field as it became.
An edit records only the fields that changed, each before and after, so a
rate change reads `{"daily_rate": "280.00"}` and `{"daily_rate": "310.00"}`.
An edit that changes nothing writes nothing. `updatedAt` is stamped from the
clock the use case is handed.

| Route | Body or query | Answers |
|---|---|---|
| `GET /api/admin/categories` | `page`, `pageSize` (default 100) | 200 with `items` of `AdminCategory`, `page`, `pageSize` and `total`. 422 naming the parameter. |
| `POST /api/admin/categories` | `code`, `name`, `slug`, `description`, `parentCategoryId`, `sortOrder` | 201 with the `AdminCategory`. 422 naming the field. |
| `PATCH /api/admin/categories/{id}` | any of those and `isActive` | 200 with the `AdminCategory`. 404. 422 naming the field. |
| `GET /api/admin/models` | `q`, `categoryId`, `published`, `page`, `pageSize` | 200 with `items` of `AdminModel`. 422 naming the parameter. |
| `GET /api/admin/models/{id}` | none | 200 with the `AdminModel`. 404. |
| `POST /api/admin/models` | every member of `AdminModel` but `id`, `categoryName`, `assetCount` and `updatedAt` | 201 with the `AdminModel`, unpublished. 422 naming the field. |
| `PATCH /api/admin/models/{id}` | any of those but `sku` | 200 with the `AdminModel`. 404. 422 naming the field. |
| `POST /api/admin/models/{id}/publication` | `published` | 200 with the `AdminModel`. 404. 422 naming `published`. |

Every route answers 403 to counter staff and customers.

| Read or write | Statements | Indexes |
|---|---|---|
| Category list | 2, the count and the page, with a correlated count of models a row | `category_pkey` for the parent, `ix_product_model_category` for each count |
| Model list by category | 2, with a correlated count of units a row | `ix_product_model_category`, or `ix_product_model_published` when narrowed to published models, and `ix_asset_product_model` for each count |
| Model list unfiltered, by publication alone, or by text | 2 | none, it reads `product_model` from end to end |
| One category or one model | 1 | the primary key |
| Create a category | the check of code and slug, the parent, the insert, the audit event, the read | `category_code_key`, `category_slug_key`, `category_pkey` |
| Edit a category | the row under its lock, the parent and whether it has children when the parent changes, the check, the update, the audit event, the read | `category_pkey`, the unique indexes, and a scan of `category` for its children |
| Create a model | the check of SKU and slug, the category, the insert, the audit event, the read | `product_model_sku_key`, `product_model_slug_key`, `category_pkey` |
| Edit or publish a model | the row under its lock, the category or the slug check when they change, the update, the audit event, the read | `product_model_pkey`, `product_model_slug_key`, `category_pkey` |

**What degrades first as the data grows.** The model list that is not narrowed
by category. Its count and its page read `product_model` from end to end, and
a text search is a contains match on four columns that no btree can serve,
the same as a visitor's search. The catalogue is 120 models kept by hand, so
that is nothing, and at a hundred times as many it is still a few
milliseconds. Past that I would put a trigram index on the four columns,
because `pg_trgm` is installed, and page by name and SKU rather than OFFSET.
The category list orders the whole table in the statement, which is fine for
the hundreds of categories a hire business could ever hold, and whether a
category has children is a scan of the same small table. Each correlated count
is one index probe for each row of the page, so it is bounded by the hundred a
page may hold. A write locks one row, so two administrators only ever wait for
each other on the same model or category.

## The asset register

Every physical unit is tagged and moves through a fixed lifecycle from intake
to retirement, and the owner keeps the register of them (FR-23, US-31, US-32,
BR-34, BR-37, BR-38). There is no new table and no new column. Revision
`0010` adds two indexes. Every route is for an administrator alone, and every
write reads the account again under a row lock (`FreshAdminUser`). Each write
is a use case on the unit of work that commits the change with its audit
event, and answers the unit with its history, read once it has committed, so
the screen shows the move it has just made.

**Registering and editing (BR-34).** `app/domain/asset_register.py` holds a
unit to its rules, each a 422 naming its field. A tag is capital letters and
digits in words joined by single hyphens, the form of a code, in sixteen
characters at most, for example `TSH-DR-0042`. A tag another unit carries is
refused naming `assetTag`, whether the check finds it or the unique constraint
`asset_asset_tag_key` does when two administrators race, which
`app/infrastructure/catalogue_uniques.py` recognises the way it recognises a
SKU. The model has to exist, published or not, because stock arrives before a
model is put in the catalogue, and the branch has to be trading. A unit is
acquired on or before today, because that day is where its days in the fleet
begin for the report, and its cost is zero or more in whole cents. A new unit
starts at INTAKE. An edit changes the serial number, the grade, the meter
reading and the notes it names, and `UnitDetails` holds exactly those four,
so nothing an edit carries can reach the tag, the model or the branch. A body
that sends any of the three is refused naming it, the way an edit that sends a
SKU is. An edit that changes nothing writes nothing. A meter reading may go
down here, because correcting a misread meter is what an edit is for, and the
event records it before and after.

**Moving a unit by hand.** `app/domain/asset_transitions.py` adds the guards of
the route to the one table of moves in `app/domain/asset_lifecycle.py`, and
every move goes through its `moved`. I made five decisions there that the
contract does not settle.

1. ON_HIRE and LOST are never set here, because only checkout and the loss
   route set them. Asking for either is a 422 naming `to`, since no status of
   the unit would ever make it acceptable.
2. A unit on hire has no move by hand. The table lets it go back to the shelf
   or to quarantine, but those moves belong to the return, which closes the
   rental item and lets the allocation go with it. Doing either by hand would
   leave a rental item out and a booking holding a unit on the shelf. It is a
   409 that says the unit comes off hire through its return or its loss.
3. A move to QUARANTINED, UNDER_REPAIR or RETIRED takes a reason of 5 to 200
   characters, the rule of an administrator's override. A move to AVAILABLE
   may carry one and is held to the same bounds when it does.
4. A unit with a damage report still open goes back on the shelf when the
   report is resolved, and a move to AVAILABLE by hand is a 409 naming the
   report. Resolving the report records the repair cost and ends its span in
   the report, so putting the unit back by hand would leave it counted out of
   service while it is on the shelf.
5. `allowedTransitions` comes from the same table and the first two rules, so
   it is what the route accepts. It does not leave out RETIRED for a unit a
   booking holds, because the refusal names the booking, which is what the
   administrator needs to act on.

A move the table does not hold is a 409 whose sentence names where the unit
stands and whose `errors` carries `from_status` and `to_status`. A retirement
is refused with 409 while a booking holds the unit, and the sentence names the
booking's reference (BR-37). The booking is found through the GiST index of
the exclusion constraint, after the unit is locked with `FOR UPDATE`, and
`lock_allocatable` takes the same row lock with `SKIP LOCKED`, so a hold racing
the retirement either skips the unit or waits and finds it retired. A
retirement stamps `retired_on` with the business day and keeps the row (BR-38),
so the unit stays in the register, in its history and in the report, and the
availability search, which offers AVAILABLE units only, never offers it again.

**The audit events.** `asset.registered` records every field of the new unit
with the code of its branch. `asset.updated` records the fields that changed,
each before and after. A move writes `asset.status_changed`, the action
checkout, a return, a loss and a damage report already write, with the status
before, and after it the status, the tag and `retired_on`, which is the shape
the report reads, and the reason beside them. The move is written through
`save_units` of the asset repository, where every other change of a unit's
status is written. The utilisation report rebuilds a unit's days out of
service from these events, so a unit quarantined by hand is out of service
from the day it was moved and not from the day it was acquired.

**The history.** `GET /api/admin/assets/{tag}` adds `history`, at most fifty
entries, the newest first, each `at`, `kind`, `summary` and `reference`. `kind`
is where the entry comes from, `ALLOCATION`, `RENTAL`, `DAMAGE_REPORT` or
`AUDIT_EVENT`. An allocation is the hold and, once let go, the release with
why. A rental item is the handover and, once it ended, the return with its
grade or the loss. A damage report is the filing and, once closed, how it
ended. An audit event is the registration, an edit naming the fields it
changed, or a move with its reason. A checkout therefore shows the handover
and the move it made, because both happened. Each source is one statement of
at most fifty rows ordered by the latest instant a row carries, so the fifty
newest entries are always among what is read, and
`app/application/catalogue/asset_history.py` puts them in one list and says
what each means.

| Route | Body or query | Answers |
|---|---|---|
| `GET /api/admin/assets` | `q` of 2 to 80 characters, `branchCode`, `status`, `modelId`, `page`, `pageSize` | 200 with `items` of `AdminAsset`, in tag order. 422 naming the parameter, and `query.branchCode` for a code no branch has. |
| `GET /api/admin/assets/{tag}` | none | 200 with `AdminAsset` and `history`. 404. |
| `POST /api/admin/assets` | `assetTag`, `modelId`, `branchCode`, `serialNumber`, `conditionGrade`, `acquiredOn`, `acquisitionCost`, `hourMeterReading`, `notes` | 201 with the unit and its history, at INTAKE. 422 naming the field. |
| `PATCH /api/admin/assets/{tag}` | any of `serialNumber`, `conditionGrade`, `hourMeterReading`, `notes` | 200 with the unit and its history. 404. 422 naming the field, and `assetTag`, `modelId` or `branchCode` when one is sent. |
| `POST /api/admin/assets/{tag}/transitions` | `to`, `reason` | 200 with the unit and its history. 404. 409 `state-transition` naming the status, the booking or the report. 422 naming `to` or `reason`. |

Every route answers 403 to counter staff and customers. A tag in a path is
read in capitals, the way it is painted on the unit. The branch filter takes
any branch, trading or not, because units of a closed branch are still in the
register.

| Read or write | Statements | Indexes |
|---|---|---|
| A page | 2, the count and the page, and 3 with `branchCode`, which is looked up first. Each row carries two correlated counts | `asset_asset_tag_key` for the order, `ix_asset_branch_status` for a branch, `ix_asset_product_model` for a model, `ix_asset_tag_trgm`, `ix_asset_serial_trgm` and a read of `product_model` for `q`, the GiST index of `asset_allocation_no_overlap` and `ix_damage_report_asset` for the counts |
| One unit | 1, and 4 more for its history | `asset_asset_tag_key`, then `ix_asset_allocation_released` and the GiST index of the exclusion constraint for the released and the active allocations, `ix_rental_item_asset`, `ix_damage_report_asset` and `ix_audit_event_entity_id` |
| Register | the model, the branch, the check of the tag, the insert, the audit event, then the read of the answer | the primary key, `branch_code_key`, `asset_asset_tag_key` |
| Edit | the unit under its lock, the update, the audit event, the read | `asset_asset_tag_key` |
| Move | the unit under its lock, the booking that holds it for a retirement or the open report for a move to the shelf, the update, the audit event, the read | `asset_asset_tag_key`, the GiST index of the exclusion constraint, `ix_damage_report_asset` |

The route adds the account to each, and a write reads it again under its lock.

**What degrades first as the data grows.** The page narrowed by `status`
alone. No index leads with the status, so the planner walks the tag index and
keeps the units in that status, which is quick for a status many units hold
and reads most of the fleet to fill a page of one few hold, such as LOST. At
four hundred units that is nothing. At a hundred times the fleet a partial
index on the tag for each rare status, or one on `(status, asset_tag)`, would
serve it. After that comes the count of every page, which counts every unit
that matches, and OFFSET, which reads every unit before a deep page, as the
other lists do. A search of two characters reads the whole trigram index, so
the screen should ask for three. A unit's history reads at most fifty rows of
each of its four sources, and each source is sorted inside the statement,
which is a few hundred rows over a unit's life. The audit events grow fastest
and are read off the end of their index, so the history stays four short
statements however long the unit has been in the fleet.

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

Revision `0006` adds one column and nothing else,
`rental_item.flagged_for_damage`, a `BOOLEAN NOT NULL DEFAULT false` that holds
the counter's damage flag on a unit that came back. The design document lists
no such column, and the revision's docstring explains the departure. A column
with a constant default is added without rewriting the table, so the statement
holds its lock for a moment however many items there are. The release before
it never names the column, so its inserts take the default and it keeps working
against a migrated database. A privilege on a table covers the columns it gains
later, so there is nothing to grant.

Revision `0007` adds five indexes and nothing else, all of them read by the
utilisation report. `ix_charge_raised_at` on `charge.raised_at` finds the
charges of a period. `ix_rental_item_returned_at` on `rental_item.returned_at`
finds the hires still out and those back since a period began.
`ix_rental_item_lost`, partial on a rental item closed with no condition,
holds the lost units and nothing else. `ix_damage_report_resolved_at` on
`damage_report.resolved_at` finds the reports open during a period and those
resolved in it. `ix_audit_event_asset_status` on `audit_event (entity_id,
occurred_at)`, partial on the action `asset.status_changed`, finds the last
change of a unit's status before a period and the first after it. Each is
built inside the migration's transaction, which blocks writes to its table
while it builds, and `audit_event` is written by every change. On the tables of
a first year that takes moments. A table a hundred times larger would want
`CREATE INDEX CONCURRENTLY` outside a transaction instead.

Revision `0008` adds four indexes and nothing else, read by the two logs of
the admin console. `ix_audit_event_entity_id` on `audit_event (entity_id,
occurred_at)` finds the history of one record by its key alone, which the
baseline index on the kind and the key cannot. `ix_audit_event_action` on
`(action, occurred_at)` finds every event of one action, and it is partial on
every action but `asset.status_changed`. Holding those changes in time order
it would answer the report's question about a unit's last change of status by
reading every change of the fleet backwards, which the planner takes on a
small table, so it leaves them out, and the log of that one action is read
through `ix_audit_event_occurred_at`. A search for any other action says so in
the statement as a literal, which is how the planner matches the predicate.
`ix_audit_event_actor` on `(actor_user_id, occurred_at)`, partial on an event
that has an actor, finds everything one account did, and
`ix_notification_queued_at` on `notification.queued_at` reads the notification
log newest first. Each ends in the column its log is ordered by, so a page is
read off the end of its index. They are built inside the migration's
transaction like those of `0007`, with the same caution for a table a hundred
times larger.

Revision `0009` adds one index and nothing else, `ix_product_model_category`
on `product_model (category_id, name)` with no predicate. The admin catalogue
finds the models of one category through it, published or not, in the order
it lists them, and counts the models of each category through it. The partial
index of the baseline holds the published models only, and PostgreSQL never
indexes a foreign key by itself. `product_model` is the catalogue, 120 rows
that change by hand, so building it inside the migration's transaction blocks
writes to the table for a moment. A table a hundred times larger would want
`CREATE INDEX CONCURRENTLY` outside a transaction instead.

Revision `0010` adds two indexes and nothing else, both read by the asset
register. `ix_asset_serial_trgm` is a trigram index on `asset.serial_number`,
through which the register finds part of a serial number the way it finds
part of a tag through `ix_asset_tag_trgm`. `ix_asset_allocation_released` is a
btree on `asset_allocation (asset_id, released_at)`, partial on a released
allocation, through which the history of a unit reads every booking it was
released from. The GiST index of the exclusion constraint already holds the
active ones, and `asset_allocation` is the table that grows with every
booking. The index is partial on purpose. A plain index on the unit was my
first version, and on a small table the planner then preferred it to the
GiST index for the availability search, which
`tests/integration/test_availability_list.py` caught. An index that holds
released allocations only can never answer a question about active ones, so
the search keeps the index it was written for. Both are built inside the
migration's transaction, with the same caution as the revisions before it for
a table a hundred times larger.

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
| GET | `/api/admin/reports/utilisation` | An administrator. |
| GET | `/api/admin/reports/utilisation.csv` | An administrator. |
| GET | `/api/admin/dashboard` | An administrator. |
| GET | `/api/admin/audit-events` | An administrator. |
| GET | `/api/admin/notifications` | An administrator. |
| POST | `/api/admin/notifications/{id}/resend` | An administrator, read again under a lock. |
| POST | `/api/admin/charges/{id}/waiver` | An administrator, read again under a lock. |
| POST | `/api/admin/charges/{id}/reversal` | An administrator, read again under a lock. |
| POST | `/api/admin/rentals/{id}/adjustments` | An administrator, read again under a lock. |
| POST | `/api/admin/allocations/{id}/release` | An administrator, read again under a lock. |
| POST | `/api/reservations/{id}/reallocation` | Counter staff of the collection branch, and administrators. |
| GET | `/api/admin/categories` | An administrator. |
| POST | `/api/admin/categories` | An administrator, read again under a lock. |
| PATCH | `/api/admin/categories/{id}` | An administrator, read again under a lock. |
| GET | `/api/admin/models` | An administrator. |
| GET | `/api/admin/models/{id}` | An administrator. |
| POST | `/api/admin/models` | An administrator, read again under a lock. |
| PATCH | `/api/admin/models/{id}` | An administrator, read again under a lock. |
| POST | `/api/admin/models/{id}/publication` | An administrator, read again under a lock. |
| GET | `/api/admin/assets` | An administrator. |
| GET | `/api/admin/assets/{tag}` | An administrator. |
| POST | `/api/admin/assets` | An administrator, read again under a lock. |
| PATCH | `/api/admin/assets/{tag}` | An administrator, read again under a lock. |
| POST | `/api/admin/assets/{tag}/transitions` | An administrator, read again under a lock. |
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
| `GET /api/reservations/{id}/checkout` | none | 200 with the reservation, its customer, its units, `hireTotalIncVat`, `depositTotal`, `canCheckOut`, `refusal`, `rentalId` and `unitsShort`. 404. |
| `POST /api/reservations/{id}/checkout` | `items` of `allocationId`, `conditionOut`, `accessoriesOut` and `hourMeterOut`, and `agreementSigned` | 201 with the `Rental` and a `Location` header. 200 with the existing rental when it was already checked out. 409 `state-transition` when it is not confirmed, its hire has not started or it is short of a unit. 403 `branch-scope`. 422 naming the field. |
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
flag kept on the item apart from the notes, which never decide anything, the
moves of a report's status on their own, what each move
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
indexes. `test_flagged_return.py` takes a unit back flagged in the grade it
went out in and reads the committed row, which holds the flag in its column and
the notes exactly as they were posted.

The report and the dashboard are tested the same way. `tests/unit` holds the
day counting on half open spans, the serviceable days of a unit acquired,
retired, damaged, lost and moved through its statuses, the days on hire of a
unit back, still out, back the day it went out and late into a booking, the
percentage at its rounding edges, gross contribution, the share of a whole
hire with its rounding cent and its reversal, the escape of a CSV cell, the
lines, ranking, totals and pages, and both use cases against fakes of their
ports, with every refusal and the sweep before the read. `tests/api` pins the
shapes of the report, the CSV and the dashboard, a hire of two units shared
between them, every refused parameter by name, the three roles and a caller
with no credential, a model name a spreadsheet would run, and a booking the
sweep marks before the dashboard counts it. On PostgreSQL,
`test_report_worked_dataset.py` builds the fleet in `tests/support/report_dataset.py`,
whose docstring works every figure out by hand, and asserts every grouping,
both filters, the totals and the dashboard against those figures.
`test_report_losses.py` follows a loss to the next recorded change, and
`test_report_reads.py` counts the statements and proves the indexes.

The admin operations are tested the same way. `tests/unit` holds the reason
rule, the waiver, the reversal and the adjustment and every refusal of each,
the rework of a settlement before and after the deposit is settled with a
balance and with nothing left, the force release, the missing units at the
checkout and the top up, and the force release, the reallocation, the re-send
and the two reads against the in memory stores and fakes of their ports.
`tests/api` follows every correction, the release and the replacement through
the routes, asks each route for every refusal it can give, reads the two logs
with every filter, and sends a failed confirmation again through the Resend
adapter with an allowed recipient, which still refuses it. On PostgreSQL,
`test_charge_correction_transaction.py` makes a correction fail at its audit
event and finds nothing kept and proves the original row of a reversal is left
as it was, `test_force_release_transaction.py` releases and tops up through
the exclusion constraint, `test_admin_log_reads.py` counts the statements of
both logs with few rows and many and asks the planner to prove each filter
stands on its index, and `test_application_role.py` proves the restricted role
reads both logs and cannot change or remove one event.

The admin catalogue is tested the same way. `tests/unit` holds the forms of a
code and a slug, the amounts, the cap of two levels, the weekly rate and the
hire days and every refusal of each, and the five writes and the reads
against the in memory unit of work in `tests/support/memory_catalogue.py`,
which can be made to lose a race to a unique constraint or to fail at its
audit event. `tests/api` lists, creates, edits and publishes through the
routes, asks for every refusal with the field it names, and proves a hidden
model leaves the public catalogue. On PostgreSQL,
`test_rate_change_snapshot.py` raises a rate from R280 to R310 between a
booking and its checkout, `test_unpublished_model.py` hides a model from the
availability search and still checks out a booking made before,
`test_admin_catalogue_transaction.py` makes each write fail at its audit event,
`test_admin_catalogue_race.py` names the field of each unique constraint and
stages a race for one code, and `test_admin_catalogue_reads.py` counts the
statements of each read with few rows and many and asks the planner to prove
each filter and each count stands on its index.

The asset register is tested the same way. `tests/unit` holds the form of a
tag, the day a unit is acquired, its cost, its meter reading and its text,
every move by hand the table offers and every one it refuses, ON_HIRE and
LOST asked for from every status, the reason, a unit a booking holds and a
unit with a report open, the three use cases against the in memory unit of
work in `tests/support/memory_register.py`, which can be made to lose the tag
to the unique constraint or to fail at its audit event, and the history put
together from facts built by hand. `tests/api` lists, searches, registers,
edits and moves through the routes, reads the history of a unit checked out at
the counter, and asks every route for every refusal with the field or the
status it names. On PostgreSQL, `test_asset_register_transaction.py` makes
each write fail at its audit event, refuses to retire a unit a booking holds,
shows a retired unit kept, never offered again and still in the report for
the days it was in the fleet, and a unit quarantined by hand out of service
from the day it moved. `test_asset_register_race.py` stages a race for one
tag. `test_asset_register_reads.py` counts the statements of a page, a unit
and its history with few rows and many, and `test_asset_register_indexes.py`
asks the planner to prove each condition stands on its index.

The role tests need no setup. They create `toolshed_app` and `toolshed_migrate`
through `scripts/provision_roles.py`, using the connection in `DATABASE_URL` as
the owner, and apply the grants through the function revision `0002` calls. The
passwords they set are throwaway values in `tests/support/roles.py`. Roles
belong to the cluster and not to one database, so the two roles stay behind
after the run.

`tests/integration/test_schema_baseline.py` runs before every other test. It
reads the PostgreSQL catalogue and asserts that the three extensions, the
seventeen tables, the seventeen enumerated types, the exclusion constraint with
its exact definition and the partial indexes all exist, and that every column a
later revision added is NOT NULL with its default. Every other integration
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
