"""A lost unit is out of service from the day its loss was recorded, on PostgreSQL.

Two hammers went out on 10 August and were never brought back. Each loss was
recorded on 5 September at ten in the morning, which closes the rental item
with no condition. The period is September, thirty days, and the clock stands
on the twentieth.

The first hammer has no recorded change of status at all, so only the loss
says it was out. It is out from the 5th to the end of the month, 26 days, so
it was serviceable on 4 days, the 1st to the 4th, and on hire on all four.
Utilisation 4 over 4, 100.00.

The second has every change recorded. It went on hire on 10 August, was
recorded lost on the 5th, was found and quarantined on the 20th and was back
on the shelf on the 25th. The loss runs to the next change, the 20th, and the
quarantine from the 20th to the 25th, so it was out from the 5th to the 24th,
20 days, and serviceable on 10. On hire the same 4 days, 4 over 10, 40.00.
"""

from __future__ import annotations

from datetime import date
from typing import Final

import pytest
from sqlmodel import Session

from app.application.reporting.fleet_figures import FleetFigures, FleetQuestion
from app.application.reporting.report_models import GroupBy
from app.domain.enums import AssetStatus, ReleaseReason, ReservationStatus, UserRole
from app.domain.period import BookingPeriod
from app.infrastructure.fleet_report import SqlFleetReport
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.report_dataset import NOW, OCTOBER_FIRST, SEPTEMBER_FIRST, sep
from tests.support.report_pg import FleetBuilder, Line, cape_town

pytestmark = pytest.mark.postgres

WENT_OUT: Final[date] = date(2026, 8, 10)


def build_two_losses(session: Session, factory: Factory) -> None:
    """Commit the two lost hammers of this module."""
    branch = factory.branch(name="Cape Town CBD")
    hammer = factory.product_model(name="Hammer")
    build = FleetBuilder(
        factory, factory.user(role=UserRole.ADMIN), factory.customer_profile(branch=branch)
    )
    silent = build.unit(
        "TSH-HM-0101", hammer, branch, acquired_on=date(2025, 1, 1), status=AssetStatus.LOST
    )
    recorded = build.unit("TSH-HM-0102", hammer, branch, acquired_on=date(2025, 1, 1))
    for unit in (silent, recorded):
        booking = build.booking(
            branch,
            BookingPeriod(WENT_OUT, date(2026, 8, 13)),
            [Line(hammer, [unit])],
            status=ReservationStatus.RETURNED,
            released=ReleaseReason.RETURNED,
        )
        build.rental(booking, out=WENT_OUT, returns={unit.id: (sep(5), None)})
    build.moved(recorded, cape_town(WENT_OUT), AssetStatus.AVAILABLE, AssetStatus.ON_HIRE)
    build.moved(recorded, sep(5), AssetStatus.ON_HIRE, AssetStatus.LOST)
    build.moved(recorded, sep(20), AssetStatus.LOST, AssetStatus.QUARANTINED)
    build.moved(recorded, sep(25), AssetStatus.QUARANTINED, AssetStatus.AVAILABLE)
    session.commit()


def test_a_loss_runs_to_the_next_recorded_change_or_to_the_end_of_the_period(
    postgres_session: Session, postgres_factory: Factory
) -> None:
    build_two_losses(postgres_session, postgres_factory)
    clock = FixedClock(NOW)
    report = FleetFigures(SqlFleetReport(postgres_session), clock).report(
        FleetQuestion(starts_on=SEPTEMBER_FIRST, ends_on=OCTOBER_FIRST, group_by=GroupBy.ASSET)
    )
    figures = {
        line.key: (line.days_on_hire, line.serviceable_days, str(line.utilisation_percent))
        for line in report.lines
    }
    assert figures == {"TSH-HM-0101": (4, 4, "100.00"), "TSH-HM-0102": (4, 10, "40.00")}
