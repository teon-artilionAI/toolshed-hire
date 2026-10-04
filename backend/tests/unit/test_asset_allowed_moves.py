"""The moves the register offers for a unit, with no database (FR-23, BR-38).

The register offers exactly the moves the server would accept, so a unit with
an open damage report is never offered the move back to service, which would
only be refused until the report is resolved.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.application.catalogue.asset_read_models import AdminAssetEntry
from app.domain.enums import AssetStatus, ConditionGrade


def quarantined_unit(*, open_damage_reports: int) -> AdminAssetEntry:
    """Return a quarantined unit with the given number of open damage reports."""
    return AdminAssetEntry(
        id=uuid4(),
        asset_tag="TSH-PC-0007",
        model_id=uuid4(),
        model_name="Plate compactor",
        model_slug="plate-compactor",
        category_name="Compaction",
        branch_code="CBD",
        branch_name="Cape Town CBD",
        serial_number=None,
        status=AssetStatus.QUARANTINED,
        condition_grade=ConditionGrade.C,
        acquired_on=date(2025, 3, 4),
        acquisition_cost=Decimal("18500.00"),
        hour_meter_reading=None,
        notes=None,
        retired_on=None,
        active_allocation_count=0,
        open_damage_reports=open_damage_reports,
    )


class TestTheMovesOnOffer:
    """The register never offers a move the server would refuse for an open report."""

    def test_a_quarantined_unit_with_no_open_report_may_go_back_to_service(self) -> None:
        moves = quarantined_unit(open_damage_reports=0).allowed_transitions
        assert AssetStatus.AVAILABLE in moves

    def test_a_quarantined_unit_with_an_open_report_is_not_offered_service(self) -> None:
        moves = quarantined_unit(open_damage_reports=1).allowed_transitions
        assert AssetStatus.AVAILABLE not in moves
        assert AssetStatus.UNDER_REPAIR in moves
        assert AssetStatus.RETIRED in moves
