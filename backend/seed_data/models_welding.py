"""Product models for the Welding category.

This category is new, so nothing here comes from the prototype. Every model
takes the WD tag prefix.
"""

from decimal import Decimal

from .types import ProductModelSeed

WELDING_MODELS: tuple[ProductModelSeed, ...] = (
    ProductModelSeed(
        sku="WD-ESAB-BUDDYARC200",
        name="Buddy Arc 200 Inverter Welder",
        slug="buddy-arc-200-inverter-welder",
        category_code="WELDING",
        manufacturer="ESAB",
        model_number="Buddy Arc 200",
        short_description=(
            "Stick welding inverter, 200 A, single phase, about 7 kg. General steelwork, gates and "
            "repairs."
        ),
        long_description=(
            "Supplied with an electrode holder and an earth clamp. Electrodes and helmets are sold "
            "at the counter."
        ),
        daily_rate=Decimal("170.00"),
        weekly_rate=Decimal("680.00"),
        deposit_amount=Decimal("700.00"),
        late_fee_per_day=Decimal("80.00"),
        replacement_value=Decimal("6900.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="WD",
        units_per_branch={"CBD": 2, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="WD-FRONIUS-TP180",
        name="TransPocket 180 Stick Welder",
        slug="transpocket-180-stick-welder",
        category_code="WELDING",
        manufacturer="Fronius",
        model_number="TransPocket 180",
        short_description=(
            "Stick welding inverter, 180 A, that also runs from a generator. Site welding and "
            "maintenance work."
        ),
        long_description="Supplied with welding leads in a carry case.",
        daily_rate=Decimal("260.00"),
        weekly_rate=Decimal("1040.00"),
        deposit_amount=Decimal("1100.00"),
        late_fee_per_day=Decimal("120.00"),
        replacement_value=Decimal("19500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="WD",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="WD-ESAB-REBEL215IC",
        name="Rebel EMP 215ic Multi-Process Welder",
        slug="rebel-emp-215ic-multi-process-welder",
        category_code="WELDING",
        manufacturer="ESAB",
        model_number="Rebel EMP 215ic",
        short_description=(
            "Single phase multi-process welder for MIG, stick and lift TIG, 200 A class. "
            "Fabrication and vehicle body work."
        ),
        long_description=(
            "Supplied with a MIG torch and an earth lead. Wire and shielding gas are not included."
        ),
        daily_rate=Decimal("420.00"),
        weekly_rate=Decimal("1680.00"),
        deposit_amount=Decimal("2000.00"),
        late_fee_per_day=Decimal("190.00"),
        replacement_value=Decimal("44000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="WD",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="WD-ESAB-ROGUE200IP",
        name="Rogue ET 200iP TIG Welder",
        slug="rogue-et-200ip-tig-welder",
        category_code="WELDING",
        manufacturer="ESAB",
        model_number="Rogue ET 200iP",
        short_description=(
            "DC TIG and stick inverter, 200 A, with high frequency start and pulse. Stainless and "
            "thin steel."
        ),
        long_description="Supplied with a TIG torch and an earth lead. Argon is not included.",
        daily_rate=Decimal("280.00"),
        weekly_rate=Decimal("1120.00"),
        deposit_amount=Decimal("1200.00"),
        late_fee_per_day=Decimal("130.00"),
        replacement_value=Decimal("16500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="WD",
        units_per_branch={"CBD": 1, "BLV": 0, "SMW": 0},
    ),
    ProductModelSeed(
        sku="WD-HYPERTHERM-PMX45XP",
        name="Powermax45 XP Plasma Cutter",
        slug="powermax45-xp-plasma-cutter",
        category_code="WELDING",
        manufacturer="Hypertherm",
        model_number="Powermax45 XP",
        short_description=(
            "Air plasma cutter, 45 A, cuts 16 mm mild steel cleanly. Needs a compressed air supply."
        ),
        long_description=(
            "Supplied with a hand torch and a work clamp. Consumables are sold at the counter."
        ),
        daily_rate=Decimal("520.00"),
        weekly_rate=Decimal("2080.00"),
        deposit_amount=Decimal("2500.00"),
        late_fee_per_day=Decimal("230.00"),
        replacement_value=Decimal("62000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="WD",
        units_per_branch={"CBD": 1, "BLV": 0, "SMW": 0},
    ),
    ProductModelSeed(
        sku="WD-LINCOLN-RANGER305D",
        name="Ranger 305D Welder Generator",
        slug="ranger-305d-welder-generator",
        category_code="WELDING",
        manufacturer="Lincoln Electric",
        model_number="Ranger 305D",
        short_description=(
            "Diesel engine driven welder, 300 A DC, with auxiliary power for grinders and lights. "
            "Site and pipeline welding."
        ),
        long_description=(
            "Collected on a trailer or loaded by forklift. Goes out with a full tank of diesel."
        ),
        daily_rate=Decimal("820.00"),
        weekly_rate=Decimal("3280.00"),
        deposit_amount=Decimal("4500.00"),
        late_fee_per_day=Decimal("370.00"),
        replacement_value=Decimal("285000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="WD",
        units_per_branch={"CBD": 1, "BLV": 0, "SMW": 0},
    ),
    ProductModelSeed(
        sku="WD-AFROX-PORTAPAK",
        name="PortaPak Oxy-Acetylene Set",
        slug="portapak-oxy-acetylene-set",
        category_code="WELDING",
        manufacturer="Afrox",
        model_number="PortaPak",
        short_description=(
            "Portable oxy-acetylene cutting and welding set with regulators, hoses and torch on a "
            "carry frame."
        ),
        long_description=(
            "Flashback arrestors are fitted and must stay on. Goes out with full cylinders."
        ),
        daily_rate=Decimal("240.00"),
        weekly_rate=Decimal("960.00"),
        deposit_amount=Decimal("1500.00"),
        late_fee_per_day=Decimal("110.00"),
        replacement_value=Decimal("9800.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="WD",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="WD-LEISTER-TRIACST",
        name="Triac ST Hot Air Welder",
        slug="triac-st-hot-air-welder",
        category_code="WELDING",
        manufacturer="Leister",
        model_number="Triac ST",
        short_description=(
            "Hot air hand tool, 1600 W, for welding vinyl flooring, tarpaulins and plastic sheet."
        ),
        long_description="Supplied with a standard nozzle and a pressure roller.",
        daily_rate=Decimal("190.00"),
        weekly_rate=Decimal("760.00"),
        deposit_amount=Decimal("800.00"),
        late_fee_per_day=Decimal("90.00"),
        replacement_value=Decimal("9800.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="WD",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 0},
    ),
)
