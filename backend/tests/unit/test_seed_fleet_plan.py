"""The fleet plan gives every unit a tag, and the same tag every time.

An asset tag is painted on a machine, so the seed may never give a unit one tag
on the first run and another on the second. The plan is a pure function of the
seed data, which is why it can be proved here with no database at all.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal

import pytest

from app.domain.enums import AssetStatus, ConditionGrade
from seed_data import BRANCHES, PINNED_ASSETS, PRODUCT_MODELS
from seed_data.types import PinnedAssetSeed, ProductModelSeed
from seeding import SeedDataError
from seeding.fleet_plan import format_tag, parse_tag, plan_fleet

BRANCH_ORDER = ("CBD", "BLV", "SMW")
FLEET_SIZE = 400
PINNED_COUNT = 34
UNITS_BY_BRANCH = {"CBD": 171, "BLV": 125, "SMW": 104}
FIRST_GENERATED_TAG = "TSH-AG-0001"


def model(sku: str, prefix: str, units: dict[str, int]) -> ProductModelSeed:
    """Build a product model that differs only in the fields the plan reads."""
    return ProductModelSeed(
        sku=sku,
        name=f"Model {sku}",
        slug=sku.lower(),
        category_code="BREAK-DRILL",
        manufacturer="Bosch",
        model_number=sku,
        short_description="A unit for the plan to number.",
        long_description=None,
        daily_rate=Decimal("100.00"),
        weekly_rate=Decimal("400.00"),
        deposit_amount=Decimal("500.00"),
        late_fee_per_day=Decimal("60.00"),
        replacement_value=Decimal("2500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix=prefix,
        units_per_branch=units,
    )


def pinned(tag: str, sku: str, branch_code: str = "CBD") -> PinnedAssetSeed:
    """Build an available pinned unit with the given tag."""
    return PinnedAssetSeed(
        asset_tag=tag,
        sku=sku,
        branch_code=branch_code,
        status="AVAILABLE",
        condition_grade="A",
        serial_number=None,
        acquired_on=date(2024, 6, 11),
        acquisition_cost=Decimal("2300.00"),
        hour_meter_reading=None,
    )


def real_plan() -> tuple[str, ...]:
    """Return the tags planned from the real seed data, in plan order."""
    plan = plan_fleet(PRODUCT_MODELS, PINNED_ASSETS, [branch.code for branch in BRANCHES])
    return tuple(unit.asset_tag for unit in plan)


class TestTheRealFleet:
    """The plan built from the seed data package itself."""

    def test_the_branches_are_listed_in_numbering_order(self) -> None:
        assert tuple(branch.code for branch in BRANCHES) == BRANCH_ORDER

    def test_it_holds_four_hundred_units_with_no_tag_used_twice(self) -> None:
        tags = real_plan()
        assert len(tags) == FLEET_SIZE
        assert len(set(tags)) == FLEET_SIZE

    def test_the_pinned_units_come_first_with_their_own_tags(self) -> None:
        tags = real_plan()
        assert tags[:PINNED_COUNT] == tuple(unit.asset_tag for unit in PINNED_ASSETS)

    def test_the_first_generated_unit_takes_the_first_number_of_the_first_sku(self) -> None:
        assert real_plan()[PINNED_COUNT] == FIRST_GENERATED_TAG

    def test_the_units_are_spread_over_the_three_branches(self) -> None:
        plan = plan_fleet(PRODUCT_MODELS, PINNED_ASSETS, BRANCH_ORDER)
        assert Counter(unit.branch_code for unit in plan) == UNITS_BY_BRANCH

    def test_the_same_data_always_gives_the_same_plan(self) -> None:
        first = plan_fleet(PRODUCT_MODELS, PINNED_ASSETS, BRANCH_ORDER)
        second = plan_fleet(tuple(reversed(PRODUCT_MODELS)), PINNED_ASSETS, BRANCH_ORDER)
        assert first == second

    def test_every_generated_unit_is_available_and_graded_a_or_b(self) -> None:
        plan = plan_fleet(PRODUCT_MODELS, PINNED_ASSETS, BRANCH_ORDER)
        generated = [unit for unit in plan if not unit.is_pinned]
        assert all(unit.status is AssetStatus.AVAILABLE for unit in generated)
        assert {unit.condition_grade for unit in generated} == {ConditionGrade.A, ConditionGrade.B}

    def test_a_generated_unit_is_carried_at_the_replacement_value_of_its_model(self) -> None:
        values = {seed.sku: seed.replacement_value for seed in PRODUCT_MODELS}
        plan = plan_fleet(PRODUCT_MODELS, PINNED_ASSETS, BRANCH_ORDER)
        assert all(
            unit.acquisition_cost == values[unit.sku] for unit in plan if not unit.is_pinned
        )


class TestNumbering:
    """Upward within a prefix, by SKU and then by branch, stepping over pinned numbers."""

    def test_a_number_a_pinned_unit_carries_is_skipped(self) -> None:
        plan = plan_fleet(
            [model("DR-A", "DR", {"CBD": 3})], [pinned("TSH-DR-0002", "DR-A")], BRANCH_ORDER
        )
        generated = [unit.asset_tag for unit in plan if not unit.is_pinned]
        assert generated == ["TSH-DR-0001", "TSH-DR-0003", "TSH-DR-0004"]

    def test_models_are_numbered_in_sku_order_whatever_order_they_are_given_in(self) -> None:
        models = [model("DR-B", "DR", {"CBD": 1}), model("DR-A", "DR", {"CBD": 1})]
        plan = plan_fleet(models, [], BRANCH_ORDER)
        assert [(unit.asset_tag, unit.sku) for unit in plan] == [
            ("TSH-DR-0001", "DR-A"),
            ("TSH-DR-0002", "DR-B"),
        ]

    def test_branches_are_numbered_in_the_order_given(self) -> None:
        plan = plan_fleet(
            [model("DR-A", "DR", {"SMW": 1, "BLV": 1, "CBD": 1})], [], BRANCH_ORDER
        )
        assert [unit.branch_code for unit in plan] == list(BRANCH_ORDER)

    def test_each_prefix_keeps_its_own_count(self) -> None:
        models = [model("DR-A", "DR", {"CBD": 1}), model("PC-A", "PC", {"CBD": 1})]
        plan = plan_fleet(models, [], BRANCH_ORDER)
        assert [unit.asset_tag for unit in plan] == ["TSH-DR-0001", "TSH-PC-0001"]

    def test_a_tag_round_trips_through_format_and_parse(self) -> None:
        assert parse_tag(format_tag("DR", 42)) == ("DR", 42)
        assert format_tag("DR", 42) == "TSH-DR-0042"


class TestBadSeedDataIsRefused:
    """A mistake in the data stops the plan with a sentence that names the row."""

    @pytest.mark.parametrize("tag", ["TSH-DR-42", "DR-0042", "TSH-dr-0042", "TSH-DR-00042"])
    def test_a_malformed_tag_is_refused(self, tag: str) -> None:
        with pytest.raises(SeedDataError, match="not in the form"):
            parse_tag(tag)

    def test_a_pinned_unit_of_an_unknown_model_is_refused(self) -> None:
        orphan = [pinned("TSH-DR-0001", "DR-MISSING")]
        with pytest.raises(SeedDataError, match="DR-MISSING"):
            plan_fleet([model("DR-A", "DR", {})], orphan, BRANCH_ORDER)

    def test_a_pinned_unit_with_the_wrong_prefix_is_refused(self) -> None:
        with pytest.raises(SeedDataError, match="carries prefix PC"):
            plan_fleet([model("DR-A", "DR", {})], [pinned("TSH-PC-0001", "DR-A")], BRANCH_ORDER)

    def test_a_pinned_tag_listed_twice_is_refused(self) -> None:
        twice = [pinned("TSH-DR-0001", "DR-A"), pinned("TSH-DR-0001", "DR-A")]
        with pytest.raises(SeedDataError, match="more than once"):
            plan_fleet([model("DR-A", "DR", {})], twice, BRANCH_ORDER)

    def test_a_unit_count_for_an_unknown_branch_is_refused(self) -> None:
        with pytest.raises(SeedDataError, match="'XYZ'"):
            plan_fleet([model("DR-A", "DR", {"XYZ": 1})], [], BRANCH_ORDER)

    def test_a_negative_unit_count_is_refused(self) -> None:
        with pytest.raises(SeedDataError, match="cannot be negative"):
            plan_fleet([model("DR-A", "DR", {"CBD": -1})], [], BRANCH_ORDER)
