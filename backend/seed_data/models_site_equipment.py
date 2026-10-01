"""Product models for the Site Equipment category.

This category is new, so nothing here comes from the prototype. Every model
takes the ST tag prefix. Site lighting sits with the generators under Power and
Lighting, because that is where the prototype put it.
"""

from decimal import Decimal

from .types import ProductModelSeed

SITE_EQUIPMENT_MODELS: tuple[ProductModelSeed, ...] = (
    ProductModelSeed(
        sku="ST-MASTER-BV110E",
        name="BV 110 E Indirect Diesel Heater",
        slug="bv-110-e-indirect-diesel-heater",
        category_code="SITE-EQUIP",
        manufacturer="Master",
        model_number="BV 110 E",
        short_description=(
            "Indirect fired diesel space heater, about 34 kW, with a flue connection. Clean dry "
            "heat for tents, halls and curing screeds."
        ),
        long_description=(
            "Exhaust goes out through the flue, so the heated air stays clean. Needs a plug point "
            "for the fan."
        ),
        daily_rate=Decimal("360.00"),
        weekly_rate=Decimal("1440.00"),
        deposit_amount=Decimal("1600.00"),
        late_fee_per_day=Decimal("160.00"),
        replacement_value=Decimal("34000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="ST",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 0},
    ),
    ProductModelSeed(
        sku="ST-MASTER-BLP33M",
        name="BLP 33 M Gas Space Heater",
        slug="blp-33-m-gas-space-heater",
        category_code="SITE-EQUIP",
        manufacturer="Master",
        model_number="BLP 33 M",
        short_description=(
            "LPG blow heater, up to about 33 kW. Drying plaster and heating well ventilated "
            "workshops."
        ),
        long_description="The gas cylinder is not included. Use it only where there is fresh air.",
        daily_rate=Decimal("190.00"),
        weekly_rate=Decimal("760.00"),
        deposit_amount=Decimal("800.00"),
        late_fee_per_day=Decimal("90.00"),
        replacement_value=Decimal("6400.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="ST",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="ST-MASTER-DF30P",
        name="DF 30 P Drum Fan",
        slug="df-30-p-drum-fan",
        category_code="SITE-EQUIP",
        manufacturer="Master",
        model_number="DF 30 P",
        short_description=(
            "Drum fan, about 750 mm, on wheels. Cooling and ventilating workshops, halls and "
            "marquees."
        ),
        long_description="Tilts to aim the airflow. Runs from a standard plug.",
        daily_rate=Decimal("150.00"),
        weekly_rate=Decimal("600.00"),
        deposit_amount=Decimal("600.00"),
        late_fee_per_day=Decimal("70.00"),
        replacement_value=Decimal("7600.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="ST",
        units_per_branch={"CBD": 2, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="ST-MASTER-DH752",
        name="DH 752 Dehumidifier",
        slug="dh-752-dehumidifier",
        category_code="SITE-EQUIP",
        manufacturer="Master",
        model_number="DH 752",
        short_description=(
            "Building dryer that extracts up to about 47 L per day. Drying screeds, plaster and "
            "water damage."
        ),
        long_description=(
            "Close doors and windows while it runs. Empties into its tank or through a drain hose."
        ),
        daily_rate=Decimal("320.00"),
        weekly_rate=Decimal("1280.00"),
        deposit_amount=Decimal("1400.00"),
        late_fee_per_day=Decimal("140.00"),
        replacement_value=Decimal("27500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="ST",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="ST-MAKITA-VC4210L",
        name="VC4210L Dust Extractor",
        slug="vc4210l-dust-extractor",
        category_code="SITE-EQUIP",
        manufacturer="Makita",
        model_number="VC4210L",
        short_description=(
            "L class dust extractor, 42 L, with automatic filter cleaning and a power tool socket."
        ),
        long_description=(
            "Starts and stops with the tool plugged into it. Hire it with a wall chaser, planer or "
            "sander."
        ),
        daily_rate=Decimal("220.00"),
        weekly_rate=Decimal("880.00"),
        deposit_amount=Decimal("900.00"),
        late_fee_per_day=Decimal("100.00"),
        replacement_value=Decimal("13500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="ST",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="ST-BOSCH-GRL300HV",
        name="GRL 300 HV Rotary Laser Level",
        slug="grl-300-hv-rotary-laser-level",
        category_code="SITE-EQUIP",
        manufacturer="Bosch",
        model_number="GRL 300 HV",
        short_description=(
            "Self levelling rotary laser with receiver, tripod and staff. Slab levels, foundations "
            "and ceiling grids."
        ),
        long_description="Works horizontally and vertically. Supplied in a case with batteries.",
        daily_rate=Decimal("320.00"),
        weekly_rate=Decimal("1280.00"),
        deposit_amount=Decimal("1500.00"),
        late_fee_per_day=Decimal("140.00"),
        replacement_value=Decimal("19500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="ST",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="ST-BOSCH-GLL380",
        name="GLL 3-80 Line Laser",
        slug="gll-3-80-line-laser",
        category_code="SITE-EQUIP",
        manufacturer="Bosch",
        model_number="GLL 3-80",
        short_description="Three plane line laser for tiling, drywall, cupboards and ceilings.",
        long_description="Supplied with a mount and batteries in a carry case.",
        daily_rate=Decimal("150.00"),
        weekly_rate=Decimal("600.00"),
        deposit_amount=Decimal("700.00"),
        late_fee_per_day=Decimal("70.00"),
        replacement_value=Decimal("6800.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="ST",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="ST-BOSCH-DTECT200C",
        name="D-tect 200 C Wall Scanner",
        slug="d-tect-200-c-wall-scanner",
        category_code="SITE-EQUIP",
        manufacturer="Bosch",
        model_number="D-tect 200 C",
        short_description=(
            "Wall scanner that finds rebar, pipes and live cables before drilling or chasing, to "
            "about 200 mm deep."
        ),
        long_description=(
            "Scan before every core hole or chase. Supplied in a case with a battery and charger."
        ),
        daily_rate=Decimal("190.00"),
        weekly_rate=Decimal("760.00"),
        deposit_amount=Decimal("900.00"),
        late_fee_per_day=Decimal("90.00"),
        replacement_value=Decimal("16500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="ST",
        units_per_branch={"CBD": 1, "BLV": 0, "SMW": 0},
    ),
    ProductModelSeed(
        sku="ST-ATLASCOPCO-XAS88",
        name="XAS 88 Towable Compressor",
        slug="xas-88-towable-compressor",
        category_code="SITE-EQUIP",
        manufacturer="Atlas Copco",
        model_number="XAS 88",
        short_description=(
            "Towable diesel screw compressor, about 175 cfm at 7 bar. Runs two pneumatic breakers."
        ),
        long_description="Needs a tow bar. Air hoses and breakers are quoted separately.",
        daily_rate=Decimal("1150.00"),
        weekly_rate=Decimal("4600.00"),
        deposit_amount=Decimal("6000.00"),
        late_fee_per_day=Decimal("520.00"),
        replacement_value=Decimal("340000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="ST",
        units_per_branch={"CBD": 1, "BLV": 0, "SMW": 0},
    ),
)
