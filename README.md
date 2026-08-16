# Toolshed Hire

Toolshed Hire is a rental management system for a fictional three-branch tool
and equipment hire business. I designed and built it as my single-student
project for INSY7315 Work Integrated Learning.

## The problem

The business manages bookings through a paper diary and a WhatsApp group.
That makes it possible to promise the same tool twice for overlapping dates,
forces staff to phone other branches to locate equipment, and leaves the owner
without reliable utilisation information.

## What I built

- A public catalogue with availability searches across a date range and all
  three branches
- Reservations against individually tagged physical assets, preventing
  overlapping allocations at the database level
- Counter workflows for checkout, returns, condition inspections and damage
  recording
- Deposit, late-fee and return-settlement calculations
- Utilisation and gross-contribution reporting for each asset
- Three permission levels: Customer, Counter Staff and Admin, with the owner
  using the Admin role

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
cookie same-origin. The prototype uses the available free allowances where
appropriate, while the production cost model treats commercial hosting as a
paid service where the vendor terms require it.

## Repository layout

```text
backend/     FastAPI application, migrations and automated tests
frontend/    React application and browser-facing assets
infra/       Deployment configuration and operational instructions
docs/        Project evidence and supporting assets
.github/     Continuous-integration and deployment workflows
```

The assessment document is maintained separately and is added to the
repository only when the submission copy is final.

## Development

The backend and frontend each have their own README with setup and test
instructions. [CONTRIBUTING.md](CONTRIBUTING.md) records the workflow I use for
future changes.
