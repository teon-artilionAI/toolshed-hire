"""The catalogue categories.

I keep the seven categories from the prototype with their names and slugs
unchanged, and add five more top level areas for the rest of the range. Access
and Lifting is the only parent. Its two children separate the gear people climb
on from the gear that lifts a load, and its models all sit in the children.
"""

from .types import CategorySeed

CATEGORIES: tuple[CategorySeed, ...] = (
    CategorySeed(
        code="BREAK-DRILL",
        name="Breaking and Drilling",
        slug="breaking-drilling",
        description="Rotary hammers, breakers, drills and core drilling rigs.",
        parent_code=None,
        sort_order=10,
    ),
    CategorySeed(
        code="COMPACTION",
        name="Compaction",
        slug="compaction",
        description="Plate compactors, rammers and pedestrian rollers.",
        parent_code=None,
        sort_order=20,
    ),
    CategorySeed(
        code="CONCRETE-MIX",
        name="Concrete and Mixing",
        slug="concrete-mixing",
        description="Mixers, vibrators, screeds, power trowels and masonry fixing tools.",
        parent_code=None,
        sort_order=30,
    ),
    CategorySeed(
        code="CUT-GRIND",
        name="Cutting and Grinding",
        slug="cutting-grinding",
        description="Cut-off saws, floor saws, tile and masonry saws, grinders and wood saws.",
        parent_code=None,
        sort_order=40,
    ),
    CategorySeed(
        code="FLOOR-PREP",
        name="Sanding and Floor Preparation",
        slug="sanding-floor-preparation",
        description="Floor sanders, hand sanders, concrete grinders, planers and scrapers.",
        parent_code=None,
        sort_order=50,
    ),
    CategorySeed(
        code="ACCESS-LIFT",
        name="Access and Lifting",
        slug="access-lifting",
        description="Equipment for working at height and for lifting or moving loads.",
        parent_code=None,
        sort_order=60,
    ),
    CategorySeed(
        code="ACCESS",
        name="Ladders, Trestles and Towers",
        slug="ladders-trestles-towers",
        description="Ladders, builders trestles and mobile scaffold towers.",
        parent_code="ACCESS-LIFT",
        sort_order=61,
    ),
    CategorySeed(
        code="LIFTING",
        name="Lifting and Material Handling",
        slug="lifting-material-handling",
        description="Cranes, hoists, material lifts and pallet trucks.",
        parent_code="ACCESS-LIFT",
        sort_order=62,
    ),
    CategorySeed(
        code="GARDEN",
        name="Gardening and Landscaping",
        slug="gardening",
        description="Brushcutters, chainsaws, mowers, blowers, tillers and augers.",
        parent_code=None,
        sort_order=70,
    ),
    CategorySeed(
        code="POWER-LIGHT",
        name="Power and Lighting",
        slug="power-lighting",
        description="Generators, portable power stations, site lighting and extension reels.",
        parent_code=None,
        sort_order=80,
    ),
    CategorySeed(
        code="PUMPS",
        name="Pumps and Dewatering",
        slug="pumps-dewatering",
        description="Petrol water and trash pumps, submersible pumps and test pumps.",
        parent_code=None,
        sort_order=90,
    ),
    CategorySeed(
        code="WELDING",
        name="Welding",
        slug="welding",
        description="Stick, MIG and TIG welders, plasma cutting, gas sets and hot air welding.",
        parent_code=None,
        sort_order=100,
    ),
    CategorySeed(
        code="CLEANING",
        name="Cleaning and Floor Care",
        slug="cleaning-floor-care",
        description="Pressure washers, vacuums, carpet and floor machines and drain cleaning.",
        parent_code=None,
        sort_order=110,
    ),
    CategorySeed(
        code="SITE-EQUIP",
        name="Site Equipment",
        slug="site-equipment",
        description="Heaters, fans, dryers, dust control, lasers, scanners and compressed air.",
        parent_code=None,
        sort_order=120,
    ),
)
