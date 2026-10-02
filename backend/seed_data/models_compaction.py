"""Product models for the Compaction category.

I list the two models carried over from the prototype first. New models take the
PC tag prefix. The Wacker Neuson rammer keeps RM because its units are already
tagged that way.
"""

from decimal import Decimal

from .types import ProductModelSeed

COMPACTION_MODELS: tuple[ProductModelSeed, ...] = (
    ProductModelSeed(
        sku="PC-WACKER-CP100",
        name="CP 100 Plate Compactor",
        slug="cp-100-plate-compactor",
        category_code="COMPACTION",
        manufacturer="Wacker Neuson",
        model_number="CP 100",
        short_description=(
            "Forward plate compactor, 62 kg, 500 mm plate. Paving, driveways and trench backfill."
        ),
        long_description=(
            "The handle folds so it fits in a bakkie. Takes unleaded petrol and goes out with a "
            "full tank."
        ),
        daily_rate=Decimal("340.00"),
        weekly_rate=Decimal("1360.00"),
        deposit_amount=Decimal("1500.00"),
        late_fee_per_day=Decimal("220.00"),
        replacement_value=Decimal("18500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="PC",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 0},
    ),
    ProductModelSeed(
        sku="RM-WACKER-BS604",
        name="BS 60-4 Trench Rammer",
        slug="bs-60-4-trench-rammer",
        category_code="COMPACTION",
        manufacturer="Wacker Neuson",
        model_number="BS 60-4",
        short_description=(
            "Upright rammer for narrow trenches and cohesive soils. 68 kg, 280 mm shoe."
        ),
        long_description=(
            "Four-stroke engine, so it takes straight unleaded petrol with no oil mix. Transport "
            "it upright."
        ),
        daily_rate=Decimal("395.00"),
        weekly_rate=Decimal("1580.00"),
        deposit_amount=Decimal("1800.00"),
        late_fee_per_day=Decimal("250.00"),
        replacement_value=Decimal("24000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="RM",
        units_per_branch={"CBD": 1, "BLV": 0, "SMW": 0},
    ),
    ProductModelSeed(
        sku="PC-WACKER-VP1550A",
        name="VP1550A Forward Plate Compactor",
        slug="vp1550a-forward-plate-compactor",
        category_code="COMPACTION",
        manufacturer="Wacker Neuson",
        model_number="VP1550A",
        short_description=(
            "Single direction vibratory plate, about 86 kg, 500 mm plate, Honda petrol engine. "
            "Paving sand, sub-base and asphalt patching."
        ),
        long_description=(
            "The standard machine for bedding paving. A rubber mat can be added at the counter to "
            "protect finished pavers."
        ),
        daily_rate=Decimal("360.00"),
        weekly_rate=Decimal("1440.00"),
        deposit_amount=Decimal("1600.00"),
        late_fee_per_day=Decimal("160.00"),
        replacement_value=Decimal("34000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="PC",
        units_per_branch={"CBD": 2, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="PC-HUSQVARNA-LF75LAT",
        name="LF 75 LAT Forward Plate Compactor",
        slug="lf-75-lat-forward-plate-compactor",
        category_code="COMPACTION",
        manufacturer="Husqvarna",
        model_number="LF 75 LAT",
        short_description=(
            "Forward plate compactor, about 95 kg, with a water tank for asphalt work. Driveways, "
            "paths and repair patches."
        ),
        long_description=(
            "The water sprinkler stops hot asphalt sticking to the plate. Also works well on "
            "granular base layers."
        ),
        daily_rate=Decimal("370.00"),
        weekly_rate=Decimal("1480.00"),
        deposit_amount=Decimal("1600.00"),
        late_fee_per_day=Decimal("170.00"),
        replacement_value=Decimal("36000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="PC",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="PC-WACKER-BPU2540A",
        name="BPU 2540A Reversible Plate Compactor",
        slug="bpu-2540a-reversible-plate-compactor",
        category_code="COMPACTION",
        manufacturer="Wacker Neuson",
        model_number="BPU 2540A",
        short_description=(
            "Reversible petrol plate, about 145 kg, 400 mm working width. Trench backfill and base "
            "layers where a forward plate is too light."
        ),
        long_description=(
            "Forward and reverse travel makes it easy to work in a trench without turning. Needs "
            "two people or a ramp to load."
        ),
        daily_rate=Decimal("480.00"),
        weekly_rate=Decimal("1920.00"),
        deposit_amount=Decimal("2200.00"),
        late_fee_per_day=Decimal("220.00"),
        replacement_value=Decimal("78000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="PC",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 0},
    ),
    ProductModelSeed(
        sku="PC-BOMAG-BPR3560D",
        name="BPR 35/60 D Reversible Plate Compactor",
        slug="bpr-35-60-d-reversible-plate-compactor",
        category_code="COMPACTION",
        manufacturer="Bomag",
        model_number="BPR 35/60 D",
        short_description=(
            "Reversible diesel plate, about 220 kg, 600 mm working width. Deep fill, sub-base and "
            "heavy interlocking paving."
        ),
        long_description=(
            "Collected on a trailer or with a crane truck. A lifting eye is fitted for loading by "
            "hoist."
        ),
        daily_rate=Decimal("620.00"),
        weekly_rate=Decimal("2480.00"),
        deposit_amount=Decimal("3000.00"),
        late_fee_per_day=Decimal("280.00"),
        replacement_value=Decimal("118000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="PC",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 0},
    ),
    ProductModelSeed(
        sku="PC-AMMANN-ATR68",
        name="ATR 68 Trench Rammer",
        slug="atr-68-trench-rammer",
        category_code="COMPACTION",
        manufacturer="Ammann",
        model_number="ATR 68",
        short_description=(
            "Upright petrol rammer, about 68 kg with a 280 mm shoe. Cohesive soils in trenches and "
            "around foundations."
        ),
        long_description="Use it where a plate bounces on clay. Takes straight unleaded petrol.",
        daily_rate=Decimal("390.00"),
        weekly_rate=Decimal("1560.00"),
        deposit_amount=Decimal("1800.00"),
        late_fee_per_day=Decimal("180.00"),
        replacement_value=Decimal("44000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="PC",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="PC-BOMAG-BW65H",
        name="BW 65 H Pedestrian Roller",
        slug="bw-65-h-pedestrian-roller",
        category_code="COMPACTION",
        manufacturer="Bomag",
        model_number="BW 65 H",
        short_description=(
            "Hand-guided double drum vibratory roller, 650 mm drums, diesel. Asphalt patching, "
            "paths and sub-base in confined areas."
        ),
        long_description=(
            "Collected on a trailer. Fill the water spray tank before rolling asphalt."
        ),
        daily_rate=Decimal("980.00"),
        weekly_rate=Decimal("3920.00"),
        deposit_amount=Decimal("5000.00"),
        late_fee_per_day=Decimal("440.00"),
        replacement_value=Decimal("285000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="PC",
        units_per_branch={"CBD": 1, "BLV": 0, "SMW": 0},
    ),
)
