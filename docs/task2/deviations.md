# Deviations from the Task 1 design document

Every place I know of where the built system differs from the Task 1 design
document, and why. I found them in the pull request descriptions, the backend
and frontend READMEs and the code. Each pull request also has a "Self review"
section that records these decisions at the moment I made them.

<!-- final: add anything branches 015 to 022 change, and recheck every row -->

## Hosting and operations

| What the design planned | What I built | Why |
|---|---|---|
| The database region was left open between London and Frankfurt until a round trip had been measured, and the API was to sit beside it. | The API runs on Cloud Run in `europe-west2`, London, and the database on Neon in AWS `eu-west-2`, London. | A request makes several database round trips and only one back to the browser, so the API belongs beside the database. London is a dearer Cloud Run price tier than Belgium, and I accepted that. |
| Production capped at four instances, with a pool of five connections each, which is the connection ceiling the scalability requirement is worked out from. | Both environments are capped at one instance. | The system runs on a free trial, and an instance cap is the only hard limit on what a public service can cost if somebody floods it. One instance at a concurrency of 80 is far more than a demonstration needs. The workflow records the design figure, and a paying client means setting it back to four. |
| A billing budget with alerts in rand. | A budget of 30 USD with alerts at 20, 50 and 100 percent. | The billing account and its free trial credit are in US dollars, and a budget is set in the currency of its billing account. |
| The image cleanup policy keeps the two newest images and the one serving production. | It keeps the three newest and deletes the rest once they are seven days old. | A cleanup policy cannot name the image that is serving, so I keep one more instead. Storage stays under the free allowance, and [OPERATIONS.md](../../infra/OPERATIONS.md) has the command I use to check it. |
| Scheduled checks every five and every thirty minutes to measure availability over trading hours. | No scheduled checks. Each deployment smoke tests the new revision, and I check the health route by hand. | A scheduled request every few minutes would keep the API and the database awake all day, which defeats scaling to zero and spends the trial credit. I still want the availability figure, so this is open for Task 3. |
| Production holds the business's own records, with the open bookings carried across from the paper diary. | The seed loads a fictional fleet of 400 units, five accounts and the worked example into every environment, production included. It runs on every deployment and only creates what is missing. Customer accounts have their own seed password. | This is a demonstration with no real business behind it, so production needs a fleet and accounts from its first deployment. The separate customer password lets me publish one customer login without exposing the staff ones. |

## Repository and pipeline

| What the design planned | What I built | Why |
|---|---|---|
| A private repository. | The repository is public. | The submission is the link to this repository, so my lecturer has to be able to open it without an invitation. Every account specific value in [infra](../../infra) is a placeholder, and the API's own address is masked in the workflow logs. |
| A preview of the frontend and a staging revision of the API for every pull request, with a short lived database branch. | Staging is deployed on every merge into `develop`. Every pull request runs the browser tests against the real API and a freshly seeded PostgreSQL inside the pipeline. | The browser tests in the pipeline already prove each pull request against a real API and database, without the extra secrets, database branches and allowances a preview per pull request would need. |
| A browser smoke suite after each deployment. | The smoke test asks the health route of the new revision, then asks it again through the site. | The browser journeys write data, so I keep them in the pipeline against a throwaway database. Running them against staging is planned in issue [#22](https://github.com/teon-artilionAI/toolshed-hire/issues/22). |
| Release branches named after each task. | Release branches are named after the version, `release/0.1.0` and `release/0.2.0` so far, and the tag `task2-v1.0` marks the state I hand in. | Task 2 is delivered in several releases, and a version number says which. |
| Every migration rehearsed on an empty database, on a seeded one and as a downgrade before it reaches production. | Every pull request migrates an empty database and every merge migrates the seeded staging database. I rehearsed the downgrade by hand for the first migrations only. | A rollback never runs a downgrade. Each migration is written to work with the revision still serving, and a migration that is itself wrong is fixed forward with a new one, as [OPERATIONS.md](../../infra/OPERATIONS.md#rollback) says. |
| High and critical advisories block a merge. | They still do, unless [audit-exceptions.json](../../frontend/audit-exceptions.json) holds a reviewed exception for that one advisory, with a reason and an expiry date. One does, for `braces`. | A high advisory against every version of `braces` was published while a pull request was in review, and blocked every merge. It reaches the build only through Tailwind CSS 3 expanding my own file patterns, and nothing from it is in the bundle. The only fix is the move to Tailwind 4, tracked in issue [#49](https://github.com/teon-artilionAI/toolshed-hire/issues/49). Every other advisory still blocks, and this one blocks again when the exception expires. |
| The browser tests run on the real clock. | The pipeline starts the API's clock at 10:00 in Cape Town on the day of the run with `TEST_BUSINESS_TIME`. | A hire can only start today while the branch is open, so the counter journey would fail whenever the pipeline ran after 17:00. The setting is refused by every environment except test, so no deployed service can run on a clock that lies. |
| No `any` type anywhere. | Strict mypy everywhere, with the check on an explicit `Any` switched off in the eleven modules that declare pydantic models. | pydantic makes mypy invent a hidden member typed `Any` on every model, and the check reports it against my class. Narrowing the exception to those modules keeps it live everywhere a hand written `Any` would matter. |

## Data model

| What the design planned | What I built | Why |
|---|---|---|
| No column for late cancellations. | `customer_profile.late_cancellation_count`. | A late cancellation has to be recorded on the customer's profile, and the column list had nowhere to put it. |
| No columns for the email verification and password reset tokens. | `user_account` holds the SHA-256 of each token and when it expires, with unique partial indexes. | Each link needs a single use, time limited token, and only its hash may be stored. |
| The indexes of the baseline. | Migration `0003` adds a trigram index over the digits of a customer's phone number. Migration `0004` adds a trigram index on the asset tag, an index on an asset's model and an index on a rental's branch and due date. Each adds indexes and nothing else. | The counter's customer search, asset locator and diary each needed an index the baseline did not have. A test asks PostgreSQL for its plan and proves each is used. |
| `no_show_count` as a rolling count over twelve months. | `no_show_count` is a running total, and the three strikes rule counts the no shows of the last twelve months from the reservations themselves. | A rolling figure in a column goes stale as days pass without anything writing to it. Counting from the reservations is always right and stands on an index. |

## Security and sessions

| What the design planned | What I built | Why |
|---|---|---|
| The lockout counts failures in the account's own columns, and `rate_limit_counter` serves the throttles. | Each wrong password is also counted in `rate_limit_counter`, to the second, under a salted hash of the account, and the account locks on the fifth failure inside the last fifteen minutes. | A window of fifteen minutes needs the time of each failure, and the account row holds only a number. The first version counted consecutive failures, and I corrected it to a sliding window without adding a table or a column. |
| A 128 bit refresh token. | A 256 bit refresh token. | It costs nothing and is stronger. |
| The role on the access token trusted for up to fifteen minutes. | Every request reads the role from the database. | It is stricter, and the cost is one indexed read. |
| Throttling on the account routes, with no numbers set. | Seven limits with defaults of my own, listed in [backend/README.md](../../backend/README.md#the-throttles-of-the-account-routes). They can be lowered in a deployment and never raised. | The design named the routes and not the figures. |
| A password reset revokes every session. | It does, with the revocation reason `LOGOUT`, and the audit event says it was a reset. | The enumeration of reasons had no closer match, and adding one was not worth a migration. |

## Email

| What the design planned | What I built | Why |
|---|---|---|
| Email delivered to every customer. | Restricted mode. `EMAIL_ALLOWED_RECIPIENT` names the only address the service sends to, the adapter refuses any other before the provider is called, and a refused message is never redirected. | The demonstration has no verified sending domain. Refusing on the server stops a stranger's address from ever receiving mail from a university project, and redirecting would hand one customer's booking to somebody else. |
| The confirmation sent after the commit. | It is sent after the commit, inside the same request, with an idempotency key, and the account messages are sent the same way. | Cloud Run only gives a container CPU while it serves a request, so work left for a background thread might never run. The key means a message dispatched twice is delivered once. |
| Three outbound messages. | A fourth, a short note to the owner of an address that somebody tried to register again. It carries no token and writes no notification row. | Registration answers every address the same way, so the form cannot reveal who has an account. The note tells the real owner what happened without telling the person at the form. |

## Business rules

| What the design planned | What I built | Why |
|---|---|---|
| Counter staff may book for today, and customers from today onwards. | Nobody can start a hire today once the collection branch has closed. | After closing nobody can collect, and the no show sweep would mark the booking a no show at once with a strike against the customer. |
| Opening hours that differ on a Saturday, and no trading on a Sunday. | Each branch has one opening and one closing time, seeded as 07:00 to 17:00, and every day of the week is treated the same. | The branch table in the design holds one pair of times. Hours by weekday need a schema change, and I have listed it as a known limitation. |
| A late fee per day that attracts VAT. | The late fee per day is an amount including VAT. R240.00 is written as R208.70 plus R31.30. | It is the only reading under which the figures of the worked example add up. |
| Hire revenue attributed to each unit, so gross contribution can be reported per unit. | On a hire of one unit the hire charge belongs to that unit, as in the worked example. On a hire of more units it belongs to the rental. | The charge is written from the figures stored on the reservation and never worked out again. Sharing it across units needs an apportioning rule, which belongs with the utilisation report that needs it. |
| Release reasons for a booking that is returned, cancelled, not collected, expired or reallocated, and none for a loss. | The allocation is released with the reason `RETURNED` before the unit moves to `LOST`, and the audit event says what happened. A lost unit reads as closed with no condition recorded. | The release reasons have no member for a loss, and a unit may not be marked lost while it holds a booking. |
| An overdue hire goes back to partially returned as units come in. | A hire with any unit still out past its due date stays `OVERDUE` until that unit is back. | A hire that still has a late unit is still overdue, and the overdue list should keep showing it. |
| Expired holds and no shows swept on reads and on the first signed in request of the day. | A bounded batch of 25 is swept before every hold, confirmation, read of reservations, availability search and counter read, and each use case also lapses the one reservation it is about to decide on. | A hold lasts thirty minutes, so a lapse has to be seen before anything an expired hold could wrongly block or allow. A bounded batch keeps the cost of each request flat however many are due. |
| A damage report created at the return itself, quarantining the unit at once. | The return flags a unit, and the damage report is filed as a second step on SC-16. The deposit settlement waits until every flagged unit is assessed. <!-- final: confirm against 015 --> | <!-- final: the reason from the 015 pull request --> |
| A damage photograph stored in a private bucket in `us-central1`. | No photograph upload and no bucket yet. | <!-- final: confirm the plan for photographs --> |

## Screens and the API

| What the design planned | What I built | Why |
|---|---|---|
| The model page shows a fourteen day availability strip for each branch. | SC-03 says for each branch whether the quantity is free for the dates chosen, beside the price for those dates. | The customer has already chosen dates by then, and one clear answer for them is what the search exists to give. |
| The counter can pick a specific unit or let the system allocate one. | SC-13 always lets the server allocate. | One allocation path keeps the lock and the constraint in one place. The tags of the units set aside are shown once the booking is held. |
| The counter dashboard lists bookings that need a unit swapped. | SC-10 has no such panel. | Nothing in the system reallocates a unit yet, so there is nothing to list. |
| A quote that applies the customer's trade discount. | The public quote route applies none. The booking applies the discount on the customer's profile. | A public route cannot also depend on a signed in role, because the application refuses to start on a route that declares both. |
