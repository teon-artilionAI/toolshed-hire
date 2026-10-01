"""Product models for the Gardening and Landscaping category.

I list the two models carried over from the prototype first. Every model takes
the BC tag prefix that is already printed on the brushcutters. The chipper had
no tagged units in the prototype, so all of its units are generated.
"""

from decimal import Decimal

from .types import ProductModelSeed

GARDENING_MODELS: tuple[ProductModelSeed, ...] = (
    ProductModelSeed(
        sku="BC-STIHL-FS240",
        name="FS 240 Brushcutter",
        slug="fs-240-brushcutter",
        category_code="GARDEN",
        manufacturer="Stihl",
        model_number="FS 240",
        short_description=(
            "Petrol brushcutter with grass blade and nylon head. Verges, embankments and heavy "
            "growth."
        ),
        long_description=(
            "Supplied with a harness and a face shield. Runs on two-stroke mix, which is sold at "
            "the counter."
        ),
        daily_rate=Decimal("195.00"),
        weekly_rate=Decimal("780.00"),
        deposit_amount=Decimal("700.00"),
        late_fee_per_day=Decimal("130.00"),
        replacement_value=Decimal("8900.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="BC",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 0},
    ),
    ProductModelSeed(
        sku="BC-STIHL-GH370",
        name="GH 370 Chipper Shredder",
        slug="gh-370-chipper-shredder",
        category_code="GARDEN",
        manufacturer="Stihl",
        model_number="GH 370",
        short_description=(
            "Petrol garden shredder, 75 mm branch capacity. Reduces prunings to mulch on site."
        ),
        long_description="Feed branches butt end first. Hearing and eye protection must be worn.",
        daily_rate=Decimal("425.00"),
        weekly_rate=Decimal("1700.00"),
        deposit_amount=Decimal("1800.00"),
        late_fee_per_day=Decimal("270.00"),
        replacement_value=Decimal("21000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="BC",
        units_per_branch={"CBD": 1, "BLV": 0, "SMW": 1},
    ),
    ProductModelSeed(
        sku="BC-STIHL-MS250",
        name="MS 250 Chainsaw",
        slug="ms-250-chainsaw",
        category_code="GARDEN",
        manufacturer="Stihl",
        model_number="MS 250",
        short_description=(
            "Petrol chainsaw, 45 cc, 40 cm bar. Felling small trees, limbing and cutting firewood."
        ),
        long_description=(
            "Goes out with a sharp chain and full bar oil. Chaps, gloves and a helmet are sold at "
            "the counter."
        ),
        daily_rate=Decimal("260.00"),
        weekly_rate=Decimal("1040.00"),
        deposit_amount=Decimal("1200.00"),
        late_fee_per_day=Decimal("120.00"),
        replacement_value=Decimal("9900.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="BC",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 2},
    ),
    ProductModelSeed(
        sku="BC-HUSQVARNA-365",
        name="365 Chainsaw",
        slug="365-chainsaw",
        category_code="GARDEN",
        manufacturer="Husqvarna",
        model_number="365",
        short_description=(
            "Professional petrol chainsaw, 70 cc class, 50 cm bar. Larger felling and storm clean "
            "up."
        ),
        long_description=(
            "For experienced users only. Goes out with a sharp chain and full bar oil."
        ),
        daily_rate=Decimal("340.00"),
        weekly_rate=Decimal("1360.00"),
        deposit_amount=Decimal("1500.00"),
        late_fee_per_day=Decimal("150.00"),
        replacement_value=Decimal("15500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="BC",
        units_per_branch={"CBD": 1, "BLV": 0, "SMW": 1},
    ),
    ProductModelSeed(
        sku="BC-STIHL-HT133",
        name="HT 133 Pole Pruner",
        slug="ht-133-pole-pruner",
        category_code="GARDEN",
        manufacturer="Stihl",
        model_number="HT 133",
        short_description=(
            "Telescopic petrol pole pruner that reaches branches about 5 m up while the user stays "
            "on the ground."
        ),
        long_description="Avoids ladder work for high pruning. Supplied with a shoulder strap.",
        daily_rate=Decimal("280.00"),
        weekly_rate=Decimal("1120.00"),
        deposit_amount=Decimal("1200.00"),
        late_fee_per_day=Decimal("130.00"),
        replacement_value=Decimal("16500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="BC",
        units_per_branch={"CBD": 1, "BLV": 0, "SMW": 1},
    ),
    ProductModelSeed(
        sku="BC-HONDA-HRJ216",
        name="HRJ216 Petrol Lawnmower",
        slug="hrj216-petrol-lawnmower",
        category_code="GARDEN",
        manufacturer="Honda",
        model_number="HRJ216",
        short_description=(
            "Petrol rotary lawnmower, 530 mm cut, with a grass catcher. Medium and large lawns."
        ),
        long_description=(
            "Four-stroke engine that takes straight unleaded petrol. Goes out with a full tank."
        ),
        daily_rate=Decimal("190.00"),
        weekly_rate=Decimal("760.00"),
        deposit_amount=Decimal("800.00"),
        late_fee_per_day=Decimal("90.00"),
        replacement_value=Decimal("12500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="BC",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 2},
    ),
    ProductModelSeed(
        sku="BC-STIHL-HS45",
        name="HS 45 Hedge Trimmer",
        slug="hs-45-hedge-trimmer",
        category_code="GARDEN",
        manufacturer="Stihl",
        model_number="HS 45",
        short_description=(
            "Petrol hedge trimmer with a 60 cm double sided blade. Hedges and shrubs up to finger "
            "thick growth."
        ),
        long_description=(
            "Light enough for long hedges. Runs on two-stroke mix, which is sold at the counter."
        ),
        daily_rate=Decimal("160.00"),
        weekly_rate=Decimal("640.00"),
        deposit_amount=Decimal("600.00"),
        late_fee_per_day=Decimal("70.00"),
        replacement_value=Decimal("6400.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="BC",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="BC-STIHL-BR600",
        name="BR 600 Backpack Blower",
        slug="br-600-backpack-blower",
        category_code="GARDEN",
        manufacturer="Stihl",
        model_number="BR 600",
        short_description=(
            "Backpack petrol blower for clearing leaves and cuttings from large gardens, parking "
            "areas and sites."
        ),
        long_description="The strongest blower on the shelf. Hearing protection must be worn.",
        daily_rate=Decimal("190.00"),
        weekly_rate=Decimal("760.00"),
        deposit_amount=Decimal("800.00"),
        late_fee_per_day=Decimal("90.00"),
        replacement_value=Decimal("13500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="BC",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="BC-HUSQVARNA-TF338",
        name="TF 338 Garden Tiller",
        slug="tf-338-garden-tiller",
        category_code="GARDEN",
        manufacturer="Husqvarna",
        model_number="TF 338",
        short_description=(
            "Petrol front tine tiller, 950 mm working width. Breaks ground for new lawns and "
            "vegetable beds."
        ),
        long_description=(
            "Water hard ground the day before tilling. Fits in a bakkie with the handle folded."
        ),
        daily_rate=Decimal("380.00"),
        weekly_rate=Decimal("1520.00"),
        deposit_amount=Decimal("1600.00"),
        late_fee_per_day=Decimal("170.00"),
        replacement_value=Decimal("19500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="BC",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="BC-STIHL-BT131",
        name="BT 131 Earth Auger",
        slug="bt-131-earth-auger",
        category_code="GARDEN",
        manufacturer="Stihl",
        model_number="BT 131",
        short_description=(
            "One person petrol earth auger with a 150 mm bit. Holes for fence posts, poles and "
            "planting."
        ),
        long_description="Other bit diameters can be ordered a day ahead. Not for rocky ground.",
        daily_rate=Decimal("360.00"),
        weekly_rate=Decimal("1440.00"),
        deposit_amount=Decimal("1500.00"),
        late_fee_per_day=Decimal("160.00"),
        replacement_value=Decimal("21500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="BC",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="BC-STIHL-FS55",
        name="FS 55 Grass Trimmer",
        slug="fs-55-grass-trimmer",
        category_code="GARDEN",
        manufacturer="Stihl",
        model_number="FS 55",
        short_description=(
            "Light petrol grass trimmer with a nylon head. Lawn edges and small gardens."
        ),
        long_description="Trimmer line is sold at the counter. Runs on two-stroke mix.",
        daily_rate=Decimal("130.00"),
        weekly_rate=Decimal("520.00"),
        deposit_amount=Decimal("450.00"),
        late_fee_per_day=Decimal("60.00"),
        replacement_value=Decimal("4400.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="BC",
        units_per_branch={"CBD": 2, "BLV": 1, "SMW": 2},
    ),
)
