"""Product models for the Sanding and Floor Preparation category.

This category is new, so nothing here comes from the prototype. Every model
takes the SD tag prefix.
"""

from decimal import Decimal

from .types import ProductModelSeed

FLOOR_PREP_MODELS: tuple[ProductModelSeed, ...] = (
    ProductModelSeed(
        sku="SD-LAGLER-HUMMEL",
        name="Hummel Belt Floor Sander",
        slug="hummel-belt-floor-sander",
        category_code="FLOOR-PREP",
        manufacturer="Lagler",
        model_number="Hummel",
        short_description=(
            "Belt sander for timber floors, 200 mm drum, single phase. Strips old finish and "
            "levels boards before sealing."
        ),
        long_description=(
            "Sanding belts are sold by grit at the counter. The machine goes out with a dust bag "
            "and a tool kit."
        ),
        daily_rate=Decimal("520.00"),
        weekly_rate=Decimal("2080.00"),
        deposit_amount=Decimal("2500.00"),
        late_fee_per_day=Decimal("230.00"),
        replacement_value=Decimal("165000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="SD",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="SD-LAGLER-FLIP",
        name="Flip Edge Sander",
        slug="flip-edge-sander",
        category_code="FLOOR-PREP",
        manufacturer="Lagler",
        model_number="Flip",
        short_description=(
            "Edge sander for floor perimeters, stairs and corners that the belt sander cannot "
            "reach."
        ),
        long_description=(
            "Usually hired together with the Hummel. Sanding discs are sold by grit at the counter."
        ),
        daily_rate=Decimal("300.00"),
        weekly_rate=Decimal("1200.00"),
        deposit_amount=Decimal("1300.00"),
        late_fee_per_day=Decimal("140.00"),
        replacement_value=Decimal("46000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="SD",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="SD-BOSCH-GEX125150",
        name="GEX 125-150 AVE Random Orbit Sander",
        slug="gex-125-150-ave-random-orbit-sander",
        category_code="FLOOR-PREP",
        manufacturer="Bosch",
        model_number="GEX 125-150 AVE",
        short_description=(
            "Random orbit sander, 400 W, takes 125 mm and 150 mm pads, with vibration damping and "
            "a dust extraction port."
        ),
        long_description=(
            "A good finishing sander for doors, counters and furniture. Sanding discs are sold "
            "separately."
        ),
        daily_rate=Decimal("110.00"),
        weekly_rate=Decimal("440.00"),
        deposit_amount=Decimal("400.00"),
        late_fee_per_day=Decimal("50.00"),
        replacement_value=Decimal("5600.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="SD",
        units_per_branch={"CBD": 2, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="SD-MAKITA-9403",
        name="9403 Belt Sander",
        slug="9403-belt-sander",
        category_code="FLOOR-PREP",
        manufacturer="Makita",
        model_number="9403",
        short_description=(
            "Belt sander, 100 mm wide, 1200 W, with a dust bag. Fast stock removal on doors, "
            "counters and decking."
        ),
        long_description=(
            "Heavy enough to do the work under its own weight. Belts are sold by grit."
        ),
        daily_rate=Decimal("140.00"),
        weekly_rate=Decimal("560.00"),
        deposit_amount=Decimal("500.00"),
        late_fee_per_day=Decimal("60.00"),
        replacement_value=Decimal("6400.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="SD",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="SD-MAKITA-BO3710",
        name="BO3710 Orbital Sander",
        slug="bo3710-orbital-sander",
        category_code="FLOOR-PREP",
        manufacturer="Makita",
        model_number="BO3710",
        short_description=(
            "Third sheet orbital finishing sander, 190 W. Paint preparation and fine finishing on "
            "flat surfaces."
        ),
        long_description=(
            "Takes standard sandpaper sheets cut to size, which are sold at the counter."
        ),
        daily_rate=Decimal("70.00"),
        weekly_rate=Decimal("280.00"),
        deposit_amount=Decimal("250.00"),
        late_fee_per_day=Decimal("40.00"),
        replacement_value=Decimal("1500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="SD",
        units_per_branch={"CBD": 2, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="SD-FESTOOL-LHS2225",
        name="Planex LHS 2 225 Drywall Sander",
        slug="planex-lhs-2-225-drywall-sander",
        category_code="FLOOR-PREP",
        manufacturer="Festool",
        model_number="LHS 2 225",
        short_description=(
            "Long reach drywall sander, 225 mm head, for walls and ceilings. Works with a dust "
            "extractor."
        ),
        long_description=(
            "Hire it with a dust extractor for a nearly dust free finish on skimmed walls and "
            "ceilings."
        ),
        daily_rate=Decimal("340.00"),
        weekly_rate=Decimal("1360.00"),
        deposit_amount=Decimal("1500.00"),
        late_fee_per_day=Decimal("150.00"),
        replacement_value=Decimal("24500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="SD",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="SD-HUSQVARNA-PG280",
        name="PG 280 Floor Grinder",
        slug="pg-280-floor-grinder",
        category_code="FLOOR-PREP",
        manufacturer="Husqvarna",
        model_number="PG 280",
        short_description=(
            "Single disc concrete floor grinder, 280 mm, single phase. Removes coatings, adhesive "
            "and high spots."
        ),
        long_description=(
            "Diamond tooling is hired separately. Connect a dust extractor before grinding indoors."
        ),
        daily_rate=Decimal("680.00"),
        weekly_rate=Decimal("2720.00"),
        deposit_amount=Decimal("3000.00"),
        late_fee_per_day=Decimal("310.00"),
        replacement_value=Decimal("72000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="SD",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 0},
    ),
    ProductModelSeed(
        sku="SD-HUSQVARNA-S26",
        name="S 26 Dust Extractor",
        slug="s-26-dust-extractor",
        category_code="FLOOR-PREP",
        manufacturer="Husqvarna",
        model_number="S 26",
        short_description=(
            "HEPA dust extractor for floor grinders and hand-held concrete tools, single phase."
        ),
        long_description=(
            "Uses a continuous bagging system so fine dust is never tipped out. Bags are sold at "
            "the counter."
        ),
        daily_rate=Decimal("350.00"),
        weekly_rate=Decimal("1400.00"),
        deposit_amount=Decimal("1500.00"),
        late_fee_per_day=Decimal("160.00"),
        replacement_value=Decimal("36000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="SD",
        units_per_branch={"CBD": 1, "BLV": 0, "SMW": 0},
    ),
    ProductModelSeed(
        sku="SD-MAKITA-PC5010C",
        name="PC5010C Concrete Planer",
        slug="pc5010c-concrete-planer",
        category_code="FLOOR-PREP",
        manufacturer="Makita",
        model_number="PC5010C",
        short_description=(
            "Hand-held concrete planer, 125 mm diamond cup wheel, 1400 W, with a dust shroud. "
            "Levels joints and removes thin coatings."
        ),
        long_description=(
            "Supplied with a diamond cup wheel. Connect a dust extractor for indoor work."
        ),
        daily_rate=Decimal("280.00"),
        weekly_rate=Decimal("1120.00"),
        deposit_amount=Decimal("1200.00"),
        late_fee_per_day=Decimal("130.00"),
        replacement_value=Decimal("11500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="SD",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 0},
    ),
    ProductModelSeed(
        sku="SD-MAKITA-HK1820",
        name="HK1820 Power Scraper",
        slug="hk1820-power-scraper",
        category_code="FLOOR-PREP",
        manufacturer="Makita",
        model_number="HK1820",
        short_description=(
            "SDS-plus power scraper, 550 W. Lifts tiles, vinyl, adhesive and loose plaster."
        ),
        long_description="Supplied with a wide scraper blade and a tile chisel in a carry case.",
        daily_rate=Decimal("180.00"),
        weekly_rate=Decimal("720.00"),
        deposit_amount=Decimal("700.00"),
        late_fee_per_day=Decimal("80.00"),
        replacement_value=Decimal("7900.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="SD",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
)
