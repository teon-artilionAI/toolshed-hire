"""Registering a customer, with no database (FR-01, US-01, BR-45, R-13).

A new address gets an account, a profile at the chosen branch and a link that
proves the address, written together with one audit event. An address that
already has an account gets nothing new, its holder gets a note with no token,
and the caller cannot tell the two apart by the answer or by the work done.

The use case runs over the in memory stores with a fake gateway and a hasher
that counts, so every path can be asked how many hashes it ran and how many
messages it sent.
"""

from __future__ import annotations

from typing import Final

import pytest

from app.application.identity.attempts import AccountThrottleRules
from app.application.identity.register import REGISTERED_ACTION, REGISTRATION_REPEATED_ACTION
from app.application.refusal import refused_parameter_of
from app.domain.account_messages import ALREADY_REGISTERED_SUBJECT, VERIFICATION_SUBJECT
from app.domain.account_tokens import EMAIL_VERIFICATION_LIFETIME, hash_account_token
from app.domain.enums import AccountStatus, CustomerType, IdDocType, UserRole
from app.domain.errors import TooManyAttempts, ValidationFailure
from app.infrastructure.notification import UnconfiguredEmailGateway
from tests.support.account_desk import (
    CHOSEN_PASSWORD,
    FRONTEND_ORIGIN,
    NEW_EMAIL,
    VERIFY_KEY,
    AccountDesk,
    registration,
)
from tests.support.memory import StoreFault
from tests.support.memory_crypto import fake_hash
from tests.support.memory_identity import KNOWN_EMAIL

STRICT_LIMIT: Final[int] = 2


@pytest.fixture
def desk() -> AccountDesk:
    return AccountDesk()


class TestANewAddress:
    """An account, a profile, an audit event and a verification link."""

    def test_the_account_is_an_unverified_customer_with_the_hash_of_the_password(
        self, desk: AccountDesk
    ) -> None:
        account = desk.registered()
        assert account.role is UserRole.CUSTOMER
        assert account.is_active
        assert not account.email_verified
        assert account.password_hash == fake_hash(CHOSEN_PASSWORD)
        assert (account.full_name, account.phone) == ("Thandi Mokoena", "082 441 7719")

    def test_the_address_is_kept_in_lower_case(self, desk: AccountDesk) -> None:
        desk.register(email="  Thandi.Mokoena@Example.co.za ")
        assert desk.account_for(NEW_EMAIL).email == NEW_EMAIL

    def test_the_profile_is_an_individual_in_good_standing_at_the_home_branch(
        self, desk: AccountDesk
    ) -> None:
        account = desk.registered()
        profile = desk.read_profile(account.id)
        assert profile.customer_type is CustomerType.INDIVIDUAL
        assert profile.account_status is AccountStatus.ACTIVE
        assert profile.trade_discount_percent == 0
        assert profile.home_branch_code == desk.branch.code
        assert (profile.id_document_type, profile.id_document_last4) == (IdDocType.SA_ID, "5083")
        assert profile.billing_city == "Cape Town"

    def test_the_link_in_the_message_proves_the_address(self, desk: AccountDesk) -> None:
        expectation = desk.register()
        (message,) = desk.gateway.sent_to(NEW_EMAIL)
        assert message.subject == VERIFICATION_SUBJECT
        assert f"{FRONTEND_ORIGIN}/register#verify=" in message.text_body
        token = desk.sent_token(VERIFY_KEY)
        pending = desk.account_for().email_verification
        assert pending is not None
        assert pending.token_hash == hash_account_token(token)
        assert pending.expires_at == desk.clock.now() + EMAIL_VERIFICATION_LIFETIME
        assert expectation.email_deliverable is True

    def test_one_audit_event_names_the_new_account(self, desk: AccountDesk) -> None:
        account = desk.registered()
        (event,) = desk.audit(REGISTERED_ACTION)
        assert event.entity_id == account.id
        assert event.actor_user_id == account.id
        assert event.after_state is not None
        assert event.after_state["home_branch_code"] == desk.branch.code
        assert event.after_state["email_verified"] is False

    def test_an_audit_event_that_cannot_be_written_leaves_neither_account_nor_profile(
        self, desk: AccountDesk
    ) -> None:
        desk.store.fail_audit = True
        with pytest.raises(StoreFault):
            desk.register()
        assert desk.identity.committed.accounts == {}
        assert desk.identity.committed.details == {}
        assert desk.gateway.sent == []

    def test_the_password_is_left_out_of_the_representation_of_the_command(self) -> None:
        assert CHOSEN_PASSWORD not in repr(registration())


class TestAnAddressThatAlreadyHasAnAccount:
    """Nothing new is written, the holder is told, and the caller learns nothing."""

    @pytest.fixture
    def holder(self, desk: AccountDesk) -> None:
        desk.identity.add_account(email=NEW_EMAIL)

    @pytest.mark.usefixtures("holder")
    def test_no_account_and_no_profile_are_written(self, desk: AccountDesk) -> None:
        before = desk.account_for()
        desk.register()
        assert list(desk.identity.committed.accounts.values()) == [before]
        assert desk.identity.committed.details == {}

    @pytest.mark.usefixtures("holder")
    def test_the_holder_is_sent_a_note_with_no_token(self, desk: AccountDesk) -> None:
        desk.register()
        (message,) = desk.gateway.sent_to(NEW_EMAIL)
        assert message.subject == ALREADY_REGISTERED_SUBJECT
        assert "#" not in message.text_body

    @pytest.mark.usefixtures("holder")
    def test_the_attempt_is_written_to_the_audit_trail(self, desk: AccountDesk) -> None:
        desk.register()
        (event,) = desk.audit(REGISTRATION_REPEATED_ACTION)
        assert event.entity_id == desk.account_for().id
        assert event.actor_user_id is None
        assert desk.audit(REGISTERED_ACTION) == []

    def test_the_answer_and_the_work_are_the_same_either_way(self) -> None:
        fresh, taken = AccountDesk(), AccountDesk()
        taken.identity.add_account(email=NEW_EMAIL)
        answers = [fresh.register(), taken.register()]
        assert answers[0] == answers[1]
        assert fresh.hasher.call_count == taken.hasher.call_count == 1
        assert len(fresh.gateway.sent) == len(taken.gateway.sent) == 1
        assert len(fresh.store.committed.audit_events) == len(taken.store.committed.audit_events)

    def test_an_address_taken_at_the_moment_of_writing_is_answered_the_same(
        self, desk: AccountDesk
    ) -> None:
        desk.identity.address_taken_at_write = True
        expectation = desk.register()
        assert expectation.email_deliverable is True
        assert desk.identity.committed.accounts == {}
        assert desk.store.committed.audit_events == []
        (message,) = desk.gateway.sent
        assert message.subject == ALREADY_REGISTERED_SUBJECT


class TestTheFieldsThatAreRefused:
    """Each refusal names the field as the request named it, and nothing is written."""

    def refusal(self, desk: AccountDesk, **overrides: object) -> ValidationFailure:
        with pytest.raises(ValidationFailure) as refused:
            desk.register(**overrides)
        assert desk.identity.committed.accounts == {}
        assert desk.gateway.sent == []
        return refused.value

    def test_a_password_under_twelve_characters_is_refused_before_any_hash(
        self, desk: AccountDesk
    ) -> None:
        refused = self.refusal(desk, password="elevenchars")
        assert refused_parameter_of(refused) == "password"
        assert desk.hasher.call_count == 0

    def test_the_privacy_notice_has_to_be_accepted(self, desk: AccountDesk) -> None:
        refused = self.refusal(desk, accepts_privacy_notice=False)
        assert refused_parameter_of(refused) == "acceptsPrivacyNotice"

    def test_a_branch_that_does_not_trade_is_refused(self, desk: AccountDesk) -> None:
        refused = self.refusal(desk, home_branch_code="XYZ")
        assert refused_parameter_of(refused) == "homeBranchCode"

    @pytest.mark.parametrize(
        ("field", "value", "on_the_wire"),
        [
            ("full_name", " ", "fullName"),
            ("phone", "not a number", "phone"),
            ("id_document_last4", "508", "idDocumentLast4"),
            ("billing_postal_code", "80011-12345", "billingPostalCode"),
        ],
    )
    def test_a_detail_that_is_refused_is_named(
        self, desk: AccountDesk, field: str, value: str, on_the_wire: str
    ) -> None:
        refused = self.refusal(desk, **{field: value})
        assert refused_parameter_of(refused) == on_the_wire


class TestTheThrottle:
    """Counted for the address and for the client, before anything else is done."""

    def test_the_address_is_counted_whatever_the_client(self) -> None:
        desk = AccountDesk(
            account_rules=AccountThrottleRules().with_limits(
                register_per_email=STRICT_LIMIT,
                register_per_address=100,
                verification_per_address=100,
                resends_per_account=100,
                reset_requests_per_email=100,
                reset_requests_per_address=100,
                reset_completions_per_address=100,
            )
        )
        for _ in range(STRICT_LIMIT):
            desk.register(email=KNOWN_EMAIL)
        hashes_before = desk.hasher.call_count
        with pytest.raises(TooManyAttempts) as refusal:
            desk.register(email=KNOWN_EMAIL.upper())
        assert refusal.value.retry_after_seconds > 0
        assert desk.hasher.call_count == hashes_before
        desk.register()

    def test_the_client_is_counted_whatever_the_address(self) -> None:
        desk = AccountDesk()
        limit = desk.account_rules.register_address.limit
        for number in range(limit):
            desk.register(email=f"person{number}@example.co.za")
        with pytest.raises(TooManyAttempts):
            desk.register(email="one.more@example.co.za")
        assert len(desk.gateway.sent) == limit


class TestWhereNoMailIsDelivered:
    """The answer says so, and it says so for every address alike."""

    def test_an_environment_with_email_off_answers_that_nothing_is_delivered(self) -> None:
        desk = AccountDesk(gateway_override=UnconfiguredEmailGateway())
        assert desk.register().email_deliverable is False
        assert desk.account_for().email_verification is not None
