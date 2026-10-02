"""Shared test support.

Everything in here exists so that `conftest.py` stays readable and stays under
the file size limit. Four concerns are separated deliberately.

`sqlite_dialect` teaches SQLite enough about the PostgreSQL schema to create
the tables in memory. `factories` builds valid rows without every test
repeating the same twelve required columns. `tokens` mints access tokens the
way the application mints them. `pg` holds the PostgreSQL only helpers, so a
module that never touches a real database never imports them.

`roles` provisions the two restricted database roles and opens connections as
them, for the tests that prove what the application role may not do.

`log_capture` reads what the application wrote through its real log handler,
and `request_probe` adds a few routes to the real application for the tests of
the request middleware to aim at.

`clock` holds the clock that stands still, and `memory` holds an in memory unit
of work, so a use case can be tested with no database behind it.

`catalogue` gives the public read side a visitor's client and a few builders,
and `statements` counts what an engine is asked to run, for the tests that
prove a query does not loop.

`memory_identity` extends the in memory unit of work with accounts, refresh
sessions and throttle counters, and holds the two fakes that stand in for
bcrypt and the token signer. `identity_desk` wires the three session use cases
over it. `sessions` gives the session routes a client on a clock that stands
still, and reads and presents the refresh cookie.
"""
