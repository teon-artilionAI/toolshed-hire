"""The client address a request is remembered with.

The audit trail records where a request came from when the server knows. The
server reports the peer as text, and behind a proxy that text comes from a
forwarding header the caller can influence. So it is parsed, and anything that
is not an IP address is dropped instead of being stored.
"""

from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address

import pytest

from app.request_context import (
    RequestContext,
    bind_request_context,
    current_client_address,
    release_request_context,
    resolve_client_address,
)

REQUEST_ID = "6f1c2b9e-3d4a-4c5b-8e7f-0a1b2c3d4e5f"


class TestResolvingTheAddress:
    """Text in, an address or nothing out."""

    def test_an_ipv4_address_is_kept(self) -> None:
        assert resolve_client_address("203.0.113.9") == IPv4Address("203.0.113.9")

    def test_an_ipv6_address_is_kept(self) -> None:
        assert resolve_client_address("2001:db8::17") == IPv6Address("2001:db8::17")

    def test_surrounding_space_is_ignored(self) -> None:
        assert resolve_client_address("  203.0.113.9 ") == IPv4Address("203.0.113.9")

    @pytest.mark.parametrize(
        "candidate",
        [None, "", "testclient", "203.0.113.9, 198.51.100.4", "203.0.113.999", "<script>"],
    )
    def test_anything_that_is_not_one_address_is_dropped(self, candidate: str | None) -> None:
        assert resolve_client_address(candidate) is None


class TestReadingItBack:
    """The audit trail reads the address of the request being served."""

    def test_outside_a_request_there_is_no_address(self) -> None:
        assert current_client_address() is None

    def test_inside_a_request_it_is_the_address_the_context_was_given(self) -> None:
        address = IPv4Address("203.0.113.9")
        token = bind_request_context(RequestContext(request_id=REQUEST_ID, client_address=address))
        try:
            assert current_client_address() == address
        finally:
            release_request_context(token)
        assert current_client_address() is None

    def test_a_request_with_no_known_address_reports_none(self) -> None:
        token = bind_request_context(RequestContext(request_id=REQUEST_ID))
        try:
            assert current_client_address() is None
        finally:
            release_request_context(token)
