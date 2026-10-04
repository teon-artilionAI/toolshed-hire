"""A small fleet with a month of history, and every figure of its report worked out by hand.

The period is September 2026, `[2026-09-01, 2026-10-01)`, thirty days. The
clock stands on Sunday the twentieth at ten in the morning in Cape Town, so a
unit still out is on hire up to and including the twentieth. Every instant
below is a time on a clock in Cape Town, at ten in the morning unless a time
is given.

Two branches, CBD and BLV. Two categories, Drilling and Concrete. Three
models, the Hammer and the Drill in Drilling and the Mixer in Concrete. A
customer on hold and a confirmation that could not be sent are there for the
dashboard and touch no figure of the report.

What happened to each unit.

- TSH-HM-0001, a Hammer at CBD. On the hire of three from the 2nd to the 9th.
  Out again on the 18th for a week, and still out.
- TSH-HM-0002, a Hammer at CBD. On the hire of three from the 2nd, back two
  days late on the 11th, with a late fee of R208.70 ex VAT.
- TSH-MX-0001, a Mixer at CBD. On the hire of three from the 2nd, back on the
  9th flagged and quarantined at the counter. Its report was filed on the 10th
  at 09:00 and charged, R400.00 recovered ex VAT. Under repair from the 11th,
  resolved on the 14th at 15:00 at R350.00.
- TSH-DR-0001, a Drill at CBD. Out since 27 August, back a day late on the
  4th, its late fee waived. Damage found on the 5th at 09:00, written off on
  the 11th at 12:00 and retired that day.
- TSH-HM-0003, a Hammer at BLV. Damage found on the 5th at 11:00, under
  repair from the 8th, resolved on the 12th at 16:00 at R180.00. Hired from
  the 15th to the 18th for R370.00, a charge then reversed in full.
- TSH-MX-0002, a Mixer at BLV, acquired on the 15th. Confirmed for the 25th
  to 3 October, held until 10:20 today for the 21st and 22nd, held until
  09:30 today for the 19th, which has run out, and a cancelled booking for
  the 16th and 17th.
- TSH-DR-0002, a Drill at BLV, acquired on the 18th and still at INTAKE.

The hire of three is one charge on the whole hire, R725.25 ex VAT, for a
Hammer line of two units at R425.25 and a Mixer line of one at R300.00. Each
Hammer weighs R212.625 and the Mixer R300.00, so a Hammer's share is exactly
R212.625, rounded half up to R212.63, and the Mixer as the last unit takes
725.25 - 212.63 - 212.63 = R299.99. The second hire of TSH-HM-0001 is R518.00
on the unit. Deposits held and released are not part of gross contribution.

Serviceable days and days on hire, by hand. "Fleet" is the days in the fleet,
"Out" the days out of service, each counted once.

| Unit | Fleet | Out | Serviceable | On hire | Utilisation |
|---|---|---|---|---|---|
| HM-0001 | 30 | 0 | 30 | 2nd to 8th 7, 18th to 20th 3, so 10 | 10/30 = 33.33 |
| HM-0002 | 30 | 0 | 30 | 2nd to 10th, 9 | 9/30 = 30.00 |
| MX-0001 | 30 | 9th to 13th, 5 | 25 | 2nd to 8th, 7 | 7/25 = 28.00 |
| DR-0001 | 1st to 10th, 10 | 5th to 10th, 6 | 4 | 1st to 3rd, 3 | 3/4 = 75.00 |
| HM-0003 | 30 | 5th to 11th, 7 | 23 | 15th to 17th, 3 | 3/23 = 13.04 |
| MX-0002 | 15th to 30th, 16 | 0 | 16 | 25th to 30th 6, 21st to 22nd 2 | 8/16 = 50.00 |
| DR-0002 | 18th to 30th, 13 | 13 | 0 | 0 | none |

The five days of MX-0001 are the quarantine from its return on the 9th and
its report from the 10th, the 10th to the 13th named by both and counted once.

Money ex VAT, by hand. Hire, late fees, recovery, repairs, gross contribution.

| Unit | Hire | Late | Recovery | Repairs | Gross |
|---|---|---|---|---|---|
| HM-0001 | 212.63 + 518.00 = 730.63 | 0.00 | 0.00 | 0.00 | 730.63 |
| HM-0002 | 212.63 | 208.70 | 0.00 | 0.00 | 421.33 |
| MX-0001 | 299.99 | 0.00 | 400.00 | 350.00 | 349.99 |
| DR-0001 | 0.00, raised in August | 0.00, waived | 0.00 | 0.00, written off | 0.00 |
| HM-0003 | 370.00 - 370.00 = 0.00 | 0.00 | 0.00 | 180.00 | -180.00 |
| MX-0002 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| DR-0002 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

The groupings and the totals are these rows added up, in
`tests/integration/test_report_worked_dataset.py` beside the assertions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Final

from sqlmodel import Session

from app.domain.enums import (
    AccountStatus,
    AssetStatus,
    ChargeStatus,
    ChargeType,
    ConditionGrade,
    DamageStatus,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    ReleaseReason,
    ReservationStatus,
    UserRole,
)
from app.domain.period import BookingPeriod
from app.infrastructure.models import Notification
from tests.support.factories import Factory
from tests.support.report_pg import FleetBuilder, Line, cape_town

NOW: Final[datetime] = datetime(2026, 9, 20, 8, 0, tzinfo=UTC)
SEPTEMBER_FIRST: Final[date] = date(2026, 9, 1)
OCTOBER_FIRST: Final[date] = date(2026, 10, 1)
AVAILABLE: Final[AssetStatus] = AssetStatus.AVAILABLE
ON_HIRE: Final[AssetStatus] = AssetStatus.ON_HIRE
QUARANTINED: Final[AssetStatus] = AssetStatus.QUARANTINED
UNDER_REPAIR: Final[AssetStatus] = AssetStatus.UNDER_REPAIR
RETURNED: Final[ReleaseReason] = ReleaseReason.RETURNED
# The line amounts of the four hires, excluding VAT.
DRILL_HIRE: Final[Decimal] = Decimal("450.00")
HAMMER_LINE: Final[Decimal] = Decimal("425.25")
MIXER_LINE: Final[Decimal] = Decimal("300.00")
REVERSED_HIRE: Final[Decimal] = Decimal("370.00")
SECOND_HIRE: Final[Decimal] = Decimal("518.00")


def sep(day: int, hour: int = 10, minute: int = 0) -> datetime:
    """Return a time on a day of September 2026 in Cape Town, in UTC."""
    return cape_town(date(2026, 9, day), time(hour, minute))


def on(day: int) -> date:
    """Return a day of September 2026."""
    return date(2026, 9, day)


@dataclass(frozen=True, slots=True)
class Dataset:
    """The keys a test reads after the commit, kept as plain values."""

    concrete_slug: str


def build_report_dataset(session: Session, factory: Factory) -> Dataset:
    """Commit the fleet of this module with its September, and return what a test asks by."""
    cbd = factory.branch(code="CBD", name="Cape Town CBD")
    blv = factory.branch(code="BLV", name="Bellville")
    drilling = factory.category(name="Drilling")
    concrete = factory.category(name="Concrete")
    drilling.slug, concrete.slug = "drilling", "concrete"
    hammer = factory.product_model(name="Hammer", category=drilling)
    drill = factory.product_model(name="Drill", category=drilling)
    mixer = factory.product_model(name="Mixer", category=concrete)
    hammer.slug, drill.slug, mixer.slug = "hammer", "drill", "mixer"
    session.add_all([drilling, concrete, hammer, drill, mixer])
    session.flush()
    staff = factory.user(role=UserRole.ADMIN)
    build = FleetBuilder(factory, staff, factory.customer_profile(branch=cbd))
    held_back = factory.customer_profile(branch=blv)
    held_back.account_status = AccountStatus.ON_HOLD
    session.add(held_back)

    hm1 = build.unit("TSH-HM-0001", hammer, cbd, acquired_on=date(2025, 1, 10), status=ON_HIRE)
    hm2 = build.unit("TSH-HM-0002", hammer, cbd, acquired_on=date(2025, 1, 10))
    mx1 = build.unit("TSH-MX-0001", mixer, cbd, acquired_on=date(2025, 3, 1))
    dr1 = build.unit(
        "TSH-DR-0001",
        drill,
        cbd,
        acquired_on=date(2024, 5, 1),
        status=AssetStatus.RETIRED,
        retired_on=on(11),
    )
    hm3 = build.unit("TSH-HM-0003", hammer, blv, acquired_on=date(2025, 6, 1))
    mx2 = build.unit("TSH-MX-0002", mixer, blv, acquired_on=on(15))
    build.unit("TSH-DR-0002", drill, blv, acquired_on=on(18), status=AssetStatus.INTAKE)

    # The drill, out since 27 August, back a day late, found damaged and written off.
    drill_hire = build.booking(
        cbd,
        BookingPeriod(date(2026, 8, 27), on(3)),
        [Line(drill, [dr1], DRILL_HIRE)],
        status=ReservationStatus.RETURNED,
        released=RETURNED,
    )
    dr1_item = build.rental(
        drill_hire, out=date(2026, 8, 27), returns={dr1.id: (sep(4), ConditionGrade.A)}
    )[dr1.id]
    build.charge(dr1_item, ChargeType.HIRE, "450.00", date(2026, 8, 27))
    build.charge(dr1_item, ChargeType.LATE_FEE, "104.35", on(4), status=ChargeStatus.WAIVED)
    build.moved(dr1, cape_town(date(2026, 8, 27)), AVAILABLE, ON_HIRE)
    build.moved(dr1, sep(4), ON_HIRE, AVAILABLE)
    build.moved(dr1, sep(5, 9), AVAILABLE, QUARANTINED)
    build.moved(dr1, sep(11, 12), QUARANTINED, AssetStatus.RETIRED)
    build.damage(dr1, sep(5, 9), status=DamageStatus.WRITTEN_OFF, resolved_at=sep(11, 12))

    # The hire of three, one charge on the whole hire.
    three = build.booking(
        cbd,
        BookingPeriod(on(2), on(9)),
        [Line(hammer, [hm1, hm2], HAMMER_LINE), Line(mixer, [mx1], MIXER_LINE)],
        status=ReservationStatus.RETURNED,
        released=RETURNED,
    )
    items = build.rental(
        three,
        out=on(2),
        returns={
            hm1.id: (sep(9), ConditionGrade.A),
            hm2.id: (sep(11), ConditionGrade.A),
            mx1.id: (sep(9), ConditionGrade.C),
        },
    )
    build.charge(items[hm1.id], ChargeType.HIRE, "725.25", on(2), on_the_unit=False)
    build.charge(items[hm1.id], ChargeType.DEPOSIT_HOLD, "1800.00", on(2), on_the_unit=False)
    build.charge(items[hm2.id], ChargeType.LATE_FEE, "208.70", on(11))
    build.charge(items[hm1.id], ChargeType.DEPOSIT_RELEASE, "-1800.00", on(11), on_the_unit=False)
    mixer_report = build.damage(
        mx1,
        sep(10, 9),
        status=DamageStatus.RESOLVED,
        resolved_at=sep(14, 15),
        actual_repair_cost="350.00",
        item=items[mx1.id],
    )
    recovery = build.charge(items[mx1.id], ChargeType.DAMAGE_RECOVERY, "400.00", on(10))
    recovery.damage_report_id = mixer_report.id
    session.add(recovery)
    for unit in (hm1, hm2, mx1):
        build.moved(unit, sep(2), AVAILABLE, ON_HIRE)
    build.moved(hm1, sep(9), ON_HIRE, AVAILABLE)
    build.moved(hm2, sep(11), ON_HIRE, AVAILABLE)
    build.moved(mx1, sep(9), ON_HIRE, QUARANTINED)
    build.moved(mx1, sep(11), QUARANTINED, UNDER_REPAIR)
    build.moved(mx1, sep(14, 15), UNDER_REPAIR, AVAILABLE)

    # The hammer at BLV, damaged before its hire, its hire charge then reversed.
    build.damage(
        hm3,
        sep(5, 11),
        status=DamageStatus.RESOLVED,
        resolved_at=sep(12, 16),
        actual_repair_cost="180.00",
    )
    build.moved(hm3, sep(5, 11), AVAILABLE, QUARANTINED)
    build.moved(hm3, sep(8), QUARANTINED, UNDER_REPAIR)
    build.moved(hm3, sep(12, 16), UNDER_REPAIR, AVAILABLE)
    away = build.booking(
        blv,
        BookingPeriod(on(15), on(18)),
        [Line(hammer, [hm3], REVERSED_HIRE)],
        status=ReservationStatus.RETURNED,
        released=RETURNED,
    )
    hm3_item = build.rental(away, out=on(15), returns={hm3.id: (sep(18), ConditionGrade.A)})[
        hm3.id
    ]
    first = build.charge(hm3_item, ChargeType.HIRE, "370.00", on(15))
    build.charge(hm3_item, ChargeType.HIRE, "-370.00", on(16), reverses=first)
    build.moved(hm3, sep(15), AVAILABLE, ON_HIRE)
    build.moved(hm3, sep(18), ON_HIRE, AVAILABLE)

    # The first hammer out again, still out today.
    again = build.booking(
        cbd,
        BookingPeriod(on(18), on(25)),
        [Line(hammer, [hm1], SECOND_HIRE)],
        status=ReservationStatus.COLLECTED,
    )
    hm1_again = build.rental(again, out=on(18), returns={})[hm1.id]
    build.charge(hm1_again, ChargeType.HIRE, "518.00", on(18))
    build.moved(hm1, sep(18), AVAILABLE, ON_HIRE)

    # The mixer at BLV, booked and held but not collected. Its confirmation
    # could not be sent, which the dashboard counts.
    confirmed = build.booking(
        blv,
        BookingPeriod(on(25), date(2026, 10, 3)),
        [Line(mixer, [mx2])],
        status=ReservationStatus.CONFIRMED,
    )
    session.add(
        Notification(
            reservation_id=confirmed.reservation.id,
            notification_type=NotificationType.BOOKING_CONFIRMATION,
            channel=NotificationChannel.EMAIL,
            recipient_email="nomsa@example.co.za",
            subject="Your booking is confirmed",
            status=NotificationStatus.FAILED,
            provider="fake",
            attempts=1,
            last_error="The provider refused the message.",
            queued_at=sep(19),
        )
    )
    build.booking(
        blv,
        BookingPeriod(on(21), on(23)),
        [Line(mixer, [mx2])],
        status=ReservationStatus.HELD,
        hold_expires_at=sep(20, 10, 20),
    )
    build.booking(
        blv,
        BookingPeriod(on(19), on(20)),
        [Line(mixer, [mx2])],
        status=ReservationStatus.HELD,
        hold_expires_at=sep(20, 9, 30),
    )
    build.booking(
        blv,
        BookingPeriod(on(16), on(18)),
        [Line(mixer, [mx2])],
        status=ReservationStatus.CANCELLED,
        released=ReleaseReason.CANCELLED,
    )
    session.commit()
    return Dataset(concrete_slug="concrete")

