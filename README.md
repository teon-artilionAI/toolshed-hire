# Toolshed Hire

Toolshed Hire is a rental management system for a fictional three-branch tool
and equipment hire business in Cape Town. I am designing and building it as my
single-student project for INSY7315 Work Integrated Learning.

## The problem

The business manages bookings through a paper diary and a WhatsApp group.
That makes it possible to promise the same tool twice for overlapping dates,
forces staff to phone other branches to locate equipment, and leaves the owner
without reliable utilisation information.

## What the system does

- A public catalogue with availability searches across a date range and all
  three branches
- Reservations against individually tagged physical assets, with overlapping
  allocations refused by the database itself
- Counter workflows for checkout, returns, condition inspections and damage
  recording
- Deposit, late-fee and return-settlement calculations
- Utilisation and gross-contribution reporting for each asset
- Three permission levels, which are Customer, Counter Staff and Admin. The
  owner uses the Admin role.

## Where it stands

I am building this in stages, and this section says what is real today.

| Part | State |
|---|---|
| Design document | Submitted for Task 1. The final copy is in [`docs/task1`](docs/task1). |
| Prototype | All 24 screens exist in `frontend/` and run on fixture data. |
| API | A walking skeleton. It signs a user in, enforces roles, and allocates tagged assets against PostgreSQL with the overlap constraint. |
| Hosting | Live. Production is at <https://toolshed-hire.vercel.app> and is released from version tags. Staging follows `develop` at <https://toolshed-hire-staging.vercel.app>. |

The Task 2 build replaces the fixture data screen by screen and takes the system
live. Each piece of that work is an issue with its own branch, and the
[milestones](https://github.com/teon-artilionAI/toolshed-hire/milestones) show
the order. [`CHANGELOG.md`](CHANGELOG.md) records what each release added.

## Technology

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLModel, Python 3.12 |
| Database | PostgreSQL on Neon |
| Migrations | Alembic |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS |
| API hosting | Google Cloud Run |
| Frontend hosting | Vercel |
| CI/CD | GitHub Actions |

The frontend proxies `/api/*` to Cloud Run through a Vercel rewrite. The
browser therefore communicates with one origin, which keeps the session
cookie same-origin. The build uses the available free allowances where
appropriate, while the production cost model treats commercial hosting as a
paid service where the vendor terms require it.

## Repository layout

```text
backend/     FastAPI application, migrations and automated tests
frontend/    React application and browser-facing assets
infra/       Deployment configuration and operational instructions
docs/        Project evidence and supporting assets
.github/     Workflows, pull request template and issue forms
```

The assessment document is maintained separately and is added to the
repository only when the submission copy is final.

## Development

The backend and frontend each have their own README with setup and test
instructions. [`CONTRIBUTING.md`](CONTRIBUTING.md) describes the branch model,
the checks every change goes through and how a release is made.
