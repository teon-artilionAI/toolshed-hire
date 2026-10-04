"""An administrator setting a customer's standing, and listing customers by it (BR-18).

Any standing may move to any other with a reason of five to two hundred
characters, which the audit event keeps beside the standing before and after.
Releasing a hold changes the standing and nothing else, so the count of
bookings not collected stays. Asking for the standing a customer has writes
nothing. The list passes the standing and the text on and is bounded. The
invitation a new member of staff is sent carries the reset link.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.application.identity.account_mail import INVITATION_KIND, AccountMailer
from app.application.identity.customer_directory import CustomerPage, CustomerSummary
from app.application.identity.customer_listing import (
    CustomerListRequest,
    CustomerListSearch,
    ReadCustomerList,
)
from app.application.identity.customer_standing import (
    CUSTOMER_STATUS_CHANGED_ACTION,
    ChangeCustomerStandingCommand,
    ChangeCustomerStandingUseCase,
)
from app.application.refusal import refused_parameter_of
from app.domain.account_messages import (
    INVITATION_SUBJECT,
    password_reset_link,
    staff_invitation_message,
)
from app.domain.customer_standing import standing_change
from app.domain.enums import AccountStatus, CustomerType, IdDocType, UserRole
from app.domain.errors import NotFound, ValidationFailure
from app.domain.identity import Actor
from app.infrastructure.notification import FakeEmailGateway
from tests.support.clock import FixedClock
from tests.support.memory_staff import MemoryStaffUnitOfWork, StaffStore, StoreFault

ADMINISTRATOR = Actor(user_id=uuid4(), role=UserRole.ADMIN)
REASON = "Paid what was owed and promised to collect on time."
ORIGIN = "https://toolshed-hire.example.test"


def a_customer(status: AccountStatus = AccountStatus.ON_HOLD) -> CustomerSummary:
    """Return a customer with three bookings not collected."""
    return CustomerSummary(
        id=uuid4(),
        display_name="Nomsa Dlamini",
        email="nomsa.dlamini@example.co.za",
        phone="082 441 7719",
        has_login=True,
        email_verified=True,
        customer_type=CustomerType.INDIVIDUAL,
        company_name=None,
        id_document_type=IdDocType.SA_ID,
        id_document_last4="4189",
        billing_suburb="Salt River",
        billing_city="Cape Town",
        account_status=status,
        trade_discount_percent=Decimal("0.00"),
        no_show_count=3,
        home_branch_code="CBD",
    )


def change(
    store: StaffStore, customer_id: UUID, status: AccountStatus, reason: str = REASON
) -> CustomerSummary:
    """Set the standing of a customer as an administrator."""
    use_case = ChangeCustomerStandingUseCase(MemoryStaffUnitOfWork(store), FixedClock())
    return use_case.execute(
        ChangeCustomerStandingCommand(
            actor=ADMINISTRATOR,
            customer_profile_id=customer_id,
            account_status=status,
            reason=reason,
        )
    )


class TestTheRule:
    """Every pairing is allowed, with a reason, and the same standing changes nothing."""

    @pytest.mark.parametrize("before", list(AccountStatus))
    @pytest.mark.parametrize("after", list(AccountStatus))
    def test_every_pairing_of_standings_is_allowed(
        self, before: AccountStatus, after: AccountStatus
    ) -> None:
        moved = standing_change(before, after, f"  {REASON}  ")
        assert (moved.reason, moved.changes_anything) == (REASON, before is not after)

    @pytest.mark.parametrize("reason", ["", "Paid", "x" * 201])
    def test_a_reason_out_of_bounds_is_refused(self, reason: str) -> None:
        with pytest.raises(ValidationFailure):
            standing_change(AccountStatus.ON_HOLD, AccountStatus.ACTIVE, reason)


class TestSettingTheStanding:
    """The standing changes with its audit event, and the count of no shows stays."""

    def test_releasing_a_hold_keeps_the_count_of_no_shows_and_is_recorded(self) -> None:
        held = a_customer()
        store = StaffStore(customers={held.id: held})
        summary = change(store, held.id, AccountStatus.ACTIVE)
        assert (summary.account_status, summary.no_show_count) == (AccountStatus.ACTIVE, 3)
        assert store.standing_of(held.id) is AccountStatus.ACTIVE
        event = store.events[-1]
        assert (event.action, event.entity_type, event.entity_id) == (
            CUSTOMER_STATUS_CHANGED_ACTION,
            "customer_profile",
            held.id,
        )
        assert (event.before_state, event.after_state) == (
            {"account_status": "ON_HOLD"},
            {"account_status": "ACTIVE", "reason": REASON},
        )
        assert event.actor_user_id == ADMINISTRATOR.user_id

    @pytest.mark.parametrize("wanted", [AccountStatus.ON_HOLD, AccountStatus.BLACKLISTED])
    def test_a_customer_in_good_standing_is_put_on_hold_or_blacklisted(
        self, wanted: AccountStatus
    ) -> None:
        customer = a_customer(AccountStatus.ACTIVE)
        store = StaffStore(customers={customer.id: customer})
        assert change(store, customer.id, wanted).account_status is wanted

    def test_the_standing_a_customer_has_writes_nothing(self) -> None:
        held = a_customer()
        store = StaffStore(customers={held.id: held})
        assert change(store, held.id, AccountStatus.ON_HOLD).account_status is (
            AccountStatus.ON_HOLD
        )
        assert store.journal == []

    def test_a_customer_nobody_registered_is_not_found(self) -> None:
        with pytest.raises(NotFound):
            change(StaffStore(), uuid4(), AccountStatus.ACTIVE)

    def test_a_reason_out_of_bounds_is_refused_naming_it_and_nothing_changes(self) -> None:
        held = a_customer()
        store = StaffStore(customers={held.id: held})
        with pytest.raises(ValidationFailure) as error:
            change(store, held.id, AccountStatus.ACTIVE, reason="ok")
        assert refused_parameter_of(error.value) == "reason"
        assert store.journal == []

    def test_an_audit_event_that_cannot_be_written_keeps_the_hold(self) -> None:
        held = a_customer()
        store = StaffStore(customers={held.id: held}, fail_audit=True)
        with pytest.raises(StoreFault):
            change(store, held.id, AccountStatus.ACTIVE)
        assert store.standing_of(held.id) is AccountStatus.ON_HOLD


class _Listing:
    """A listing that answers one page and remembers what it was asked."""

    def __init__(self) -> None:
        """Start with nothing asked."""
        self.asked: list[CustomerListSearch] = []

    def page(self, search: CustomerListSearch) -> CustomerPage:
        """Remember the search and answer one customer."""
        self.asked.append(search)
        return CustomerPage(
            items=(a_customer(),), page=search.page, page_size=search.page_size, total=1
        )


class TestTheList:
    """The list passes the standing and the text on, and a search is bounded."""

    def test_the_standing_and_the_text_reach_the_query(self) -> None:
        listing = _Listing()
        page = ReadCustomerList(listing).page(
            CustomerListRequest(
                actor=ADMINISTRATOR,
                status=AccountStatus.ON_HOLD,
                text="nomsa",
                page=2,
                page_size=10,
            )
        )
        assert page.total == 1
        (asked,) = listing.asked
        assert (asked.status, asked.text, asked.offset) == (AccountStatus.ON_HOLD, "nomsa", 10)

    @pytest.mark.parametrize(
        "changes",
        [{"text": "a"}, {"text": "x" * 81}, {"page": 0}, {"page_size": 0}, {"page_size": 101}],
    )
    def test_a_search_out_of_range_cannot_be_built(self, changes: dict[str, object]) -> None:
        values: dict[str, object] = {"status": None, "text": None, "page": 1, "page_size": 20}
        with pytest.raises(ValueError, match="Attempted to"):
            CustomerListSearch(**{**values, **changes})


class TestTheInvitation:
    """A new member of staff is sent the reset link every account uses."""

    def test_the_invitation_carries_the_reset_link_and_its_lifetime(self) -> None:
        message = staff_invitation_message(
            to="thandi@toolshedhire.co.za", frontend_origin=ORIGIN, token="made-up-token"
        )
        assert message.subject == INVITATION_SUBJECT
        assert password_reset_link(ORIGIN, "made-up-token") in message.text_body
        assert "60 minutes" in message.text_body
        assert f"{ORIGIN}/signin," in message.text_body

    def test_the_mailer_says_whether_the_gateway_took_it(self) -> None:
        accepting, refusing = FakeEmailGateway(), FakeEmailGateway(failure_reason="Down.")
        assert AccountMailer(accepting, ORIGIN).send_staff_invitation(to="a@b.co", token="t")
        assert not AccountMailer(refusing, ORIGIN).send_staff_invitation(to="a@b.co", token="t")
        assert INVITATION_KIND == "staff-invitation"
