"""Product models for the Cleaning and Floor Care category.

This category is new, so nothing here comes from the prototype. Every model
takes the CL tag prefix.
"""

from decimal import Decimal

from .types import ProductModelSeed

CLEANING_MODELS: tuple[ProductModelSeed, ...] = (
    ProductModelSeed(
        sku="CL-KARCHER-HD515C",
        name="HD 5/15 C Pressure Washer",
        slug="hd-5-15-c-pressure-washer",
        category_code="CLEANING",
        manufacturer="Karcher",
        model_number="HD 5/15 C",
        short_description=(
            "Cold water electric pressure washer, 150 bar, 500 L per hour, single phase. Paving, "
            "walls, vehicles and plant."
        ),
        long_description=(
            "Needs a tap with good flow. Supplied with a high pressure hose and lance."
        ),
        daily_rate=Decimal("280.00"),
        weekly_rate=Decimal("1120.00"),
        deposit_amount=Decimal("1200.00"),
        late_fee_per_day=Decimal("130.00"),
        replacement_value=Decimal("17500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="CL",
        units_per_branch={"CBD": 2, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="CL-KARCHER-HD615G",
        name="HD 6/15 G Classic Petrol Pressure Washer",
        slug="hd-6-15-g-classic-petrol-pressure-washer",
        category_code="CLEANING",
        manufacturer="Karcher",
        model_number="HD 6/15 G Classic",
        short_description=(
            "Petrol cold water pressure washer, 150 bar, 600 L per hour. Cleaning where there is "
            "no power on site."
        ),
        long_description=(
            "Needs a tap or a tank feed. Goes out with a full tank of unleaded petrol."
        ),
        daily_rate=Decimal("390.00"),
        weekly_rate=Decimal("1560.00"),
        deposit_amount=Decimal("1700.00"),
        late_fee_per_day=Decimal("180.00"),
        replacement_value=Decimal("27500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="CL",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="CL-KARCHER-HDS614C",
        name="HDS 6/14 C Hot Water Pressure Washer",
        slug="hds-6-14-c-hot-water-pressure-washer",
        category_code="CLEANING",
        manufacturer="Karcher",
        model_number="HDS 6/14 C",
        short_description=(
            "Hot water pressure washer, 140 bar, with a diesel fired burner. Grease, oil and "
            "workshop floors."
        ),
        long_description=(
            "Hot water lifts oil that cold water only spreads. Runs from a single phase plug."
        ),
        daily_rate=Decimal("620.00"),
        weekly_rate=Decimal("2480.00"),
        deposit_amount=Decimal("3000.00"),
        late_fee_per_day=Decimal("280.00"),
        replacement_value=Decimal("86000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="CL",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 0},
    ),
    ProductModelSeed(
        sku="CL-KARCHER-NT652AP",
        name="NT 65/2 Ap Wet and Dry Vacuum",
        slug="nt-65-2-ap-wet-and-dry-vacuum",
        category_code="CLEANING",
        manufacturer="Karcher",
        model_number="NT 65/2 Ap",
        short_description=(
            "Twin motor wet and dry vacuum with a 65 L tank and filter clean. Building dust, "
            "slurry and flood water."
        ),
        long_description=(
            "The drain hose empties the tank without lifting it. Filter bags are sold at the "
            "counter."
        ),
        daily_rate=Decimal("220.00"),
        weekly_rate=Decimal("880.00"),
        deposit_amount=Decimal("900.00"),
        late_fee_per_day=Decimal("100.00"),
        replacement_value=Decimal("21500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="CL",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="CL-KARCHER-PUZZI101",
        name="Puzzi 10/1 Carpet Cleaner",
        slug="puzzi-10-1-carpet-cleaner",
        category_code="CLEANING",
        manufacturer="Karcher",
        model_number="Puzzi 10/1",
        short_description=(
            "Spray extraction cleaner with a 10 L fresh water tank. Carpets, rugs and upholstery."
        ),
        long_description="Carpet shampoo is sold at the counter. Allow a few hours of drying time.",
        daily_rate=Decimal("240.00"),
        weekly_rate=Decimal("960.00"),
        deposit_amount=Decimal("1000.00"),
        late_fee_per_day=Decimal("110.00"),
        replacement_value=Decimal("14500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="CL",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="CL-KARCHER-BDS43150C",
        name="BDS 43/150 C Classic Floor Polisher",
        slug="bds-43-150-c-classic-floor-polisher",
        category_code="CLEANING",
        manufacturer="Karcher",
        model_number="BDS 43/150 C Classic",
        short_description=(
            "Single disc machine, 430 mm, 150 rpm. Scrubbing, stripping and polishing hard floors."
        ),
        long_description=(
            "Supplied with a pad holder. Pads and floor chemicals are sold at the counter."
        ),
        daily_rate=Decimal("260.00"),
        weekly_rate=Decimal("1040.00"),
        deposit_amount=Decimal("1100.00"),
        late_fee_per_day=Decimal("120.00"),
        replacement_value=Decimal("19500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="CL",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="CL-KARCHER-BD5050C",
        name="BD 50/50 C Classic Scrubber Drier",
        slug="bd-50-50-c-classic-scrubber-drier",
        category_code="CLEANING",
        manufacturer="Karcher",
        model_number="BD 50/50 C Bp Classic",
        short_description=(
            "Battery walk-behind scrubber drier, 510 mm working width, 50 L tanks. Shop floors, "
            "halls and warehouses."
        ),
        long_description="Scrubs and dries in one pass. Goes out fully charged with its charger.",
        daily_rate=Decimal("520.00"),
        weekly_rate=Decimal("2080.00"),
        deposit_amount=Decimal("2500.00"),
        late_fee_per_day=Decimal("230.00"),
        replacement_value=Decimal("72000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="CL",
        units_per_branch={"CBD": 1, "BLV": 0, "SMW": 0},
    ),
    ProductModelSeed(
        sku="CL-KARCHER-KM7020C",
        name="KM 70/20 C Push Sweeper",
        slug="km-70-20-c-push-sweeper",
        category_code="CLEANING",
        manufacturer="Karcher",
        model_number="KM 70/20 C",
        short_description=(
            "Manual push sweeper, 700 mm working width with a side brush and 42 L hopper. Paving, "
            "parking bays and workshops."
        ),
        long_description=(
            "No motor and no cable. Sweeps much faster than a broom on large flat areas."
        ),
        daily_rate=Decimal("150.00"),
        weekly_rate=Decimal("600.00"),
        deposit_amount=Decimal("600.00"),
        late_fee_per_day=Decimal("70.00"),
        replacement_value=Decimal("11500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="CL",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 0},
    ),
    ProductModelSeed(
        sku="CL-RIDGID-K400",
        name="K-400 Drain Cleaning Machine",
        slug="k-400-drain-cleaning-machine",
        category_code="CLEANING",
        manufacturer="Ridgid",
        model_number="K-400",
        short_description=(
            "Drum drain cleaning machine with a 23 m cable for 40 mm to 100 mm lines. Blocked "
            "sinks, showers and yard drains."
        ),
        long_description="Supplied with a cutter set and gloves. Runs from a standard plug.",
        daily_rate=Decimal("340.00"),
        weekly_rate=Decimal("1360.00"),
        deposit_amount=Decimal("1500.00"),
        late_fee_per_day=Decimal("150.00"),
        replacement_value=Decimal("24500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="CL",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 0},
    ),
    ProductModelSeed(
        sku="CL-KARCHER-SG44",
        name="SG 4/4 Steam Cleaner",
        slug="sg-4-4-steam-cleaner",
        category_code="CLEANING",
        manufacturer="Karcher",
        model_number="SG 4/4",
        short_description=(
            "Commercial steam cleaner, 4 bar, 4 L tank. Kitchens, grout, tiles and sanitary areas "
            "without chemicals."
        ),
        long_description="Supplied with floor and hand nozzles. Allow it to heat up before use.",
        daily_rate=Decimal("260.00"),
        weekly_rate=Decimal("1040.00"),
        deposit_amount=Decimal("1100.00"),
        late_fee_per_day=Decimal("120.00"),
        replacement_value=Decimal("21500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="CL",
        units_per_branch={"CBD": 1, "BLV": 0, "SMW": 0},
    ),
)
