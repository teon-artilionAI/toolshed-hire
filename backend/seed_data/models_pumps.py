"""Product models for the Pumps and Dewatering category.

This category is new, so nothing here comes from the prototype. Every model
takes the PU tag prefix.
"""

from decimal import Decimal

from .types import ProductModelSeed

PUMPS_MODELS: tuple[ProductModelSeed, ...] = (
    ProductModelSeed(
        sku="PU-HONDA-WB20XT",
        name="WB20XT Water Pump 50 mm",
        slug="wb20xt-water-pump-50-mm",
        category_code="PUMPS",
        manufacturer="Honda",
        model_number="WB20XT",
        short_description=(
            "Petrol centrifugal pump, 50 mm ports, about 600 L per minute. Clean water transfer, "
            "pools and flooded areas."
        ),
        long_description=(
            "Supplied with a suction hose and strainer. Delivery hose is available at the counter."
        ),
        daily_rate=Decimal("190.00"),
        weekly_rate=Decimal("760.00"),
        deposit_amount=Decimal("800.00"),
        late_fee_per_day=Decimal("90.00"),
        replacement_value=Decimal("8900.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="PU",
        units_per_branch={"CBD": 2, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="PU-HONDA-WB30XT",
        name="WB30XT Water Pump 80 mm",
        slug="wb30xt-water-pump-80-mm",
        category_code="PUMPS",
        manufacturer="Honda",
        model_number="WB30XT",
        short_description=(
            "Petrol centrifugal pump, 80 mm ports, about 1100 L per minute. Dams, tanks and large "
            "volumes of clean water."
        ),
        long_description=(
            "Supplied with a suction hose and strainer. Prime the pump body before starting."
        ),
        daily_rate=Decimal("230.00"),
        weekly_rate=Decimal("920.00"),
        deposit_amount=Decimal("1000.00"),
        late_fee_per_day=Decimal("100.00"),
        replacement_value=Decimal("11500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="PU",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="PU-HONDA-WT30X",
        name="WT30X Trash Pump 80 mm",
        slug="wt30x-trash-pump-80-mm",
        category_code="PUMPS",
        manufacturer="Honda",
        model_number="WT30X",
        short_description=(
            "Petrol trash pump, 80 mm ports, passes solids up to about 28 mm. Excavations, muddy "
            "water and spills."
        ),
        long_description="The pump housing opens without tools for clearing blockages.",
        daily_rate=Decimal("380.00"),
        weekly_rate=Decimal("1520.00"),
        deposit_amount=Decimal("1700.00"),
        late_fee_per_day=Decimal("170.00"),
        replacement_value=Decimal("33500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="PU",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="PU-HONDA-WX10",
        name="WX10 Water Pump 25 mm",
        slug="wx10-water-pump-25-mm",
        category_code="PUMPS",
        manufacturer="Honda",
        model_number="WX10",
        short_description=(
            "Lightweight four-stroke pump, 25 mm ports, about 6 kg. Garden irrigation and tank "
            "transfer."
        ),
        long_description="Light enough to carry in one hand. Takes straight unleaded petrol.",
        daily_rate=Decimal("140.00"),
        weekly_rate=Decimal("560.00"),
        deposit_amount=Decimal("600.00"),
        late_fee_per_day=Decimal("60.00"),
        replacement_value=Decimal("6400.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="PU",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="PU-WACKER-PDT3A",
        name="PDT 3A Diaphragm Pump",
        slug="pdt-3a-diaphragm-pump",
        category_code="PUMPS",
        manufacturer="Wacker Neuson",
        model_number="PDT 3A",
        short_description=(
            "Petrol diaphragm pump, 80 mm ports, can run dry without damage. Sludge, slurry and "
            "seepage water."
        ),
        long_description="Suits slow seepage where a centrifugal pump would lose its prime.",
        daily_rate=Decimal("400.00"),
        weekly_rate=Decimal("1600.00"),
        deposit_amount=Decimal("1800.00"),
        late_fee_per_day=Decimal("180.00"),
        replacement_value=Decimal("48000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="PU",
        units_per_branch={"CBD": 1, "BLV": 0, "SMW": 0},
    ),
    ProductModelSeed(
        sku="PU-TSURUMI-HS24S",
        name="HS2.4S Submersible Pump",
        slug="hs2-4s-submersible-pump",
        category_code="PUMPS",
        manufacturer="Tsurumi",
        model_number="HS2.4S",
        short_description=(
            "Electric submersible drainage pump, 0.4 kW, 50 mm outlet, with an agitator for sandy "
            "water."
        ),
        long_description="Lower it in on a rope, never by the cable. Runs from a standard plug.",
        daily_rate=Decimal("180.00"),
        weekly_rate=Decimal("720.00"),
        deposit_amount=Decimal("700.00"),
        late_fee_per_day=Decimal("80.00"),
        replacement_value=Decimal("7800.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="PU",
        units_per_branch={"CBD": 2, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="PU-GRUNDFOS-KP250",
        name="Unilift KP 250 Sump Pump",
        slug="unilift-kp-250-sump-pump",
        category_code="PUMPS",
        manufacturer="Grundfos",
        model_number="Unilift KP 250",
        short_description=(
            "Stainless steel submersible pump with a float switch. Draining basements, sumps and "
            "rainwater tanks."
        ),
        long_description=(
            "The float switch stops the pump when the water is gone. For clean or slightly dirty "
            "water only."
        ),
        daily_rate=Decimal("110.00"),
        weekly_rate=Decimal("440.00"),
        deposit_amount=Decimal("400.00"),
        late_fee_per_day=Decimal("50.00"),
        replacement_value=Decimal("4800.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="PU",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="PU-ATLASCOPCO-WEDA10",
        name="WEDA 10 Drainage Pump",
        slug="weda-10-drainage-pump",
        category_code="PUMPS",
        manufacturer="Atlas Copco",
        model_number="WEDA 10",
        short_description=(
            "Single phase submersible dewatering pump for construction pits and flooded basements."
        ),
        long_description=(
            "Built for continuous site use. Lower it in on a rope, never by the cable."
        ),
        daily_rate=Decimal("240.00"),
        weekly_rate=Decimal("960.00"),
        deposit_amount=Decimal("1000.00"),
        late_fee_per_day=Decimal("110.00"),
        replacement_value=Decimal("18500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="PU",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 0},
    ),
    ProductModelSeed(
        sku="PU-ROTHENBERGER-RP50S",
        name="RP 50-S Pressure Test Pump",
        slug="rp-50-s-pressure-test-pump",
        category_code="PUMPS",
        manufacturer="Rothenberger",
        model_number="RP 50-S",
        short_description=(
            "Hand pressure test pump with a 12 L tank, to 60 bar. Testing water and heating "
            "pipework for leaks."
        ),
        long_description=(
            "Supplied with a pressure gauge and a hose. Plumbers use it before closing up walls."
        ),
        daily_rate=Decimal("120.00"),
        weekly_rate=Decimal("480.00"),
        deposit_amount=Decimal("450.00"),
        late_fee_per_day=Decimal("50.00"),
        replacement_value=Decimal("3900.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="PU",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 0},
    ),
)
