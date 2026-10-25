"""Check that a staging audit event carries the browser's real client address.

Run inside the protected staging runner after the browser journeys. The runner
fetches its own public address and passes it here. The latest recent
`reservation.created` event must carry that same address, which proves the
Vercel function forwarded the client address and the API recorded it rather
than the function's private or egress address.

The database URL is read from the environment and is never printed. The check
only reads one row.
"""

from __future__ import annotations

import os
import sys
from ipaddress import ip_address

import psycopg

QUERY = """
SELECT id, action, request_id, ip_address
FROM audit_event
WHERE action = 'reservation.created'
  AND ip_address IS NOT NULL
  AND occurred_at > now() - interval '30 minutes'
ORDER BY id DESC
LIMIT 1
"""


def fail(message: str) -> int:
    """Print the failure and return the shell status."""
    print(f"audit_ip FAIL: {message}", file=sys.stderr)
    return 1


def main() -> int:
    """Read the latest event and compare its address with the runner."""
    if len(sys.argv) != 2:
        print("usage: check_staging_audit_ip.py <expected-client-ip>", file=sys.stderr)
        return 2

    try:
        expected = ip_address(sys.argv[1].strip())
    except ValueError:
        return fail("the expected client address is not an IP address")

    database_url = os.environ.get("STAGING_DATABASE_URL", "")
    if database_url == "":
        return fail("STAGING_DATABASE_URL is not set")

    with psycopg.connect(database_url, connect_timeout=15) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute(QUERY)
            row = cursor.fetchone()

    if row is None:
        return fail("no recent reservation.created audit event with a client address")

    event_id, action, request_id, stored = row
    try:
        actual = ip_address(str(stored))
    except ValueError:
        return fail("the stored client address is not an IP address")

    if not actual.is_global:
        return fail(f"the stored address is not globally routable (event {event_id})")

    if actual != expected:
        print(
            f"audit_ip FAIL: event {event_id} stored {actual}, expected {expected}",
            file=sys.stderr,
        )
        return 1

    print(
        f"audit_ip event_id={event_id} action={action} request_id={request_id} "
        f"family=IPv{actual.version} global=true match=true"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
