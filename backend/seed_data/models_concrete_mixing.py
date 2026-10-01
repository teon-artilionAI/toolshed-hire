"""Product models for the Concrete and Mixing category.

I list the two models carried over from the prototype first. New models take the
MX tag prefix. The Enarco poker keeps PV because its units are already tagged
that way. The prototype gave no model number for those two, so I describe the
size instead of guessing one.
"""

from decimal import Decimal

from .types import ProductModelSeed

CONCRETE_MIXING_MODELS: tuple[ProductModelSeed, ...] = (
    ProductModelSeed(
        sku="MX-BAUMAX-140L",
        name="140 L Concrete Mixer",
        slug="140-l-concrete-mixer",
        category_code="CONCRETE-MIX",
        manufacturer="Baumax",
        model_number="140 L tip-up",
        short_description=(
            "Tip-up drum mixer on road-tow frame, 550 W. Suits small slabs, screeds and mortar "
            "batches."
        ),
        long_description=(
            "Mixes roughly one wheelbarrow per batch. Wash the drum out before the mix sets."
        ),
        daily_rate=Decimal("210.00"),
        weekly_rate=Decimal("840.00"),
        deposit_amount=Decimal("800.00"),
        late_fee_per_day=Decimal("140.00"),
        replacement_value=Decimal("6800.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="MX",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="PV-ENARCO-45MM",
        name="Poker Vibrator 45 mm",
        slug="poker-vibrator-45-mm",
        category_code="CONCRETE-MIX",
        manufacturer="Enarco",
        model_number="45 mm head, 4 m shaft",
        short_description=(
            "Concrete poker vibrator with 4 m flexible shaft. Removes air voids from poured slabs "
            "and columns."
        ),
        long_description=(
            "Lower the head in vertically and withdraw it slowly. Supplied with the electric drive "
            "unit."
        ),
        daily_rate=Decimal("245.00"),
        weekly_rate=Decimal("980.00"),
        deposit_amount=Decimal("900.00"),
        late_fee_per_day=Decimal("160.00"),
        replacement_value=Decimal("9400.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="PV",
        units_per_branch={"CBD": 1, "BLV": 0, "SMW": 1},
    ),
    ProductModelSeed(
        sku="MX-BAUMAX-BS360L",
        name="BS360L Concrete Mixer 360 L",
        slug="bs360l-concrete-mixer-360-l",
        category_code="CONCRETE-MIX",
        manufacturer="Baumax",
        model_number="BS360L",
        short_description=(
            "Petrol concrete mixer, 360 L drum, about 200 L mixed batch, on pneumatic tyres. House "
            "slabs, foundations and paving."
        ),
        long_description=(
            "Moved around site by hand or behind a bakkie at walking pace. Goes out with a full "
            "tank of unleaded petrol."
        ),
        daily_rate=Decimal("340.00"),
        weekly_rate=Decimal("1360.00"),
        deposit_amount=Decimal("1500.00"),
        late_fee_per_day=Decimal("150.00"),
        replacement_value=Decimal("22500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="MX",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 0},
    ),
    ProductModelSeed(
        sku="MX-WACKER-CT365A",
        name="CT 36-5A Power Trowel",
        slug="ct-36-5a-power-trowel",
        category_code="CONCRETE-MIX",
        manufacturer="Wacker Neuson",
        model_number="CT 36-5A",
        short_description=(
            "Walk-behind power trowel, 915 mm, with Honda petrol engine. Floating and finishing "
            "garage floors and slabs."
        ),
        long_description=(
            "Supplied with finishing blades. A float pan is available at the counter for the first "
            "pass."
        ),
        daily_rate=Decimal("420.00"),
        weekly_rate=Decimal("1680.00"),
        deposit_amount=Decimal("1800.00"),
        late_fee_per_day=Decimal("190.00"),
        replacement_value=Decimal("46000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="MX",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="MX-WACKER-CT244A",
        name="CT 24-4A Edging Trowel",
        slug="ct-24-4a-edging-trowel",
        category_code="CONCRETE-MIX",
        manufacturer="Wacker Neuson",
        model_number="CT 24-4A",
        short_description=(
            "Edging power trowel, 610 mm, for slab edges, corners and small pours where a full "
            "size machine will not fit."
        ),
        long_description=(
            "Runs right up to walls and around columns. Fits through a standard doorway."
        ),
        daily_rate=Decimal("380.00"),
        weekly_rate=Decimal("1520.00"),
        deposit_amount=Decimal("1600.00"),
        late_fee_per_day=Decimal("170.00"),
        replacement_value=Decimal("39000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="MX",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 0},
    ),
    ProductModelSeed(
        sku="MX-WACKER-IRFU45",
        name="IRFU 45 High Frequency Vibrator",
        slug="irfu-45-high-frequency-vibrator",
        category_code="CONCRETE-MIX",
        manufacturer="Wacker Neuson",
        model_number="IRFU 45",
        short_description=(
            "High frequency internal vibrator, 45 mm head, with built-in converter. Plugs straight "
            "into a single phase supply."
        ),
        long_description=(
            "No separate drive unit to carry. Suits columns, beams and slabs up to medium pours."
        ),
        daily_rate=Decimal("320.00"),
        weekly_rate=Decimal("1280.00"),
        deposit_amount=Decimal("1300.00"),
        late_fee_per_day=Decimal("140.00"),
        replacement_value=Decimal("24500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="MX",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="MX-HUSQVARNA-BV30",
        name="BV 30 Vibrating Screed",
        slug="bv-30-vibrating-screed",
        category_code="CONCRETE-MIX",
        manufacturer="Husqvarna",
        model_number="BV 30",
        short_description=(
            "Petrol vibrating screed drive unit with a 3 m aluminium blade. Levels and compacts a "
            "slab in one pass."
        ),
        long_description=(
            "One person can pull it across the shutter boards. Other blade lengths can be ordered "
            "a day ahead."
        ),
        daily_rate=Decimal("360.00"),
        weekly_rate=Decimal("1440.00"),
        deposit_amount=Decimal("1500.00"),
        late_fee_per_day=Decimal("160.00"),
        replacement_value=Decimal("31500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="MX",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 0},
    ),
    ProductModelSeed(
        sku="MX-BOSCH-GRW12E",
        name="GRW 12 E Paddle Mixer",
        slug="grw-12-e-paddle-mixer",
        category_code="CONCRETE-MIX",
        manufacturer="Bosch",
        model_number="GRW 12 E",
        short_description=(
            "Hand-held stirrer, 1200 W, with a 140 mm paddle. Tile adhesive, plaster, screed and "
            "paint."
        ),
        long_description=(
            "Mixes a full bucket without lumps. Rinse the paddle in clean water straight after use."
        ),
        daily_rate=Decimal("130.00"),
        weekly_rate=Decimal("520.00"),
        deposit_amount=Decimal("450.00"),
        late_fee_per_day=Decimal("60.00"),
        replacement_value=Decimal("5400.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="MX",
        units_per_branch={"CBD": 2, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="MX-LASHER-WHEELBARROW",
        name="Builders Wheelbarrow 65 L",
        slug="builders-wheelbarrow-65-l",
        category_code="CONCRETE-MIX",
        manufacturer="Lasher",
        model_number="Concrete 65 L",
        short_description=(
            "Steel pan builders wheelbarrow, 65 L, with a pneumatic wheel. Moving concrete, sand, "
            "bricks and rubble."
        ),
        long_description="Usually hired with a mixer. Hose it out before the concrete sets.",
        daily_rate=Decimal("45.00"),
        weekly_rate=Decimal("180.00"),
        deposit_amount=Decimal("150.00"),
        late_fee_per_day=Decimal("40.00"),
        replacement_value=Decimal("1350.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="MX",
        units_per_branch={"CBD": 4, "BLV": 4, "SMW": 3},
    ),
    ProductModelSeed(
        sku="MX-HIKOKI-VB16Y",
        name="VB16Y Rebar Cutter Bender",
        slug="vb16y-rebar-cutter-bender",
        category_code="CONCRETE-MIX",
        manufacturer="HiKOKI",
        model_number="VB16Y",
        short_description=(
            "Electric rebar cutter and bender for bar up to 16 mm. Cuts and bends on site without "
            "a bench."
        ),
        long_description=(
            "Saves a trip to the steel merchant for small corrections. Runs from a standard plug."
        ),
        daily_rate=Decimal("290.00"),
        weekly_rate=Decimal("1160.00"),
        deposit_amount=Decimal("1300.00"),
        late_fee_per_day=Decimal("130.00"),
        replacement_value=Decimal("24500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="MX",
        units_per_branch={"CBD": 1, "BLV": 0, "SMW": 0},
    ),
    ProductModelSeed(
        sku="MX-HILTI-DX5",
        name="DX 5 Powder-Actuated Tool",
        slug="dx-5-powder-actuated-tool",
        category_code="CONCRETE-MIX",
        manufacturer="Hilti",
        model_number="DX 5",
        short_description=(
            "Powder-actuated fastening tool for fixing track, brackets and timber plates to "
            "concrete and steel."
        ),
        long_description=(
            "Nails and cartridges are sold separately. Eye and hearing protection must be worn."
        ),
        daily_rate=Decimal("240.00"),
        weekly_rate=Decimal("960.00"),
        deposit_amount=Decimal("1200.00"),
        late_fee_per_day=Decimal("110.00"),
        replacement_value=Decimal("17500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="MX",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
)
