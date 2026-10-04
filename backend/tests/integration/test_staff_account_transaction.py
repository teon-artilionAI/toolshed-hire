"""Each write of the people screens is one transaction on PostgreSQL (US-35, BR-48, BR-49).

A new account is opened, its holder chooses a password through the link they
were sent and signs in. A deactivation commits the account, the revocation of
every refresh session with `ADMIN_REVOKE` and its audit event together, after
which neither the password nor the refresh token works, and a reactivation
lets the password work again. A write whose audit event cannot be written
keeps nothing, so an account opened that way does not exist, a deactivation
leaves the account and its sessions as they were, and a release leaves the
hold. A demoted administrator's token is refused an admin route at once.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import status
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.application.identity.account_mail import AccountMailer
from app.application.identity.customer_standing import (
    ChangeCustomerStandingCommand,
    ChangeCustomerStandingUseCase,
)
from app.application.identity.staff_access import DeactivateStaffAccountUseCase
from app.application.identity.staff_accounts import OpenStaffAccountUseCase
from app.application.identity.staff_commands import (
    DeactivateStaffAccountCommand,
    OpenStaffAccountCommand,
)
from app.domain.enums import AccountStatus, RevokeReason, UserRole
from app.domain.identity import Actor
from app.infrastructure.models import (
    AuditEvent,
    Branch,
    CustomerProfile,
    RefreshSession,
    UserAccount,
)
from app.infrastructure.notification import FakeEmailGateway
from app.infrastructure.staff_query import SqlStaffDirectory
from tests.support.account_desk import RESET_KEY
from tests.support.accounts_api import RESET_COMPLETE_PATH, CachedBcryptHasher, token_from
from tests.support.admin_user_api import (
    STAFF_EMAIL,
    deactivate_user,
    edit_user,
    open_user,
    people_client,
    reactivate_user,
    staff_body,
)
from tests.support.booking import AuditWriteFailed, UnitOfWorkWithBrokenAudit
from tests.support.booking_api import BookingClient, answered, created
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.sessions import REFRESH_PATH, present, refresh_token_of, sign_in

pytestmark = pytest.mark.postgres

CHOSEN_PASSWORD = "a-made-up-passphrase-for-staff"
ORIGIN = "https://toolshed-hire.example.test"
REASON = "Left the business at the end of September."


@pytest.fixture
def branch(postgres_session: Session, postgres_factory: Factory) -> Branch:
    """Commit the CBD branch."""
    made = postgres_factory.branch(code="CBD")
    postgres_session.commit()
    return made


@pytest.fixture
def owner(postgres_session: Session, postgres_factory: Factory, branch: Branch) -> UserAccount:
    """Commit the owner, an administrator."""
    account = postgres_factory.user(role=UserRole.ADMIN)
    postgres_session.commit()
    return account


@pytest.fixture
def people(postgres_session: Session) -> Iterator[tuple[BookingClient, FakeEmailGateway]]:
    """Yield the routes on PostgreSQL and the gateway they send through."""
    gateway = FakeEmailGateway()
    with people_client(postgres_session, FixedClock(), gateway) as client:
        yield client, gateway


def sessions_of(session: Session, account_id: object) -> list[RefreshSession]:
    """Return the committed refresh sessions of an account."""
    session.rollback()
    statement = select(RefreshSession).where(col(RefreshSession.user_account_id) == account_id)
    return list(session.exec(statement).all())


def test_an_account_is_opened_stopped_and_started_again_through_http(
    postgres_session: Session, people: tuple[BookingClient, FakeEmailGateway], owner: UserAccount
) -> None:
    client, gateway = people
    user = created(open_user(client, owner, staff_body()))["user"]
    assert isinstance(user, dict)
    token = token_from(gateway, STAFF_EMAIL, RESET_KEY)
    chosen = client.client.post(
        RESET_COMPLETE_PATH, json={"token": token, "newPassword": CHOSEN_PASSWORD}
    )
    assert chosen.status_code == status.HTTP_204_NO_CONTENT, chosen.text
    signed_in = sign_in(client.client, STAFF_EMAIL, CHOSEN_PASSWORD)
    assert signed_in.status_code == status.HTTP_200_OK, signed_in.text
    refresh_token = refresh_token_of(signed_in)

    answered(deactivate_user(client, owner, user["id"]))
    revoked = sessions_of(postgres_session, user["id"])
    assert revoked
    assert {row.revoked_reason for row in revoked} == {RevokeReason.ADMIN_REVOKE}
    assert sign_in(client.client, STAFF_EMAIL, CHOSEN_PASSWORD).status_code == 401
    assert present(client.client, REFRESH_PATH, refresh_token).status_code == 401

    answered(reactivate_user(client, owner, user["id"]))
    assert sign_in(client.client, STAFF_EMAIL, CHOSEN_PASSWORD).status_code == 200


def test_the_link_of_an_account_stopped_before_it_was_used_no_longer_works(
    people: tuple[BookingClient, FakeEmailGateway], owner: UserAccount
) -> None:
    client, gateway = people
    user = created(open_user(client, owner, staff_body()))["user"]
    assert isinstance(user, dict)
    token = token_from(gateway, STAFF_EMAIL, RESET_KEY)
    answered(deactivate_user(client, owner, user["id"]))
    chosen = client.client.post(
        RESET_COMPLETE_PATH, json={"token": token, "newPassword": CHOSEN_PASSWORD}
    )
    assert chosen.status_code == status.HTTP_400_BAD_REQUEST, chosen.text
    answered(reactivate_user(client, owner, user["id"]))
    assert sign_in(client.client, STAFF_EMAIL, CHOSEN_PASSWORD).status_code == 401


def test_a_demoted_administrator_is_refused_with_the_token_they_had(
    postgres_session: Session,
    postgres_factory: Factory,
    people: tuple[BookingClient, FakeEmailGateway],
    owner: UserAccount,
    branch: Branch,
) -> None:
    client, _ = people
    bookkeeper = postgres_factory.user(role=UserRole.ADMIN)
    postgres_session.commit()
    old_headers = client.headers(bookkeeper)
    answered(
        edit_user(client, owner, bookkeeper.id, {"role": "COUNTER_STAFF", "branchCode": "CBD"})
    )
    refused = client.client.get("/api/admin/users", headers=old_headers)
    assert refused.status_code == status.HTTP_403_FORBIDDEN


def test_an_account_whose_audit_event_fails_is_never_opened_or_mailed(
    postgres_engine: Engine, postgres_session: Session, owner: UserAccount, branch: Branch
) -> None:
    gateway = FakeEmailGateway()
    with Session(postgres_engine) as reader:
        use_case = OpenStaffAccountUseCase(
            UnitOfWorkWithBrokenAudit(lambda: Session(postgres_engine)),
            FixedClock(),
            SqlStaffDirectory(reader),
            CachedBcryptHasher(),
            AccountMailer(gateway, ORIGIN),
        )
        with pytest.raises(AuditWriteFailed):
            use_case.execute(
                OpenStaffAccountCommand(
                    actor=Actor(user_id=owner.id, role=UserRole.ADMIN),
                    email=STAFF_EMAIL,
                    full_name="Thandi Mokoena",
                    phone=None,
                    role=UserRole.COUNTER_STAFF,
                    branch_code=branch.code,
                )
            )
    postgres_session.rollback()
    found = postgres_session.exec(
        select(UserAccount).where(col(UserAccount.email) == STAFF_EMAIL)
    ).first()
    assert found is None
    assert gateway.sent == []


def test_a_deactivation_whose_audit_event_fails_keeps_the_account_and_its_sessions(
    postgres_engine: Engine,
    postgres_session: Session,
    postgres_factory: Factory,
    people: tuple[BookingClient, FakeEmailGateway],
    owner: UserAccount,
    branch: Branch,
) -> None:
    client, _ = people
    staff = postgres_factory.user(role=UserRole.COUNTER_STAFF, branch=branch)
    postgres_session.commit()
    assert sign_in(client.client, staff.email).status_code == status.HTTP_200_OK
    with Session(postgres_engine) as reader:
        use_case = DeactivateStaffAccountUseCase(
            UnitOfWorkWithBrokenAudit(lambda: Session(postgres_engine)),
            FixedClock(),
            SqlStaffDirectory(reader),
        )
        with pytest.raises(AuditWriteFailed):
            use_case.execute(
                DeactivateStaffAccountCommand(
                    actor=Actor(user_id=owner.id, role=UserRole.ADMIN),
                    user_id=staff.id,
                    reason=REASON,
                )
            )
    assert [row.revoked_at for row in sessions_of(postgres_session, staff.id)] == [None]
    stored = postgres_session.get(UserAccount, staff.id)
    assert stored is not None
    postgres_session.refresh(stored)
    assert stored.is_active is True


def test_a_release_whose_audit_event_fails_keeps_the_hold(
    postgres_engine: Engine,
    postgres_session: Session,
    postgres_factory: Factory,
    owner: UserAccount,
    branch: Branch,
) -> None:
    profile = postgres_factory.customer_profile(branch=branch)
    profile.account_status = AccountStatus.ON_HOLD
    postgres_session.add(profile)
    postgres_session.commit()
    use_case = ChangeCustomerStandingUseCase(
        UnitOfWorkWithBrokenAudit(lambda: Session(postgres_engine)), FixedClock()
    )
    with pytest.raises(AuditWriteFailed):
        use_case.execute(
            ChangeCustomerStandingCommand(
                actor=Actor(user_id=owner.id, role=UserRole.ADMIN),
                customer_profile_id=profile.id,
                account_status=AccountStatus.ACTIVE,
                reason="Paid what was owed.",
            )
        )
    postgres_session.rollback()
    stored = postgres_session.get(CustomerProfile, profile.id)
    assert stored is not None
    postgres_session.refresh(stored)
    assert stored.account_status is AccountStatus.ON_HOLD
    events = postgres_session.exec(select(AuditEvent)).all()
    assert [event.action for event in events] == []
