# Presentation outline

The recorded presentation of Task 2 runs for about fifteen minutes. It is a
walk through the slides below with a live demonstration on production in the
middle. The script for the demonstration follows the slides. The slides are in
[slides/toolshed-hire-task-2.pdf](slides/toolshed-hire-task-2.pdf), and the
video is linked from the [README](../../README.md#links).

| Part | Slides | Time |
|---|---|---|
| The problem and the requirements | 1 to 4 | 2:00 |
| How it is built | 5 to 8 | 3:15 |
| How it is delivered | 9 and 10 | 2:00 |
| Live demonstration | 11 | 5:30 |
| Testing, deviations and what is next | 12 to 15 | 2:15 |

## Slides

### 1. Toolshed Hire, Task 2

- Toolshed Hire, the built system for INSY7315
- Teon Kleynhans, ST10434209, working alone
- Live at toolshed-hire.vercel.app

**Notes.** I introduce myself and say that this is the built system I designed
in Task 1. Everything I show today runs on the production site, and the code,
the pipeline and the evidence are all in the public repository.

### 2. The problem

- A three branch tool hire business in Cape Town, about 400 tagged units across
  120 models
- Bookings live in a paper diary and a WhatsApp group
- The same unit gets promised twice, staff phone each other to find stock, and
  the owner cannot say which equipment earns its keep

**Notes.** I keep this short, because Task 1 covered it. The three problems
drive everything that follows. The database now prevents the first, the
locator answers the second, and the report answers the third.

### 3. What Task 2 delivers

- The customer journey, from the catalogue to a confirmed booking
- The counter journey, from a walk-in to checkout, return, damage and deposit
  settlement
- The owner's side, the dashboard, the report with its CSV, the catalogue and
  prices, the asset register, users and customer holds, the audit trail and
  charge corrections
- Two environments, deployed by the pipeline only, and live as `v0.4.1`

**Notes.** All 24 screens read from the API now, and no screen shows sample
data any more. I say plainly that the statement download and the damage
photographs are the parts still to come.

### 4. Requirements and how they are traced

- 28 functional and 18 non-functional requirements from Task 1
- Issue, then branch `feature/nnn-slug`, then pull request, then merge commit
- The traceability table in the README gives the status, the pull request, the
  screens and the tests for every requirement
- 27 built and 1 partly built, FR-28, whose statement download is planned

**Notes.** I open the README on GitHub and scroll the traceability table. I pick
FR-07, no unit with two overlapping bookings, and follow it to the pull request
and to the test that proves it. I mention that the non-functional requirements
are mapped to how I verify each one in the test plan, honestly, including the
ones I have not verified yet.

### 5. Architecture

- Browser, Vercel, Cloud Run, Neon PostgreSQL and Resend, on one origin
- Four layers, domain, application, infrastructure and API
- Eight modules with the same name in every layer, all eight built
- Five import contracts checked on every push

**Notes.** I show the request path diagram. The browser only talks to the site's
own address, and Vercel passes `/api` to Cloud Run on the server side, which
keeps the refresh cookie on one origin and lets the Content Security Policy
allow this origin alone. The rules sit in the domain layer, and a contract fails
the build if anything there imports a database or a framework.

### 6. The four design patterns

- Repository with Unit of Work, one transaction for a hold, its allocations and
  its audit event
- Adapter, the email provider behind a port, with a transactional outbox
- Strategy, the pricing policy, the late fee policy and the share of a hire
  charge in the report
- State, eight reservation states where every move is refused unless a state
  allows it

**Notes.** For each pattern I show the file and say the problem it solves here.
I point out that a test reads every module to prove that only the policy works
out a price or a late fee, so the rule cannot leak into other code later.

### 7. The database

- Seventeen tables, singular names, hand written migrations
- A `daterange` exclusion constraint, so PostgreSQL itself refuses an
  overlapping booking of one unit
- Each later migration adds indexes or one column, and tests prove each index is
  used
- Two roles, so the running application cannot change the schema or rewrite the
  audit trail

**Notes.** I show the constraint in the backend README. Periods are half open, so
a return on the twelfth frees the twelfth. I explain that the lock with
`SKIP LOCKED` lets concurrent bookings take different units, and the constraint
has the last word if anything gets past it.

### 8. Security

- Sessions with a fifteen minute token in memory and a rotating refresh cookie
- Deny by default, ownership answered as not found, branch scope for counter
  staff, and the owner's functions for the administrator alone
- Lockout, throttles, security headers checked on the deployed site after every
  deployment, and no secret in the repository
- 44 controls, 31 in place, 6 partly in place, 1 replaced and 6 planned

**Notes.** I open the security controls file and say that I only marked a
control in place where I can point at the code or the test. I name the ones
still open, which are the photograph upload, edge filtering, alerting and the
incident procedure.

### 9. Pipeline and branching, a live look at GitHub

- Reduced GitFlow, `main`, `develop`, feature, docs, test, release and hotfix
  branches
- Fast checks on every push, integration checks on every pull request
- Two required checks, merge commits only, no bypass for anyone
- After each staging deployment, the header and TLS check and the three
  journeys in a browser

**Notes.** I switch to GitHub and show the branch list, a merged pull request
with its checks and its "Manual verification" section, the Actions history,
and the rulesets. I say that I am the only person on the project, so the
checks are the review gate and I do not claim a second reviewer.

### 10. Hosting and the release procedure

- Vercel for the site, Cloud Run in London for the API, Neon in London for the
  database
- Keyless deployment through Workload Identity Federation, secrets in Secret
  Manager
- A release tag waits for my approval, then a candidate revision is smoke
  tested before it takes any traffic, and the deployed headers and TLS are
  checked last
- One instance at most and a budget alert, because this runs on a free trial

**Notes.** I show the `v0.4.0` production deployment run, cut from
`release/task-2`, with its approval step and its summary. I explain why the API
sits in London beside the database, and that the cold start is the price of
scaling to zero.

### 11. Live demonstration

- The customer journey on production
- The counter journey, with checkout, return and the deposit
- The worked example from Task 1
- The owner's side, from the dashboard to the audit trail

**Notes.** I follow the demonstration script below.

### 12. Testing

- Domain and application tests with no database, API tests, PostgreSQL 16
  integration tests, browser and accessibility tests, and checks of the
  deployed site
- 100 percent of lines covered in the domain and application layers, against a
  floor of 70
- Twenty holds at once for five units give exactly five holds
- 4,623 backend tests on PostgreSQL 16, 1,455 frontend unit and component
  tests and 392 browser and accessibility tests against the real API in CI
- 109 axe scans across all 24 screens and their states with zero findings, and
  every screen laid out at 360, 768 and 1440 pixels

**Notes.** I show the test plan table and one concurrency test. I mention the
report's dataset worked out by hand, 31.25 percent and R1,321.95, and that axe
finds nothing at any impact on all 24 screens. I say what is not verified yet,
which is the load test, the volume test and the restore drill on the
deployment.

### 13. Deviations from the design

- Both environments capped at one instance
- Email in a restricted mode on this demonstration
- A settled hire only takes a correction that gives money back
- The report works out its days in the domain rather than in one query

**Notes.** I open the deviations file and give the reason for two or three of
them. I want it clear that each change was a decision with a reason and not
something that drifted.

### 14. What is left for Task 3

- The statement download, data export and the retention period
- Damage photographs with their upload controls, and edge filtering
- The load, volume and cold start measurements, the restore drill and the
  usability sessions
- Alerting and the incident procedure
- Release `v1.0.0`, the report and the user guide

**Notes.** I close the technical part by saying what Task 3 has to finish and
that `v1.0.0` is kept for the release where the built system matches the whole
design.

### 15. Thank you

- toolshed-hire.vercel.app
- github.com/teon-artilionAI/toolshed-hire
- Teon Kleynhans, ST10434209

**Notes.** I thank the viewer and point at the README as the place to start.

## Demonstration script

### Before recording

1. Record on a weekday before 17:00 in Cape Town, because a hire can only start
   today while the branch is open.
2. Open the production site a minute before recording, so the API and the
   database are awake.
3. Sign out everywhere and empty the hire basket.
4. Have these tabs ready. The production site, the README on GitHub, the
   pull requests, the Actions page, the `v0.4.0` production deployment run, and
   the rulesets and environments in the repository settings.
5. Have the counter and admin logins to hand, off screen, and choose a tag for
   the demonstration unit and a made up name for the staff account that no
   earlier rehearsal used.

### Customer, about one and a quarter minutes

| Step | What I click | What I say |
|---|---|---|
| 1 | Open the catalogue home, pick dates from tomorrow and search | No account is needed to see what we hire and what it costs. |
| 2 | Point at the results, then choose Bellville as the branch | This one search replaces three phone calls. It says free or not free for each branch and never how many units there are. |
| 3 | Open a model, add it to the basket and review | The price is the server's quote, and the browser does no sum of its own. Reviewing needs an account, so the site sends me to sign in and brings me back. |
| 4 | Sign in as the demo customer, then Hold | Named units are now set aside for thirty minutes, and the countdown shows it. |
| 5 | Confirm | The booking has a reference. The screen does not promise an email, because this demonstration only delivers to my own address. |
| 6 | My Hires, open the booking and cancel it | The customer sees their own bookings only, and cancelling releases the units in the same transaction. |
| 7 | Account, then the last page of the hire history | This closed hire is the worked example from Task 1, with the deposit shown as held, kept and returned. The newer hires come from the season of trading history the seed writes. |
| 8 | Sign out | |

### Counter, about one and three quarter minutes

| Step | What I click | What I say |
|---|---|---|
| 1 | Sign in as the Cape Town CBD counter assistant | Counter staff land on today's dashboard for their own branch. |
| 2 | Customers, register a walk-in with a made up name | A walk-in has no login. Only the last four characters of the identity document are typed in. |
| 3 | New Booking for that customer, one unit for today, review, hold, confirm | The counter uses exactly the same booking path as a customer. The server allocates the unit and shows its tag to staff. |
| 4 | Check out now, tick the tag, keep the condition, sign the agreement, confirm | One transaction opens the hire, puts the unit on hire and takes the deposit. |
| 5 | Open the hire's return, tick the unit, take it back | Back before the due date means no late fee, so the deposit is released in full and nothing is due. |
| 6 | Locator, search `TSH-DR-0042` | Any unit at any branch, read only. This answers the second problem. |
| 7 | Type `/counter/return/TSH-H-26-000098` in the address bar | The return screen opens a hire by its reference. This is the worked example. R1,200.00 held, two days late at R120.00, R240.00 withheld, R960.00 released, R0.00 due. A test follows the same figures through the API on every pull request. |
| 8 | Sign out | |

### Owner, about two and a half minutes

| Step | What I click | What I say |
|---|---|---|
| 1 | Sign in as the administrator | The owner lands on the dashboard of the whole business. Each branch today, the month so far, and what waits on the owner, open damage reports, customers on hold and failed emails, each a link to where I would go next. |
| 2 | Open the report, which starts at the last full month, September 2026, and group by branch | Utilisation is the days a unit was booked over the days it was in the fleet and fit to hire, so a broken machine neither flatters nor punishes it. Each branch shows about 20 to 24 percent over the season the seed writes. Gross contribution is never called profit, because the system carries no overheads. |
| 3 | Download CSV and open it | The first line repeats both definitions. A cell a spreadsheet would run as a formula is escaped, and a negative amount stays a number so the owner can add it up. |
| 4 | Catalogue, search `BR-HILTI-TE1000AVR`, Edit, raise the daily rate, Save | The question says before anything is saved that bookings already made keep the rate they were booked at. Every booking copies its rates when it is made, and a test proves a booking at R280 stays at R280 after the rate goes to R310. Then I put the rate back the same way. |
| 5 | Asset register, Register a unit with the new tag, commission it, then retire it with a reason | A tag, its model and its branch never change once a unit is registered. Retiring is refused while a booking holds the unit, and the refusal names the booking. A retired unit keeps its row and its history and is never offered for hire again. |
| 6 | Users, add a counter assistant at Bellville, then deactivate them with a reason | Nobody sees a password, me included. The person chooses their own from a link, and the screen says this demonstration cannot deliver it to that address. Setting the password through the link also verifies their email. Deactivating revokes every session the person has, and the last administrator can never be deactivated or demoted. |
| 7 | Customer holds | Three no shows in twelve months put a customer on hold, and only the owner can release a hold, set one or blacklist a customer, each with a reason. A customer on hold is refused new bookings with one neutral refusal that names no cause. Releasing keeps the no show count. |
| 8 | Audit trail, newest first | Every change I just made is here, who made it, in what role and the values before and after. Nobody can change this trail, the owner included. The database role the application uses cannot update or delete an event, and a test tries both. |
| 9 | Sign out | |

### GitHub, inside slide 9

| Step | What I open | What I say |
|---|---|---|
| 1 | The branch list | Every branch is named after its issue, and I keep merged branches so the list shows the work. |
| 2 | A merged pull request, for example [#55](https://github.com/teon-artilionAI/toolshed-hire/pull/55) | The description says what changed, why, how I checked it by hand and what I found in my own review. Both required checks passed before it merged. |
| 3 | The Actions page | Fast checks on every push, integration checks on every pull request, and staging on every merge, followed by the header and TLS check and the three journeys in a browser. The journeys keep no trace or video, because those would record the passwords. |
| 4 | The `v0.4.0` production deployment run | It waited for my approval, smoke tested the candidate revision, shifted the traffic only then, and checked the deployed headers and TLS last. |
| 5 | The rulesets and environments | The rules apply to me as well. Production only accepts version tags, and only after my approval. |
