"""Product models for the Breaking and Drilling category.

I list the two models carried over from the prototype first. New models take the
DR tag prefix. The Hilti breaker keeps BR because its units are already tagged
that way. I price the Bosch GBH 2-26 at R280.00 a day with a R1,200.00 deposit,
which is higher than the prototype showed.
"""

from decimal import Decimal

from .types import ProductModelSeed

BREAKING_DRILLING_MODELS: tuple[ProductModelSeed, ...] = (
    ProductModelSeed(
        sku="DR-BOSCH-GBH226",
        name="GBH 2-26 DRE Rotary Hammer",
        slug="gbh-2-26-dre-rotary-hammer",
        category_code="BREAK-DRILL",
        manufacturer="Bosch",
        model_number="GBH 2-26 DRE",
        short_description=(
            "SDS-plus rotary hammer, 800 W, 2.7 J impact energy. Suits anchor holes up to 26 mm in "
            "concrete and light chasing work."
        ),
        long_description=(
            "Supplied in a carry case with side handle and depth stop. SDS-plus bits and chisels "
            "are sold at the counter."
        ),
        daily_rate=Decimal("280.00"),
        weekly_rate=Decimal("1120.00"),
        deposit_amount=Decimal("1200.00"),
        late_fee_per_day=Decimal("120.00"),
        replacement_value=Decimal("4200.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="DR",
        units_per_branch={"CBD": 2, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="BR-HILTI-TE1000AVR",
        name="TE 1000-AVR Breaker",
        slug="te-1000-avr-breaker",
        category_code="BREAK-DRILL",
        manufacturer="Hilti",
        model_number="TE 1000-AVR",
        short_description=(
            "Heavy demolition breaker for floors and foundations. Active vibration reduction, 26 J "
            "single impact energy."
        ),
        long_description=(
            "Supplied with a pointed and a flat chisel in a wheeled case. Runs from a standard 16 "
            "A plug."
        ),
        daily_rate=Decimal("620.00"),
        weekly_rate=Decimal("2480.00"),
        deposit_amount=Decimal("2500.00"),
        late_fee_per_day=Decimal("380.00"),
        replacement_value=Decimal("32000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="BR",
        units_per_branch={"CBD": 1, "BLV": 0, "SMW": 0},
    ),
    ProductModelSeed(
        sku="DR-MAKITA-HR2470",
        name="HR2470 Rotary Hammer",
        slug="hr2470-rotary-hammer",
        category_code="BREAK-DRILL",
        manufacturer="Makita",
        model_number="HR2470",
        short_description=(
            "SDS-plus rotary hammer, 780 W, 24 mm capacity in concrete. Three modes for drilling, "
            "hammer drilling and light chiselling."
        ),
        long_description=(
            "A lighter choice for overhead anchor work and long days on a ladder. Supplied in a "
            "carry case with side handle and depth gauge."
        ),
        daily_rate=Decimal("170.00"),
        weekly_rate=Decimal("680.00"),
        deposit_amount=Decimal("600.00"),
        late_fee_per_day=Decimal("80.00"),
        replacement_value=Decimal("3400.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="DR",
        units_per_branch={"CBD": 2, "BLV": 2, "SMW": 1},
    ),
    ProductModelSeed(
        sku="DR-BOSCH-GBH540DCE",
        name="GBH 5-40 DCE Rotary Hammer",
        slug="gbh-5-40-dce-rotary-hammer",
        category_code="BREAK-DRILL",
        manufacturer="Bosch",
        model_number="GBH 5-40 DCE",
        short_description=(
            "SDS-max rotary hammer, 1150 W, 8.8 J impact energy. Drills up to 40 mm in concrete "
            "and handles medium chiselling."
        ),
        long_description=(
            "Suits rebar dowel holes, through holes for services and removing plaster or tile "
            "beds. Supplied in a case with side handle."
        ),
        daily_rate=Decimal("340.00"),
        weekly_rate=Decimal("1360.00"),
        deposit_amount=Decimal("1500.00"),
        late_fee_per_day=Decimal("150.00"),
        replacement_value=Decimal("15500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="DR",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="DR-HILTI-TE70ATC",
        name="TE 70-ATC/AVR Combihammer",
        slug="te-70-atc-avr-combihammer",
        category_code="BREAK-DRILL",
        manufacturer="Hilti",
        model_number="TE 70-ATC/AVR",
        short_description=(
            "SDS-max combihammer with active torque control and vibration reduction. Heavy "
            "drilling and chiselling in reinforced concrete."
        ),
        long_description=(
            "The torque control cuts the motor if the bit jams, which matters when drilling large "
            "diameters off a scaffold."
        ),
        daily_rate=Decimal("480.00"),
        weekly_rate=Decimal("1920.00"),
        deposit_amount=Decimal("2200.00"),
        late_fee_per_day=Decimal("220.00"),
        replacement_value=Decimal("36000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="DR",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="DR-BOSCH-GSH11E",
        name="GSH 11 E Demolition Hammer",
        slug="gsh-11-e-demolition-hammer",
        category_code="BREAK-DRILL",
        manufacturer="Bosch",
        model_number="GSH 11 E",
        short_description=(
            "SDS-max demolition hammer, 1500 W, 16.8 J impact energy, about 10 kg. Wall openings, "
            "tile removal and slab edges."
        ),
        long_description=(
            "Light enough to work horizontally on walls. Supplied with a pointed chisel and a flat "
            "chisel."
        ),
        daily_rate=Decimal("380.00"),
        weekly_rate=Decimal("1520.00"),
        deposit_amount=Decimal("1600.00"),
        late_fee_per_day=Decimal("170.00"),
        replacement_value=Decimal("16500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="DR",
        units_per_branch={"CBD": 2, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="DR-MAKITA-HM1317C",
        name="HM1317C Demolition Hammer",
        slug="hm1317c-demolition-hammer",
        category_code="BREAK-DRILL",
        manufacturer="Makita",
        model_number="HM1317C",
        short_description=(
            "Demolition hammer with 30 mm hex shank, 1510 W, 17 kg class, with anti-vibration "
            "housing. Breaking slabs, steps and footings."
        ),
        long_description=(
            "Works best pointing downward. Supplied with a bull point and a flat chisel in a steel "
            "case."
        ),
        daily_rate=Decimal("420.00"),
        weekly_rate=Decimal("1680.00"),
        deposit_amount=Decimal("1800.00"),
        late_fee_per_day=Decimal("190.00"),
        replacement_value=Decimal("23500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="DR",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="DR-ATLASCOPCO-COBRATT",
        name="Cobra TT Petrol Breaker",
        slug="cobra-tt-petrol-breaker",
        category_code="BREAK-DRILL",
        manufacturer="Atlas Copco",
        model_number="Cobra TT",
        short_description=(
            "Self-contained petrol breaker, about 25 kg. Breaks concrete and asphalt where there "
            "is no power or compressor on site."
        ),
        long_description=(
            "Runs on two-stroke mix, which is sold at the counter. Supplied with a moil point and "
            "a narrow chisel."
        ),
        daily_rate=Decimal("780.00"),
        weekly_rate=Decimal("3120.00"),
        deposit_amount=Decimal("3500.00"),
        late_fee_per_day=Decimal("350.00"),
        replacement_value=Decimal("84000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="DR",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 0},
    ),
    ProductModelSeed(
        sku="DR-BOSCH-GSB16RE",
        name="GSB 16 RE Impact Drill",
        slug="gsb-16-re-impact-drill",
        category_code="BREAK-DRILL",
        manufacturer="Bosch",
        model_number="GSB 16 RE",
        short_description=(
            "Corded impact drill, 750 W, 13 mm keyless chuck. Masonry, timber and steel for "
            "general fixing work."
        ),
        long_description=(
            "A simple drill for wall plugs, shelving and light steelwork. Drill bits are sold "
            "separately."
        ),
        daily_rate=Decimal("90.00"),
        weekly_rate=Decimal("360.00"),
        deposit_amount=Decimal("300.00"),
        late_fee_per_day=Decimal("40.00"),
        replacement_value=Decimal("1900.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="DR",
        units_per_branch={"CBD": 3, "BLV": 3, "SMW": 2},
    ),
    ProductModelSeed(
        sku="DR-DEWALT-DCD996P2",
        name="DCD996 18 V Hammer Drill Driver Kit",
        slug="dcd996-18-v-hammer-drill-driver-kit",
        category_code="BREAK-DRILL",
        manufacturer="DeWalt",
        model_number="DCD996P2",
        short_description=(
            "Cordless brushless hammer drill driver with two 5 Ah batteries and a charger. Three "
            "speeds and a 13 mm metal chuck."
        ),
        long_description=(
            "For work away from a plug point, such as roof timbers, decking and fencing. Both "
            "batteries go out fully charged."
        ),
        daily_rate=Decimal("160.00"),
        weekly_rate=Decimal("640.00"),
        deposit_amount=Decimal("700.00"),
        late_fee_per_day=Decimal("70.00"),
        replacement_value=Decimal("6900.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="DR",
        units_per_branch={"CBD": 2, "BLV": 2, "SMW": 1},
    ),
    ProductModelSeed(
        sku="DR-HUSQVARNA-DM230",
        name="DM 230 Core Drill with Stand",
        slug="dm-230-core-drill-with-stand",
        category_code="BREAK-DRILL",
        manufacturer="Husqvarna",
        model_number="DM 230",
        short_description=(
            "Diamond core drill motor, 1850 W, on a rig stand. Wet coring up to about 150 mm for "
            "plumbing and electrical penetrations."
        ),
        long_description=(
            "Core bits are hired separately by diameter. Needs a water feed and an anchor fixing "
            "for the stand."
        ),
        daily_rate=Decimal("620.00"),
        weekly_rate=Decimal("2480.00"),
        deposit_amount=Decimal("2800.00"),
        late_fee_per_day=Decimal("280.00"),
        replacement_value=Decimal("39500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="DR",
        units_per_branch={"CBD": 1, "BLV": 0, "SMW": 0},
    ),
)
