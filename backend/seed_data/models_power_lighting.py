"""Product models for the Power and Lighting category.

I list the two models carried over from the prototype first. New models take the
GN tag prefix. The Generac tower light keeps TL because its unit is already
tagged that way. The prototype gave no model number for those two, so I describe
the size instead of guessing one.
"""

from decimal import Decimal

from .types import ProductModelSeed

POWER_LIGHTING_MODELS: tuple[ProductModelSeed, ...] = (
    ProductModelSeed(
        sku="GN-HONDA-65KVA",
        name="6.5 kVA Petrol Generator",
        slug="6-5-kva-petrol-generator",
        category_code="POWER-LIGHT",
        manufacturer="Honda",
        model_number="6.5 kVA electric start",
        short_description=(
            "Single-phase petrol generator, 6.5 kVA, electric start. Load shedding cover and site "
            "power."
        ),
        long_description="Run it outdoors only. Goes out with a full tank of unleaded petrol.",
        daily_rate=Decimal("520.00"),
        weekly_rate=Decimal("2080.00"),
        deposit_amount=Decimal("2400.00"),
        late_fee_per_day=Decimal("330.00"),
        replacement_value=Decimal("34000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="GN",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="TL-GENERAC-LEDTOWER",
        name="LED Site Tower Light",
        slug="led-site-tower-light",
        category_code="POWER-LIGHT",
        manufacturer="Generac",
        model_number="4 LED heads, 4.5 m mast",
        short_description=(
            "Four-head LED tower on a wheeled mast to 4.5 m. Night works and secure yards."
        ),
        long_description="Plugs into mains or a small generator. Lower the mast before moving it.",
        daily_rate=Decimal("310.00"),
        weekly_rate=Decimal("1240.00"),
        deposit_amount=Decimal("1400.00"),
        late_fee_per_day=Decimal("200.00"),
        replacement_value=Decimal("19500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="TL",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="GN-HONDA-EU22I",
        name="EU22i Inverter Generator",
        slug="eu22i-inverter-generator",
        category_code="POWER-LIGHT",
        manufacturer="Honda",
        model_number="EU22i",
        short_description=(
            "Portable petrol inverter generator, 2.2 kVA maximum, about 21 kg. Quiet clean power "
            "for electronics, events and small tools."
        ),
        long_description=(
            "Runs a fridge, lights and a router through load shedding. Run it outdoors only."
        ),
        daily_rate=Decimal("320.00"),
        weekly_rate=Decimal("1280.00"),
        deposit_amount=Decimal("1500.00"),
        late_fee_per_day=Decimal("140.00"),
        replacement_value=Decimal("29500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="GN",
        units_per_branch={"CBD": 2, "BLV": 2, "SMW": 1},
    ),
    ProductModelSeed(
        sku="GN-HONDA-EU70IS",
        name="EU70is Inverter Generator",
        slug="eu70is-inverter-generator",
        category_code="POWER-LIGHT",
        manufacturer="Honda",
        model_number="EU70is",
        short_description=(
            "Petrol inverter generator, 7 kVA maximum, electric start with fuel injection. Home "
            "backup and sensitive site loads."
        ),
        long_description="Quiet enough for residential areas. On wheels with folding handles.",
        daily_rate=Decimal("680.00"),
        weekly_rate=Decimal("2720.00"),
        deposit_amount=Decimal("3200.00"),
        late_fee_per_day=Decimal("310.00"),
        replacement_value=Decimal("112000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="GN",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 0},
    ),
    ProductModelSeed(
        sku="GN-RYOBI-RG6900K",
        name="RG-6900K Petrol Generator",
        slug="rg-6900k-petrol-generator",
        category_code="POWER-LIGHT",
        manufacturer="Ryobi",
        model_number="RG-6900K",
        short_description=(
            "Open frame petrol generator, 6.5 kVA maximum and 5.5 kVA continuous, key start, on "
            "wheels."
        ),
        long_description="A budget set for power tools and lighting on site. Run it outdoors only.",
        daily_rate=Decimal("340.00"),
        weekly_rate=Decimal("1360.00"),
        deposit_amount=Decimal("1500.00"),
        late_fee_per_day=Decimal("150.00"),
        replacement_value=Decimal("12500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="GN",
        units_per_branch={"CBD": 2, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="GN-KIPOR-KDE6700TA",
        name="KDE6700TA Silent Diesel Generator",
        slug="kde6700ta-silent-diesel-generator",
        category_code="POWER-LIGHT",
        manufacturer="Kipor",
        model_number="KDE6700TA",
        short_description=(
            "Silenced single phase diesel generator, about 4.5 kVA continuous, electric start, on "
            "wheels."
        ),
        long_description=(
            "Lower running cost than petrol for long shifts. Goes out with a full tank of diesel."
        ),
        daily_rate=Decimal("480.00"),
        weekly_rate=Decimal("1920.00"),
        deposit_amount=Decimal("2200.00"),
        late_fee_per_day=Decimal("220.00"),
        replacement_value=Decimal("36000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="GN",
        units_per_branch={"CBD": 1, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="GN-ATLASCOPCO-QAS20",
        name="QAS 20 Towable Diesel Generator",
        slug="qas-20-towable-diesel-generator",
        category_code="POWER-LIGHT",
        manufacturer="Atlas Copco",
        model_number="QAS 20",
        short_description=(
            "Three phase 20 kVA silenced diesel generator on a road trailer. Site establishment, "
            "events and standby power."
        ),
        long_description="Needs a tow bar and a qualified electrician to connect it.",
        daily_rate=Decimal("1450.00"),
        weekly_rate=Decimal("5800.00"),
        deposit_amount=Decimal("8000.00"),
        late_fee_per_day=Decimal("650.00"),
        replacement_value=Decimal("320000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="GN",
        units_per_branch={"CBD": 1, "BLV": 0, "SMW": 0},
    ),
    ProductModelSeed(
        sku="GN-ECOFLOW-DELTA2",
        name="DELTA 2 Portable Power Station",
        slug="delta-2-portable-power-station",
        category_code="POWER-LIGHT",
        manufacturer="EcoFlow",
        model_number="DELTA 2",
        short_description=(
            "Lithium battery power station, about 1 kWh, 1800 W output. Silent indoor backup for "
            "routers, laptops and lights."
        ),
        long_description=(
            "No fuel and no fumes. Goes out fully charged with its mains charging cable."
        ),
        daily_rate=Decimal("280.00"),
        weekly_rate=Decimal("1120.00"),
        deposit_amount=Decimal("1500.00"),
        late_fee_per_day=Decimal("130.00"),
        replacement_value=Decimal("19500.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="GN",
        units_per_branch={"CBD": 2, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="GN-DEWALT-DCL079",
        name="DCL079 18 V Tripod Light",
        slug="dcl079-18-v-tripod-light",
        category_code="POWER-LIGHT",
        manufacturer="DeWalt",
        model_number="DCL079",
        short_description=(
            "Cordless LED tripod light, 3000 lumens, extends to about 2 m. Supplied with a battery "
            "and charger."
        ),
        long_description=(
            "Folds to carry size and needs no cable run. Suits ceilings, roofs and night call outs."
        ),
        daily_rate=Decimal("140.00"),
        weekly_rate=Decimal("560.00"),
        deposit_amount=Decimal("600.00"),
        late_fee_per_day=Decimal("60.00"),
        replacement_value=Decimal("7400.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="GN",
        units_per_branch={"CBD": 2, "BLV": 1, "SMW": 1},
    ),
    ProductModelSeed(
        sku="GN-ATLASCOPCO-HILIGHTV5",
        name="HiLight V5+ Light Tower",
        slug="hilight-v5-light-tower",
        category_code="POWER-LIGHT",
        manufacturer="Atlas Copco",
        model_number="HiLight V5+",
        short_description=(
            "Towable diesel LED light tower with four heads on a mast of about 7 m. Lights a large "
            "site or event area."
        ),
        long_description="Needs a tow bar. Goes out with a full tank of diesel.",
        daily_rate=Decimal("880.00"),
        weekly_rate=Decimal("3520.00"),
        deposit_amount=Decimal("4500.00"),
        late_fee_per_day=Decimal("400.00"),
        replacement_value=Decimal("195000.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="GN",
        units_per_branch={"CBD": 1, "BLV": 0, "SMW": 0},
    ),
    ProductModelSeed(
        sku="GN-ELLIES-REEL30",
        name="Heavy Duty Extension Reel 30 m",
        slug="heavy-duty-extension-reel-30-m",
        category_code="POWER-LIGHT",
        manufacturer="Ellies",
        model_number="30 m, 16 A",
        short_description=(
            "Extension reel, 30 m, with a 16 A plug and thermal cut-out. Feeds tools from a "
            "generator or a distant plug point."
        ),
        long_description=(
            "Unwind the full length before running heavy loads so the cable does not overheat."
        ),
        daily_rate=Decimal("45.00"),
        weekly_rate=Decimal("180.00"),
        deposit_amount=Decimal("150.00"),
        late_fee_per_day=Decimal("40.00"),
        replacement_value=Decimal("950.00"),
        min_hire_days=1,
        max_hire_days=28,
        tag_prefix="GN",
        units_per_branch={"CBD": 4, "BLV": 3, "SMW": 3},
    ),
)
