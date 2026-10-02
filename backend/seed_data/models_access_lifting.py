"""Product models for the Access and Lifting area.

I split the area into its two child categories. The access gear takes the SC tag
prefix and the lifting gear takes EC, which are the prefixes already printed on
the tower scaffold and the engine crane from the prototype. The prototype gave
no model number for those two, so I describe the size instead of guessing one.
"""

from decimal import Decimal

from .types import ProductModelSeed

ACCESS_LIFTING_MODELS: tuple[ProductModelSeed, ...] = (
    ProductModelSeed(
        sku="SC-INSTANT-TOWER6M",
        name="6 m Aluminium Tower Scaffold",
        slug="6-m-aluminium-tower-scaffold",
        category_code="ACCESS",
        manufacturer="Instant Upright",
        model_number="6 m working height",
        short_description=(
            "Mobile tower to 6 m working height, with guardrails and toe boards. Two-person "
            "assembly."
        ),
        long_description=(
            "Lock the castors and fit the outriggers before anyone climbs. Collect it with a "
            "bakkie or a trailer."
        ),
        daily_rate=Decimal("480.00"),
        weekly_rate=Decimal("1920.00"),
        deposit_amount=Decimal("2200.00"),
        late_fee_per_day=Decimal("300.00"),
        replacement_value=Decimal("28000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="SC",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 0},
    ),
    ProductModelSeed(
        sku="SC-INSTANT-SPAN300",
        name="Span 300 Aluminium Tower 4 m",
        slug="span-300-aluminium-tower-4-m",
        category_code="ACCESS",
        manufacturer="Instant Upright",
        model_number="Span 300",
        short_description=(
            "Narrow aluminium mobile tower to about 4 m working height. Fits through a standard "
            "doorway for indoor work."
        ),
        long_description=(
            "Supplied with platform, guardrails, toe boards and stabilisers. One person can move "
            "it on its castors."
        ),
        daily_rate=Decimal("360.00"),
        weekly_rate=Decimal("1440.00"),
        deposit_amount=Decimal("1600.00"),
        late_fee_per_day=Decimal("160.00"),
        replacement_value=Decimal("19500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="SC",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="SC-CASTOR-SELFLOCK",
        name="Self-Lock Steel Tower 4 m",
        slug="self-lock-steel-tower-4-m",
        category_code="ACCESS",
        manufacturer="Castor & Ladder",
        model_number="Self-Lock 4 m",
        short_description=(
            "Steel frame scaffold tower with castors, platform and guardrails. Plastering, "
            "painting and facade work up to about 4 m."
        ),
        long_description=(
            "The frames slot together without tools or loose fittings. Heavier than aluminium, so "
            "allow two people to erect it."
        ),
        daily_rate=Decimal("260.00"),
        weekly_rate=Decimal("1040.00"),
        deposit_amount=Decimal("1200.00"),
        late_fee_per_day=Decimal("120.00"),
        replacement_value=Decimal("13500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="SC",
        units_per_branch={"CBD": 2, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="SC-CASTOR-CPU214",
        name="Step Extension Ladder 2.4 m to 4.2 m",
        slug="step-extension-ladder-2-4-m-to-4-2-m",
        category_code="ACCESS",
        manufacturer="Castor & Ladder",
        model_number="CPU2/14",
        short_description=(
            "Aluminium ladder that stands as a 2.4 m stepladder or opens to a 4.2 m straight "
            "ladder."
        ),
        long_description="A general purpose ladder for painting, gutters and ceiling work.",
        daily_rate=Decimal("75.00"),
        weekly_rate=Decimal("300.00"),
        deposit_amount=Decimal("300.00"),
        late_fee_per_day=Decimal("40.00"),
        replacement_value=Decimal("2900.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="SC",
        units_per_branch={"CBD": 3, "BLV": 2, "SMW": 2},
    ),
    ProductModelSeed(
        sku="SC-CASTOR-ALF220",
        name="Extension Ladder 3.3 m to 6.0 m",
        slug="extension-ladder-3-3-m-to-6-0-m",
        category_code="ACCESS",
        manufacturer="Castor & Ladder",
        model_number="ALF2/20",
        short_description=(
            "Two section aluminium extension ladder with rope and pulley, 3.3 m closed and 6.0 m "
            "extended."
        ),
        long_description=(
            "Reaches double storey gutters and fascias. Needs roof racks or a bakkie to transport."
        ),
        daily_rate=Decimal("110.00"),
        weekly_rate=Decimal("440.00"),
        deposit_amount=Decimal("500.00"),
        late_fee_per_day=Decimal("50.00"),
        replacement_value=Decimal("4600.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="SC",
        units_per_branch={"CBD": 2, "BLV": 2, "SMW": 1},
    ),
    ProductModelSeed(
        sku="SC-FORMSCAFF-TRESTLE",
        name="Steel Builders Trestle 1.8 m",
        slug="steel-builders-trestle-1-8-m",
        category_code="ACCESS",
        manufacturer="Form-Scaff",
        model_number="Adjustable 1.8 m",
        short_description=(
            "Adjustable steel builders trestle, hired per unit. Two trestles and scaffold boards "
            "make a bricklaying or plastering platform."
        ),
        long_description="The height adjusts with a pin. Ask at the counter about scaffold boards.",
        daily_rate=Decimal("45.00"),
        weekly_rate=Decimal("180.00"),
        deposit_amount=Decimal("150.00"),
        late_fee_per_day=Decimal("40.00"),
        replacement_value=Decimal("900.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="SC",
        units_per_branch={"CBD": 6, "BLV": 5, "SMW": 4},
    ),
    ProductModelSeed(
        sku="EC-SEALEY-CRANE1T",
        name="1 Tonne Engine Crane",
        slug="1-tonne-engine-crane",
        category_code="LIFTING",
        manufacturer="Sealey",
        model_number="1 tonne folding",
        short_description=(
            "Folding hydraulic engine crane, 1000 kg at minimum reach. Workshop and plant room "
            "lifts."
        ),
        long_description=(
            "The legs fold up for transport in a bakkie. The capacity drops as the boom is "
            "extended."
        ),
        daily_rate=Decimal("290.00"),
        weekly_rate=Decimal("1160.00"),
        deposit_amount=Decimal("1200.00"),
        late_fee_per_day=Decimal("190.00"),
        replacement_value=Decimal("11200.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="EC",
        units_per_branch={"CBD": 1, "BLV": 0, "SMW": 0},
    ),
    ProductModelSeed(
        sku="EC-GENIE-SLA15",
        name="SLA-15 Superlift Advantage Material Lift",
        slug="sla-15-superlift-advantage-material-lift",
        category_code="LIFTING",
        manufacturer="Genie",
        model_number="SLA-15",
        short_description=(
            "Manual winch material lift, 363 kg capacity to about 4.9 m. Lifts ducting, beams and "
            "air conditioning units into place."
        ),
        long_description=(
            "Rolls through a standard doorway and sets up without tools. Not for lifting people."
        ),
        daily_rate=Decimal("520.00"),
        weekly_rate=Decimal("2080.00"),
        deposit_amount=Decimal("2500.00"),
        late_fee_per_day=Decimal("230.00"),
        replacement_value=Decimal("72000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="EC",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 0},
    ),
    ProductModelSeed(
        sku="EC-YALE-VSIII1T",
        name="VSIII 1 Tonne Chain Block",
        slug="vsiii-1-tonne-chain-block",
        category_code="LIFTING",
        manufacturer="Yale",
        model_number="VSIII 1000 kg",
        short_description=(
            "Hand chain hoist, 1000 kg capacity, 3 m lift. Engine removal, steel erection and "
            "workshop lifts."
        ),
        long_description=(
            "Hang it from a rated beam clamp or sling. Ask at the counter if you need one."
        ),
        daily_rate=Decimal("110.00"),
        weekly_rate=Decimal("440.00"),
        deposit_amount=Decimal("500.00"),
        late_fee_per_day=Decimal("50.00"),
        replacement_value=Decimal("3400.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="EC",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="EC-TRACTEL-TU16",
        name="Tirfor TU-16 Wire Rope Hoist",
        slug="tirfor-tu-16-wire-rope-hoist",
        category_code="LIFTING",
        manufacturer="Tractel",
        model_number="Tirfor TU-16",
        short_description=(
            "Manual wire rope hoist, 1600 kg lifting capacity, with 20 m of rope. Long pulls for "
            "tree work, recovery and rigging."
        ),
        long_description=(
            "Pulls in any direction over any distance the rope allows. Supplied with the operating "
            "handle."
        ),
        daily_rate=Decimal("160.00"),
        weekly_rate=Decimal("640.00"),
        deposit_amount=Decimal("700.00"),
        late_fee_per_day=Decimal("70.00"),
        replacement_value=Decimal("15500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="EC",
        units_per_branch={"CBD": 1, "BLV": 0, "SMW": 0},
    ),
    ProductModelSeed(
        sku="EC-JUNGHEINRICH-AM22",
        name="AM 22 Hand Pallet Truck",
        slug="am-22-hand-pallet-truck",
        category_code="LIFTING",
        manufacturer="Jungheinrich",
        model_number="AM 22",
        short_description=(
            "Hand pallet truck, 2200 kg capacity, 1150 mm forks. Moving palletised bricks, tiles "
            "and stock on level floors."
        ),
        long_description="Needs a smooth hard surface. Not suitable for gravel or ramps.",
        daily_rate=Decimal("150.00"),
        weekly_rate=Decimal("600.00"),
        deposit_amount=Decimal("700.00"),
        late_fee_per_day=Decimal("70.00"),
        replacement_value=Decimal("7900.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="EC",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
)
