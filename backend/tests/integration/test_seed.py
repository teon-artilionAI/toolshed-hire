"""The seed loads the documented catalogue, fleet and people, and loads them once.

The seed is what gives a new deployment something to show, so it is tested
against the same migrated PostgreSQL the application runs on. The check
constraints are the reason. A retired unit with no retirement date or a counter
assistant with no branch would be accepted by SQLite and refused here.

The `seeded` fixture empties the database and seeds it once for the module.
Every test reads through its own session. The one test that seeds a second time
proves that doing so changes nothing, so it cannot disturb the others whichever
order they run in. The closed hire has its own module, beside this one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

import pytest
from sqlalchemy import Engine, func, table, text
from sqlmodel import Session, col, select

from app.domain.enums import AssetStatus, ConditionGrade, CustomerType, UserRole
from app.infrastructure.models import (
    Asset,
    Branch,
    Category,
    CustomerProfile,
    ProductModel,
    UserAccount,
)
from app.infrastructure.schema_ddl import REFERENCE_SEQUENCE, TABLE_NAMES
from app.infrastructure.security import verify_password
from seed_data import PINNED_ASSETS
from seeding import SeedTally, seed_database
from seeding.fleet_plan import TAG_PATTERN
from seeding.people import ACCOUNTS_OPENED_AT, TRADE_CUSTOMER_EMAIL
from seeding.worked_example import BOOKED_AT
from tests.support.factories import TEST_PASSWORD

pytestmark = pytest.mark.postgres

BRANCH_COUNT: Final[int] = 3
CATEGORY_COUNT: Final[int] = 14
PRODUCT_MODEL_COUNT: Final[int] = 120
FEWEST_ASSETS: Final[int] = 395
MOST_ASSETS: Final[int] = 405
ACCOUNT_COUNT: Final[int] = 5
SEEDED_RESERVATION_NUMBER: Final[int] = 123


def row_counts(engine: Engine) -> dict[str, int]:
    """Return the number of rows in every table of the schema."""
    with engine.connect() as connection:
        return {
            name: int(
                connection.execute(select(func.count()).select_from(table(name))).scalar_one()
            )
            for name in TABLE_NAMES
        }


class TestTheCatalogueAndTheFleetAreLoaded:
    """Three branches, the category tree, 120 published models and about 400 units."""

    def test_there_are_three_branches(self, reader: Session) -> None:
        codes = {branch.code for branch in reader.exec(select(Branch)).all()}
        assert codes == {"CBD", "BLV", "SMW"}
        assert len(codes) == BRANCH_COUNT

    def test_every_child_category_sits_under_a_top_level_parent(self, reader: Session) -> None:
        categories = reader.exec(select(Category)).all()
        by_id = {category.id: category for category in categories}
        children = [category for category in categories if category.parent_category_id]
        assert len(categories) == CATEGORY_COUNT
        assert children, "The seed data nests at least one category."
        assert all(by_id[child.parent_category_id].parent_category_id is None for child in children)

    def test_there_are_120_product_models_and_all_are_published(self, reader: Session) -> None:
        models = reader.exec(select(ProductModel)).all()
        assert len(models) == PRODUCT_MODEL_COUNT
        assert all(model.is_published for model in models)

    def test_the_fleet_holds_about_four_hundred_units(self, reader: Session) -> None:
        count = len(reader.exec(select(Asset)).all())
        assert FEWEST_ASSETS <= count <= MOST_ASSETS

    def test_every_asset_tag_has_the_documented_shape(self, reader: Session) -> None:
        tags = reader.exec(select(col(Asset.asset_tag))).all()
        malformed = sorted(tag for tag in tags if TAG_PATTERN.fullmatch(tag) is None)
        assert not malformed

    def test_every_pinned_unit_kept_its_tag(self, reader: Session) -> None:
        pinned_tags = {unit.asset_tag for unit in PINNED_ASSETS}
        stored = set(
            reader.exec(
                select(col(Asset.asset_tag)).where(col(Asset.asset_tag).in_(pinned_tags))
            ).all()
        )
        assert stored == pinned_tags

    def test_every_generated_unit_is_available_and_graded_a_or_b(self, reader: Session) -> None:
        pinned_tags = {unit.asset_tag for unit in PINNED_ASSETS}
        generated = reader.exec(
            select(Asset).where(col(Asset.asset_tag).not_in(pinned_tags))
        ).all()
        unexpected = [
            asset.asset_tag
            for asset in generated
            if asset.status is not AssetStatus.AVAILABLE
            or asset.condition_grade not in (ConditionGrade.A, ConditionGrade.B)
        ]
        assert generated
        assert not unexpected


class TestThePeopleAreLoaded:
    """One administrator, a counter assistant at two branches and two customers."""

    def test_every_account_is_verified_and_signs_in_with_the_seed_password(
        self, reader: Session
    ) -> None:
        accounts = reader.exec(select(UserAccount)).all()
        assert len(accounts) == ACCOUNT_COUNT
        assert all(account.email_verified_at is not None for account in accounts)
        assert all(verify_password(TEST_PASSWORD, account.password_hash) for account in accounts)

    def test_there_is_a_counter_assistant_at_cbd_and_at_blv(self, reader: Session) -> None:
        staff = reader.exec(
            select(UserAccount).where(col(UserAccount.role) == UserRole.COUNTER_STAFF)
        ).all()
        branch_codes = set()
        for account in staff:
            branch = reader.get(Branch, account.branch_id)
            assert branch is not None
            branch_codes.add(branch.code)
        assert branch_codes == {"CBD", "BLV"}

    def test_each_customer_has_a_profile_and_the_trade_customer_names_a_company(
        self, reader: Session
    ) -> None:
        profiles = reader.exec(select(CustomerProfile)).all()
        by_type = {profile.customer_type: profile for profile in profiles}
        assert set(by_type) == {CustomerType.TRADE, CustomerType.INDIVIDUAL}
        assert by_type[CustomerType.TRADE].company_name
        assert all(profile.registered_branch_id is not None for profile in profiles)
        assert all(profile.user_account_id is not None for profile in profiles)


class TestSeededAccountsWereOpenedBeforeTheirHistory:
    """Every seeded account and profile is opened before any seeded hire."""

    def test_every_seeded_account_and_profile_is_opened_at_the_seeded_date(
        self, postgres_engine: Engine, seeded: SeedTally
    ) -> None:
        with Session(postgres_engine) as session:
            accounts = session.exec(select(col(UserAccount.created_at))).all()
            profiles = session.exec(select(col(CustomerProfile.created_at))).all()

        assert len(accounts) == ACCOUNT_COUNT
        assert set(accounts) == {ACCOUNTS_OPENED_AT}
        assert set(profiles) == {ACCOUNTS_OPENED_AT}
        assert ACCOUNTS_OPENED_AT < BOOKED_AT

    def test_a_row_an_earlier_run_stamped_with_its_own_day_is_moved_back(
        self, postgres_engine: Engine, seeded: SeedTally
    ) -> None:
        stamped_late = datetime.now(UTC)
        with Session(postgres_engine) as session:
            account = session.exec(
                select(UserAccount).where(col(UserAccount.email) == TRADE_CUSTOMER_EMAIL)
            ).one()
            profile = session.exec(
                select(CustomerProfile).where(col(CustomerProfile.user_account_id) == account.id)
            ).one()
            account.created_at = stamped_late
            profile.created_at = stamped_late
            stranger = UserAccount(
                email="not.seeded@example.com",
                password_hash=account.password_hash,
                role=UserRole.CUSTOMER,
                full_name="Not Seeded",
                created_at=stamped_late,
            )
            session.add_all([account, profile, stranger])
            session.commit()
            stranger_id = stranger.id

        try:
            with Session(postgres_engine) as session:
                corrected = seed_database(session, TEST_PASSWORD)
                session.commit()
            with Session(postgres_engine) as session:
                again = seed_database(session, TEST_PASSWORD)
                session.commit()
            with Session(postgres_engine) as session:
                account_opened = session.exec(
                    select(col(UserAccount.created_at)).where(
                        col(UserAccount.email) == TRADE_CUSTOMER_EMAIL
                    )
                ).one()
                stranger_opened = session.get_one(UserAccount, stranger_id).created_at
        finally:
            with Session(postgres_engine) as session:
                session.delete(session.get_one(UserAccount, stranger_id))
                session.commit()

        assert corrected.total_created == 0
        assert corrected.corrected == {
            "user_account_opening_date": 1,
            "customer_profile_opening_date": 1,
        }
        assert account_opened == ACCOUNTS_OPENED_AT
        assert stranger_opened == stamped_late
        assert again.changed_nothing


class TestTheSeedIsIdempotent:
    """A second run finds every row and writes none."""

    def test_the_first_run_created_rows_and_found_none(self, seeded: SeedTally) -> None:
        assert seeded.total_created > 0
        assert not seeded.changed_nothing

    def test_a_second_run_creates_nothing(self, postgres_engine: Engine, seeded: SeedTally) -> None:
        before = row_counts(postgres_engine)
        with Session(postgres_engine) as session:
            hashes_before = set(session.exec(select(col(UserAccount.password_hash))).all())
            second = seed_database(session, TEST_PASSWORD)
            session.commit()
        with Session(postgres_engine) as session:
            hashes_after = set(session.exec(select(col(UserAccount.password_hash))).all())

        assert second.changed_nothing, f"The second run created {second.created}."
        assert second.total_found >= seeded.total_created
        assert row_counts(postgres_engine) == before
        assert hashes_after == hashes_before

    def test_the_next_reservation_reference_is_past_the_seeded_one(
        self, postgres_engine: Engine, seeded: SeedTally
    ) -> None:
        with postgres_engine.connect() as connection:
            next_value = connection.execute(
                text("SELECT nextval(CAST(:name AS regclass))"), {"name": REFERENCE_SEQUENCE}
            ).scalar_one()
        assert int(next_value) > SEEDED_RESERVATION_NUMBER
