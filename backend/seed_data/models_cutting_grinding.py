"""Product models for the Cutting and Grinding category.

I list the two models carried over from the prototype first. New models take the
CS tag prefix. The Bosch 230 mm grinder keeps AG because its units are already
tagged that way.
"""

from decimal import Decimal

from .types import ProductModelSeed

CUTTING_GRINDING_MODELS: tuple[ProductModelSeed, ...] = (
    ProductModelSeed(
        sku="CS-STIHL-TS420",
        name="TS 420 Cut-off Saw",
        slug="ts-420-cut-off-saw",
        category_code="CUT-GRIND",
        manufacturer="Stihl",
        model_number="TS 420",
        short_description=(
            "Petrol cut-off saw, 350 mm blade, 125 mm cutting depth. Concrete, masonry and steel "
            "with the correct wheel."
        ),
        long_description=(
            "Blades are hired or sold separately. Connect a hose to the water kit to keep dust "
            "down."
        ),
        daily_rate=Decimal("385.00"),
        weekly_rate=Decimal("1540.00"),
        deposit_amount=Decimal("1600.00"),
        late_fee_per_day=Decimal("240.00"),
        replacement_value=Decimal("16800.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="CS",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="AG-BOSCH-GWS22230",
        name="GWS 22-230 Angle Grinder",
        slug="gws-22-230-angle-grinder",
        category_code="CUT-GRIND",
        manufacturer="Bosch",
        model_number="GWS 22-230",
        short_description=(
            "230 mm angle grinder, 2200 W, with guard and side handle. Cutting and grinding "
            "masonry and steel."
        ),
        long_description="Discs are sold separately. Never run it without the guard fitted.",
        daily_rate=Decimal("165.00"),
        weekly_rate=Decimal("660.00"),
        deposit_amount=Decimal("550.00"),
        late_fee_per_day=Decimal("110.00"),
        replacement_value=Decimal("3600.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="AG",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 2},
    ),
    ProductModelSeed(
        sku="CS-HUSQVARNA-K770",
        name="K 770 Power Cutter",
        slug="k-770-power-cutter",
        category_code="CUT-GRIND",
        manufacturer="Husqvarna",
        model_number="K 770",
        short_description=(
            "Petrol power cutter, 350 mm blade, 125 mm cutting depth. Kerbs, pavers, pipes and "
            "slab cuts."
        ),
        long_description=(
            "Fitted with a water kit for wet cutting. Blades are hired or sold separately."
        ),
        daily_rate=Decimal("400.00"),
        weekly_rate=Decimal("1600.00"),
        deposit_amount=Decimal("1700.00"),
        late_fee_per_day=Decimal("180.00"),
        replacement_value=Decimal("21500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="CS",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="CS-HUSQVARNA-FS400LV",
        name="FS 400 LV Floor Saw",
        slug="fs-400-lv-floor-saw",
        category_code="CUT-GRIND",
        manufacturer="Husqvarna",
        model_number="FS 400 LV",
        short_description=(
            "Walk-behind petrol floor saw for blades up to 450 mm and cuts to about 160 mm deep. "
            "Expansion joints and trenches in slabs and asphalt."
        ),
        long_description=(
            "Built-in water tank for wet cutting. Blades are hired separately by size."
        ),
        daily_rate=Decimal("720.00"),
        weekly_rate=Decimal("2880.00"),
        deposit_amount=Decimal("3200.00"),
        late_fee_per_day=Decimal("320.00"),
        replacement_value=Decimal("64000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="CS",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="CS-HUSQVARNA-TS60",
        name="TS 60 Tile Saw",
        slug="ts-60-tile-saw",
        category_code="CUT-GRIND",
        manufacturer="Husqvarna",
        model_number="TS 60",
        short_description=(
            "Electric wet tile saw with a 600 mm cutting length. Porcelain, ceramic and natural "
            "stone tiles."
        ),
        long_description="The head tilts for mitre cuts. The legs fold so it fits in a car boot.",
        daily_rate=Decimal("330.00"),
        weekly_rate=Decimal("1320.00"),
        deposit_amount=Decimal("1400.00"),
        late_fee_per_day=Decimal("150.00"),
        replacement_value=Decimal("23500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="CS",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="CS-HUSQVARNA-TS400F",
        name="TS 400 F Masonry Saw",
        slug="ts-400-f-masonry-saw",
        category_code="CUT-GRIND",
        manufacturer="Husqvarna",
        model_number="TS 400 F",
        short_description=(
            "Electric wet masonry bench saw, 400 mm blade. Bricks, blocks, pavers and kerbs."
        ),
        long_description=(
            "Folding legs and wheels for moving around site. Runs from a single phase supply."
        ),
        daily_rate=Decimal("390.00"),
        weekly_rate=Decimal("1560.00"),
        deposit_amount=Decimal("1700.00"),
        late_fee_per_day=Decimal("180.00"),
        replacement_value=Decimal("41000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="CS",
        units_per_branch={"CBD": 1, "BLV": 0, "SMW": 0},
    ),
    ProductModelSeed(
        sku="CS-MAKITA-SG1251J",
        name="SG1251J Wall Chaser",
        slug="sg1251j-wall-chaser",
        category_code="CUT-GRIND",
        manufacturer="Makita",
        model_number="SG1251J",
        short_description=(
            "Twin blade wall chaser, 125 mm, 1400 W, with a dust port. Chases for conduit and pipe "
            "up to 30 mm deep."
        ),
        long_description=(
            "Connect it to a dust extractor for indoor work. Supplied with two diamond blades."
        ),
        daily_rate=Decimal("300.00"),
        weekly_rate=Decimal("1200.00"),
        deposit_amount=Decimal("1300.00"),
        late_fee_per_day=Decimal("140.00"),
        replacement_value=Decimal("12500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="CS",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="CS-BOSCH-GWS750",
        name="GWS 750-115 Angle Grinder",
        slug="gws-750-115-angle-grinder",
        category_code="CUT-GRIND",
        manufacturer="Bosch",
        model_number="GWS 750-115",
        short_description=(
            "Angle grinder, 115 mm, 750 W. Light cutting, deburring and surface preparation."
        ),
        long_description=(
            "Small enough for one hand work in tight spaces. Discs are sold separately."
        ),
        daily_rate=Decimal("80.00"),
        weekly_rate=Decimal("320.00"),
        deposit_amount=Decimal("250.00"),
        late_fee_per_day=Decimal("40.00"),
        replacement_value=Decimal("1150.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="CS",
        units_per_branch={"CBD": 3, "BLV": 2, "SMW": 2},
    ),
    ProductModelSeed(
        sku="CS-MAKITA-LS1040",
        name="LS1040 Mitre Saw",
        slug="ls1040-mitre-saw",
        category_code="CUT-GRIND",
        manufacturer="Makita",
        model_number="LS1040",
        short_description=(
            "Compound mitre saw, 260 mm blade, 1650 W. Skirting, cornice, decking and framing "
            "timber."
        ),
        long_description="Supplied with a general purpose blade and a dust bag.",
        daily_rate=Decimal("210.00"),
        weekly_rate=Decimal("840.00"),
        deposit_amount=Decimal("800.00"),
        late_fee_per_day=Decimal("90.00"),
        replacement_value=Decimal("6900.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="CS",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="CS-DEWALT-DWE7492",
        name="DWE7492 Table Saw",
        slug="dwe7492-table-saw",
        category_code="CUT-GRIND",
        manufacturer="DeWalt",
        model_number="DWE7492",
        short_description=(
            "Portable table saw, 250 mm blade, 2000 W, 825 mm rip capacity. Sheet material and "
            "site joinery."
        ),
        long_description="Supplied with a push stick, fence and blade guard.",
        daily_rate=Decimal("320.00"),
        weekly_rate=Decimal("1280.00"),
        deposit_amount=Decimal("1400.00"),
        late_fee_per_day=Decimal("140.00"),
        replacement_value=Decimal("17500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="CS",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 0},
    ),
    ProductModelSeed(
        sku="CS-BOSCH-GKS190",
        name="GKS 190 Circular Saw",
        slug="gks-190-circular-saw",
        category_code="CUT-GRIND",
        manufacturer="Bosch",
        model_number="GKS 190",
        short_description=(
            "Hand-held circular saw, 190 mm blade, 1400 W, 70 mm depth of cut. Timber, board and "
            "shutter ply."
        ),
        long_description="Supplied with a parallel guide and a general purpose blade.",
        daily_rate=Decimal("120.00"),
        weekly_rate=Decimal("480.00"),
        deposit_amount=Decimal("400.00"),
        late_fee_per_day=Decimal("50.00"),
        replacement_value=Decimal("2700.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="CS",
        units_per_branch={"CBD": 2, "BLV": 1, "SMW": 1},
    ),
)
