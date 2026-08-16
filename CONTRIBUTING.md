# Development workflow

This is a single-student project. I keep `main` as the stable branch and use a
short-lived branch when a future change is large enough to benefit from an
isolated review and test cycle.

## Before I make a change

I start with a clear outcome and acceptance criteria. I read the existing code
before editing it, keep the change focused, and avoid unrelated refactoring.

## Checks

I run the checks that cover the area I changed before merging or publishing a
change. The repository's automated checks include linting, type checking,
backend tests, frontend tests and PostgreSQL integration coverage.

Because I am the only project member, I do not claim a second-person approval.
Automated checks provide the repeatable review gate, and I record any manual
verification in the relevant change description.

## Commit messages

I use Conventional Commit subjects. The subject explains why the change is
needed, and the body adds context when the reason is not clear from the diff.

```text
feat: reject overlapping asset allocations at the database level
fix: release allocation rows when a reservation is cancelled
docs: clarify the production deployment requirements
test: cover late-fee accrual across a month boundary
```

## Files I never commit

I never commit secrets, credentials, API keys, service-account JSON files or
`.env` files. I check `git status` before staging; `.gitignore` is a safeguard,
not a replacement for that review.

## Assessment document

I keep the working assessment document outside the repository while editing
it. I add only the final submission copy after I have checked its content,
formatting and declaration.
