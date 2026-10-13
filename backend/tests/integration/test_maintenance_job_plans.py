"""The two maintenance jobs stand on their indexes, on the seeded database (#113, #90).

The monthly anonymisation reads a page of dormant customers in the order of
their key. Its plan has to walk `ix_customer_profile_identified`, which holds
the profiles not anonymised, and reach a customer's bookings and hires
through the indexes the reads of one customer already use, so a page costs the
profiles it walks past and never a scan of the bookings or hires.

The weekly pruning deletes a batch of expired refresh sessions, oldest first.
Its plan has to read `ix_refresh_session_expires_at` and stop at the batch.

The seed holds a few dozen customers, and on so few rows the planner reads
whatever is nearest. So the plan of the anonymisation is asked of the seed and
twenty thousand more customers registered years ago, three in four of them
anonymised already, as they will be once the job has run for some years, and
a settled hire for each of the rest, half of them recent. The rows are
written, analysed and planned inside one transaction, which is rolled back, so
no other test sees them. The planner chooses freely, with nothing switched off.

The pruning is asked with sequential scans switched off for the transaction,
as the other index tests do, because the seed holds no refresh session.
"""

from __future__ import annotations

from typing import Final

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import Executable

from app.application.identity.session_pruning import expired_session_cutoff
from app.domain.anonymisation import dormancy_cutoff
from app.infrastructure.dormant_customers import dormant_customers_statement
from app.infrastructure.schema_ddl import (
    CUSTOMER_IDENTIFIED_INDEX,
    REFRESH_SESSION_EXPIRY_INDEX,
)
from app.infrastructure.session_pruning import expired_sessions_statement
from seeding import SeedTally
from tests.support.clock import FixedClock

pytestmark = [pytest.mark.postgres, pytest.mark.usefixtures("seeded")]

NOW = FixedClock().now()
PAGE: Final[int] = 100
NO_SEQUENTIAL_SCAN: Final[str] = "SET LOCAL enable_seqscan = off"
ANALYSED_TABLES: Final[str] = (
    "ANALYZE customer_profile, user_account, reservation, rental, charge, refresh_session"
)
MORE_CUSTOMERS: Final[int] = 20_000
# One customer in this many of the extra ones is not anonymised.
STILL_KNOWN_EVERY: Final[int] = 4
INSERT_CUSTOMERS = text(
    "INSERT INTO customer_profile (id, customer_type, display_name, id_document_type, "
    "id_document_last4, contact_phone, billing_address_line1, billing_suburb, billing_city, "
    "billing_postal_code, account_status, registered_branch_id, created_at, anonymised_at) "
    "SELECT gen_random_uuid(), 'INDIVIDUAL', 'Planned customer ' || n, 'SA_ID', '1234', "
    "'021 555 0100', '1 Long Street', 'Gardens', 'Cape Town', '8001', 'ACTIVE', "
    "(SELECT id FROM branch ORDER BY code LIMIT 1), "
    "now() - interval '3 years' - n * interval '1 hour', "
    "CASE WHEN n % :every <> 0 THEN now() END "
    "FROM generate_series(1, :count) AS n"
)
INSERT_BOOKINGS = text(
    "INSERT INTO reservation (id, reference, customer_profile_id, branch_id, start_date, "
    "end_date, status, subtotal_ex_vat, vat_amount, deposit_total, estimated_total_inc_vat, "
    "created_by_user_id, created_at) "
    "SELECT gen_random_uuid(), 'TSH-P-' || lpad(n::text, 8, '0'), id, registered_branch_id, "
    "date '2023-01-02', date '2023-01-05', 'RETURNED', 0, 0, 0, 0, "
    "(SELECT id FROM user_account WHERE role = 'ADMIN' ORDER BY email LIMIT 1), "
    "CASE WHEN n % 2 = 0 THEN timestamptz '2026-01-02 08:00+02' "
    "ELSE timestamptz '2023-01-02 08:00+02' END "
    "FROM (SELECT id, registered_branch_id, row_number() OVER () AS n FROM customer_profile "
    "WHERE anonymised_at IS NULL AND display_name LIKE 'Planned customer %') AS known"
)
INSERT_HIRES = text(
    "INSERT INTO rental (id, reference, reservation_id, branch_id, status, checked_out_at, "
    "checked_out_by_user_id, due_back_on, returned_at, deposit_held, settled_at) "
    "SELECT gen_random_uuid(), 'TSH-Q-' || lpad(row_number() OVER ()::text, 8, '0'), id, "
    "branch_id, 'SETTLED', created_at, created_by_user_id, end_date, "
    "created_at + interval '3 days', 0, created_at + interval '3 days' "
    "FROM reservation WHERE reference LIKE 'TSH-P-%'"
)
# The index the bookings of one customer are probed through.
BOOKINGS_OF_A_CUSTOMER: Final[str] = "ix_reservation_customer_start"
# The tables that grow with every customer and every hire, none of which a
# page may read from end to end.
GROWING_TABLES: Final[tuple[str, ...]] = ("customer_profile", "reservation", "rental")


def explained(connection: Connection, statement: Executable) -> str:
    """Return the plan PostgreSQL gives a statement on this connection."""
    compiled = statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"render_postcompile": True}
    )
    lines = connection.exec_driver_sql(f"EXPLAIN {compiled}", compiled.params).all()
    return "\n".join(str(line[0]) for line in lines)


def test_the_seed_has_customers_and_hires_to_plan_over(seeded: SeedTally) -> None:
    assert seeded.total_created > 0


def test_a_page_of_dormant_customers_walks_the_index_of_profiles_not_anonymised(
    postgres_engine: Engine,
) -> None:
    statement = dormant_customers_statement(dormancy_cutoff(NOW), after=None, limit=PAGE)
    with postgres_engine.connect() as connection, connection.begin() as transaction:
        connection.execute(INSERT_CUSTOMERS, {"every": STILL_KNOWN_EVERY, "count": MORE_CUSTOMERS})
        connection.execute(INSERT_BOOKINGS)
        connection.execute(INSERT_HIRES)
        connection.execute(text(ANALYSED_TABLES))
        plan = explained(connection, statement)
        transaction.rollback()
    assert CUSTOMER_IDENTIFIED_INDEX in plan, plan
    assert BOOKINGS_OF_A_CUSTOMER in plan, plan
    for grown in GROWING_TABLES:
        assert f"Seq Scan on {grown} " not in plan, plan


def test_a_batch_of_expired_sessions_is_read_from_the_expiry_index(
    postgres_engine: Engine,
) -> None:
    statement = expired_sessions_statement(expired_session_cutoff(NOW), PAGE)
    with postgres_engine.connect() as connection, connection.begin() as transaction:
        connection.execute(text(ANALYSED_TABLES))
        connection.execute(text(NO_SEQUENTIAL_SCAN))
        plan = explained(connection, statement)
        transaction.rollback()
    assert REFRESH_SESSION_EXPIRY_INDEX in plan, plan
    assert "Limit" in plan, plan
    assert "Seq Scan" not in plan, plan
