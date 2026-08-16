"""Shared test support.

Everything in here exists so that `conftest.py` stays readable and stays under
the file size limit. Four concerns are separated deliberately.

`sqlite_dialect` teaches SQLite enough about the PostgreSQL schema to create
the tables in memory. `factories` builds valid rows without every test
repeating the same twelve required columns. `tokens` mints access tokens the
way the application mints them. `pg` holds the PostgreSQL only helpers, so a
module that never touches a real database never imports them.
"""
