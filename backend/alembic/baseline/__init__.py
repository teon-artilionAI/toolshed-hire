"""The frozen definitions behind migration 0001.

The baseline creates seventeen tables, which is far too much for one versions
file to stay readable, so the revision itself is a short orchestrator and the
definitions live here, one module per subject area.

Everything in this package is a snapshot. It imports nothing from `app`, on
purpose. The SQLModel classes and the application constants keep changing as
the system grows, and a migration that read them would quietly change what it
creates every time they did. A later change to the schema is a new revision,
never an edit in here.

`prerequisites` holds the extensions and the enumerated types that have to
exist before any table can. `columns` holds the column builders the table
modules share. The five subject areas are `identity`, `catalogue`, `booking`,
`hire` and `evidence`, and each one exposes `create()` and `drop()`.
"""
