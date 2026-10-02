# Development workflow

This is a single-student project, so everything here describes how I work on
it. I use a reduced version of GitFlow, which is the model I set out in the
DevOps section of the Task 1 document.

## Branches

| Branch | What it is for | Cut from | Merges into |
|---|---|---|---|
| `main` | Released states only. This is what is deployed to production and what gets marked. | | |
| `develop` | Integration. Every change lands here first and is deployed to staging. | `main` | `main`, through a release |
| `feature/nnn-slug` | Application code for one issue | `develop` | `develop` |
| `docs/nnn-slug` | Documentation only | `develop` | `develop` |
| `test/nnn-slug` | Tests only. A fix to production code goes on a feature branch. | `develop` | `develop` |
| `release/x.y.z` | Version bump, changelog and last checks before a release | `develop` | `main` |
| `hotfix/nnn-slug` | An urgent fix to something already released | `main` | `main` and `develop` |

`nnn` is the number of the GitHub issue the branch belongs to, so a branch, its
pull request and its commits can always be traced back to the reason for the
work. The release that closes Task 2 is named `release/task-2`.

`main` and `develop` are protected. Nothing reaches either of them without a
pull request and passing checks, force pushes and deletion are blocked, and the
rule applies to me as the repository owner too.

## How a change moves

1. I open an issue that states the outcome, the acceptance criteria and the
   requirement, user story and business rule identifiers it covers.
2. I cut a branch from `develop` and name it after the issue.
3. I push early and open a draft pull request, so the fast checks run on every
   push from the start.
4. When the work meets the acceptance criteria I read the whole diff on GitHub,
   mark the pull request ready and wait for the integration checks.
5. I merge with a merge commit. Squash and rebase merging are switched off, so
   the history shows each branch as it was built.
6. The merge into `develop` deploys to staging, where I check the change by
   hand.

A branch is merged within three working days of being cut. If it is taking
longer than that, the issue was too big and I split it.

I keep merged branches until the task they belong to has been marked, so the
branch list shows the work, and I prune them after that. The pull requests and
merge commits are the permanent record either way.

## Releases

A release takes whatever is on `develop` to production.

1. I check `develop` on the staging environment.
2. I cut `release/x.y.z` from `develop`, merge the current `main` into it, bump
   the version numbers and move the entries in `CHANGELOG.md` under the new
   version.
3. I open a pull request into `main`. Its description lists the issues the
   release closes.
4. After the checks pass I merge it and put an annotated tag `vX.Y.Z` on the
   merge commit.
5. The tag starts the production deployment, which waits for my approval before
   it touches anything.
6. I open a pull request from `main` into `develop` so both branches share the
   release commit.

Tags are never moved. If a deployment fails and the source has not changed, I
run the same deployment again. If the source needs a fix, the fix gets a new
patch version.

Submission tags such as `task2-v1.0` mark the state I hand in. They deploy
nothing.

## Review

I am the only person on this project, so I do not claim a second-person
approval anywhere. The automated checks are the review gate that repeats the
same way every time. On top of that I read every diff on GitHub before I mark a
pull request ready, and I write down what I checked by hand in the pull request.
Documentation changes get a second read on a later day before they merge.

## Checks

| When | What runs |
|---|---|
| Every push | Secret scan, linting, strict type checks, the layer import contract, and the unit and component tests for the backend and the frontend |
| Every pull request | Migrations from an empty database, PostgreSQL integration tests, the coverage floor on the domain and application layers, dependency audits, the production build, and the browser and accessibility tests |
| Merge into `develop` | Deployment to staging |
| Release tag on `main` | Deployment to production |

The commands to run the same checks locally are in the backend and frontend
READMEs.

## Commit messages

I use Conventional Commit subjects. The subject says why the change is needed,
and the body adds context when the reason is not clear from the diff. A trailer
names the issue.

```text
feat: reject overlapping asset allocations at the database level

Refs #2
```

Other subjects in the same style:

```text
fix: release allocation rows when a reservation is cancelled
docs: clarify the production deployment requirements
test: cover late-fee accrual across a month boundary
```

I keep commits small. One commit is one logical change.

## Files I never commit

I never commit secrets, credentials, API keys, service-account JSON files or
`.env` files. I check `git status` before staging. `.gitignore` and the secret
scan are safeguards, not a replacement for that check.

The module manual is copyright of The Independent Institute of Education and is
not in this repository.

## Assessment document

I keep the working assessment document outside the repository while editing
it. I add only the final submission copy after I have checked its content,
formatting and declaration.
