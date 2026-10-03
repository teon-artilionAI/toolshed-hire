# Presentation outline

The recorded presentation of Task 2 runs for about twelve to fifteen minutes.
<!-- final: check the time limit --> It is a walk through the slides below with
a live demonstration on production in the middle. The script for the
demonstration follows the slides.

<!-- final: link the slides file and the video once they exist -->

| Part | Slides | Time |
|---|---|---|
| The problem and the requirements | 1 to 4 | 2:30 |
| How it is built | 5 to 8 | 4:00 |
| How it is delivered | 9 and 10 | 2:15 |
| Live demonstration | 11 | 4:00 |
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
drive everything that follows, and the first one, double booking, is the one
the database itself now prevents.

### 3. What Task 2 delivers

- The customer journey, from the catalogue to a confirmed booking
- The counter journey, from a walk-in to checkout, return and deposit settlement
- Late fees from one policy and a deposit settled at the counter
- Two environments, deployed by the pipeline only
- <!-- final: the admin and reporting screens if 017 to 021 are in -->

**Notes.** I say plainly what is built and what is still on sample data. Every
screen that is not on the API yet says so on the screen itself, so nothing
pretends to work.

### 4. Requirements and how they are traced

- 28 functional and 18 non-functional requirements from Task 1
- Issue, then branch `feature/nnn-slug`, then pull request, then merge commit
- The traceability table in the README gives the status, the pull request, the
  screens and the tests for every requirement
- <!-- final: the counts of built, partly built and planned -->

**Notes.** I open the README on GitHub and scroll the traceability table. I pick
FR-07, no unit with two overlapping bookings, and follow it to the pull request
and to the test that proves it. I mention that the non-functional requirements
are mapped to how I verify each one in the test plan, honestly, including the
ones I have not verified yet.

### 5. Architecture

- Browser, Vercel, Cloud Run, Neon PostgreSQL and Resend, on one origin
- Four layers, domain, application, infrastructure and API
- Eight modules with the same name in every layer
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
- Strategy, the pricing policy and the late fee policy
- State, eight reservation states where every move is refused unless a state
  allows it

**Notes.** For each pattern I show the file and say the problem it solves here.
I point out that a test reads every module to prove that only the policy works
out a price or a late fee, so the rule cannot leak into other code later.

### 7. The database

- Seventeen tables, singular names, hand written migrations
- A `daterange` exclusion constraint, so PostgreSQL itself refuses an
  overlapping booking of one unit
- Composite keys, partial indexes and index use proven by tests
- Two roles, so the running application cannot change the schema or rewrite the
  audit trail

**Notes.** I show the constraint in the backend README. Periods are half open, so
a return on the twelfth frees the twelfth. I explain that the lock with
`SKIP LOCKED` lets concurrent bookings take different units, and the constraint
has the last word if anything gets past it.

### 8. Security

- Sessions with a fifteen minute token in memory and a rotating refresh cookie
- Deny by default, ownership answered as not found, branch scope for counter
  staff
- Lockout, throttles, security headers and no secret in the repository
- 44 controls, with their status in the evidence folder

**Notes.** I open the security controls file and say how many are in place,
partly in place and planned, and that I only marked a control in place where I
can point at the code or the test. I name the ones still open, which are the
photograph upload, reporting export, alerting and the incident procedure.

### 9. Pipeline and branching, a live look at GitHub

- Reduced GitFlow, `main`, `develop`, feature, docs, test, release and hotfix
  branches
- Fast checks on every push, integration checks on every pull request
- Two required checks, merge commits only, no bypass for anyone
- A ruleset that stops a release tag from being moved

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
  tested before it takes any traffic
- One instance at most and a budget alert, because this runs on a free trial

**Notes.** I show a production deployment run with its approval step and its
summary. I explain why the API sits in London beside the database, and that the
cold start is the price of scaling to zero.

### 11. Live demonstration

- The customer journey on production
- The counter journey, with checkout, return and the deposit
- The worked example from Task 1
- The owner's view

**Notes.** I follow the demonstration script below.

### 12. Testing

- Domain and application tests with no database, API tests, PostgreSQL 16
  integration tests, browser and accessibility tests
- 100 percent of lines covered in the domain and application layers, against a
  floor of 70
- Twenty holds at once for five units give exactly five holds
- <!-- final: the latest test counts -->

**Notes.** I show the test plan table and one concurrency test. I say what is not
verified yet, which is the load test, the volume test and the restore drill on
the deployment.

### 13. Deviations from the design

- Both environments capped at one instance
- Email in a restricted mode on this demonstration
- No scheduled availability checks, so the system can sleep
- A booking for today closes when the branch closes

**Notes.** I open the deviations file and give the reason for two or three of
them. I want it clear that each change was a decision with a reason and not
something that drifted.

### 14. What is left for Task 3

- <!-- final: whatever of 015 to 022 is not in task2-v1.0 -->
- The load, volume and cold start measurements, the restore drill and the
  usability sessions
- Alerting and the incident procedure
- Statement download, data export and the retention period
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
   database are awake. <!-- final: or show one cold start on purpose and time it -->
3. Sign out everywhere and empty the hire basket.
4. Have these tabs ready. The production site, the README on GitHub, the
   pull requests, the Actions page, a production deployment run, and the
   rulesets and environments in the repository settings.
5. Have the counter and admin logins to hand, off screen.

### Customer, about one and a half minutes

| Step | What I click | What I say |
|---|---|---|
| 1 | Open the catalogue home, pick dates from tomorrow and search | No account is needed to see what we hire and what it costs. |
| 2 | Point at the results, then choose Bellville as the branch | This one search replaces three phone calls. It says free or not free for each branch and never how many units there are. |
| 3 | Open a model | The rates, the deposit and the late fee are all here. The price is the server's quote, and the browser does no sum of its own. |
| 4 | Add it to the basket, open the basket and review | Reviewing needs an account, so the site sends me to sign in and brings me back. |
| 5 | Sign in as the demo customer, then Hold | Named units are now set aside for thirty minutes, and the countdown shows it. |
| 6 | Confirm | The booking has a reference. The confirmation email only reaches my own address on this demo. |
| 7 | My Hires, open the booking | The customer sees their own bookings only. Another customer's reference is answered as not found. |
| 8 | Cancel it | Cancelling releases the units in the same transaction. |
| 9 | Account, scroll to the hire history | This closed hire is the worked example from Task 1, with the deposit shown as held, kept and returned. |
| 10 | Sign out | |

### Counter, about two minutes

| Step | What I click | What I say |
|---|---|---|
| 1 | Sign in as the Cape Town CBD counter assistant | Counter staff land on today's dashboard for their own branch. |
| 2 | Point at the dashboard, then open the diary for this week | The diary replaces the paper one. It reads again whenever the window comes back into focus. |
| 3 | Customers, register a walk-in with a made up name | A walk-in has no login. Only the last four characters of the identity document are typed in. |
| 4 | New Booking for that customer, one unit for today, review, hold, confirm | The counter uses exactly the same booking path as a customer. The server allocates the unit and shows its tag to staff. |
| 5 | Check out now, tick the tag, keep the condition, sign the agreement, confirm | One transaction opens the hire, puts the unit on hire and takes the deposit. |
| 6 | Open the hire's return, tick the unit, take it back | Back before the due date means no late fee, so the deposit is released in full and nothing is due. |
| 7 | Locator, search `TSH-DR-0042` | Any unit at any branch, read only. This answers the second problem. |
| 8 | Open the return screen for `TSH-H-26-000098` | This is the worked example. R1,200.00 held, two days late at R120.00, R240.00 withheld, R960.00 released, R0.00 due. A test follows the same figures through the API on every pull request. |
| 9 | Overdue, then sign out | The overdue list shows each late unit with the fee so far, worked out by the one policy. |

<!-- final: check on production that the return screen shows the settlement of TSH-H-26-000098 -->

### Owner, about half a minute

<!-- final: write this once branches 017 to 021 are decided -->

| Step | What I click | What I say |
|---|---|---|
| 1 | Sign in as the administrator | The owner has the admin area and can work the counter at any branch. |
| 2 | Open the admin screens | <!-- final: what the admin screens show --> |
| 3 | Choose a branch and open its dashboard | An administrator chooses the branch for the tab, and counter staff never can. |
| 4 | Sign out | |

### GitHub, inside slide 9

| Step | What I open | What I say |
|---|---|---|
| 1 | The branch list | Every branch is named after its issue, and I keep merged branches until the task is marked. |
| 2 | A merged pull request, for example [#50](https://github.com/teon-artilionAI/toolshed-hire/pull/50) | The description says what changed, why, how I checked it by hand and what I found in my own review. Both required checks passed before it merged. |
| 3 | The Actions page | Fast checks on every push, integration checks on every pull request, staging on every merge. |
| 4 | A production deployment run | It waited for my approval, smoke tested the candidate revision, and only then shifted the traffic. |
| 5 | The rulesets and environments | The rules apply to me as well. Production only accepts version tags, and only after my approval. |
