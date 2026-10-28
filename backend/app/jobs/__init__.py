"""The maintenance jobs, which run outside the web process.

Each one is a module run as `python -m app.jobs.<name>`, so it runs from the
API image as a Cloud Run job with a different command, and from a developer's
machine the same way. Like the API layer, a job is a composition root. It puts
a use case together with its infrastructure and nothing imports it.

- `anonymise_customers` removes the personal details of customers nobody has
  heard from in two years (#113), monthly, as the application role.
- `prune_refresh_sessions` deletes the refresh sessions that expired more than
  ninety days ago (#90), weekly, as the operator role.

`infra/scripts/create-maintenance-jobs.sh` creates both jobs and their
schedules.
"""
