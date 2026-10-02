"""The tagged units carried over from the prototype.

I keep every tag, model, branch, acquisition date, cost and meter reading as the
prototype has them, with the branch codes moved to BLV and SMW. Four values
could not come across unchanged. The data model has no RESERVED or MAINTENANCE
status, so TSH-DR-0046 is AVAILABLE and TSH-BR-0013 is UNDER_REPAIR. It also
stops at grade C, so TSH-CS-0073 and TSH-BC-0112 are grade C where the prototype
showed D. The prototype held no serial numbers, so the ones here are made up.
The asset table wants a retirement date on a retired unit, so TSH-BC-0112 is
retired on the day its replacement, TSH-BC-0111, was bought.

Units the prototype showed as out on hire are AVAILABLE here, because the seed
creates no open hire for them to belong to.
"""

from datetime import date
from decimal import Decimal

from .types import PinnedAssetSeed

# I pack each unit onto three lines so the whole pinned fleet fits on one screen.
# fmt: off
PINNED_ASSETS: tuple[PinnedAssetSeed, ...] = (
    # Rotary hammers. TSH-DR-0042 is the worked example unit.
    PinnedAssetSeed(
        asset_tag="TSH-DR-0042", sku="DR-BOSCH-GBH226", branch_code="CBD", status="AVAILABLE",
        condition_grade="A", serial_number="BO2406-41873", acquired_on=date(2024, 6, 11),
        acquisition_cost=Decimal("3980.00"), hour_meter_reading=412,
    ),
    PinnedAssetSeed(
        asset_tag="TSH-DR-0043", sku="DR-BOSCH-GBH226", branch_code="CBD", status="AVAILABLE",
        condition_grade="A", serial_number="BO2406-41874", acquired_on=date(2024, 6, 11),
        acquisition_cost=Decimal("3980.00"), hour_meter_reading=388,
    ),
    PinnedAssetSeed(
        asset_tag="TSH-DR-0044", sku="DR-BOSCH-GBH226", branch_code="BLV", status="AVAILABLE",
        condition_grade="B", serial_number="BO2302-17750", acquired_on=date(2023, 2, 20),
        acquisition_cost=Decimal("3650.00"), hour_meter_reading=902,
    ),
    PinnedAssetSeed(
        asset_tag="TSH-DR-0045", sku="DR-BOSCH-GBH226", branch_code="SMW", status="QUARANTINED",
        condition_grade="C", serial_number="BO2302-17752", acquired_on=date(2023, 2, 20),
        acquisition_cost=Decimal("3650.00"), hour_meter_reading=1140,
    ),
    PinnedAssetSeed(
        asset_tag="TSH-DR-0046", sku="DR-BOSCH-GBH226", branch_code="BLV", status="AVAILABLE",
        condition_grade="A", serial_number="BO2509-60218", acquired_on=date(2025, 9, 2),
        acquisition_cost=Decimal("4150.00"), hour_meter_reading=96,
    ),
    # Breakers.
    PinnedAssetSeed(
        asset_tag="TSH-BR-0011", sku="BR-HILTI-TE1000AVR", branch_code="CBD", status="AVAILABLE",
        condition_grade="B", serial_number="HI2211-08834", acquired_on=date(2022, 11, 4),
        acquisition_cost=Decimal("29500.00"), hour_meter_reading=2210,
    ),
    PinnedAssetSeed(
        asset_tag="TSH-BR-0012", sku="BR-HILTI-TE1000AVR", branch_code="BLV", status="AVAILABLE",
        condition_grade="A", serial_number="HI2501-22107", acquired_on=date(2025, 1, 15),
        acquisition_cost=Decimal("31800.00"), hour_meter_reading=340,
    ),
    PinnedAssetSeed(
        asset_tag="TSH-BR-0013", sku="BR-HILTI-TE1000AVR", branch_code="SMW", status="UNDER_REPAIR",
        condition_grade="C", serial_number="HI2108-03391", acquired_on=date(2021, 8, 30),
        acquisition_cost=Decimal("26900.00"), hour_meter_reading=3980,
    ),
    # Plate compactors.
    PinnedAssetSeed(
        asset_tag="TSH-PC-0021", sku="PC-WACKER-CP100", branch_code="CBD", status="AVAILABLE",
        condition_grade="A", serial_number="WN2403-55120", acquired_on=date(2024, 3, 18),
        acquisition_cost=Decimal("17200.00"), hour_meter_reading=610,
    ),
    PinnedAssetSeed(
        asset_tag="TSH-PC-0022", sku="PC-WACKER-CP100", branch_code="CBD", status="AVAILABLE",
        condition_grade="B", serial_number="WN2305-48866", acquired_on=date(2023, 5, 22),
        acquisition_cost=Decimal("16400.00"), hour_meter_reading=1320,
    ),
    PinnedAssetSeed(
        asset_tag="TSH-PC-0023", sku="PC-WACKER-CP100", branch_code="BLV", status="AVAILABLE",
        condition_grade="A", serial_number="WN2502-61492", acquired_on=date(2025, 2, 10),
        acquisition_cost=Decimal("18100.00"), hour_meter_reading=205,
    ),
    PinnedAssetSeed(
        asset_tag="TSH-PC-0024", sku="PC-WACKER-CP100", branch_code="SMW", status="AVAILABLE",
        condition_grade="B", serial_number="WN2305-48871", acquired_on=date(2023, 5, 22),
        acquisition_cost=Decimal("16400.00"), hour_meter_reading=1455,
    ),
    # Rammers.
    PinnedAssetSeed(
        asset_tag="TSH-RM-0031", sku="RM-WACKER-BS604", branch_code="BLV", status="AVAILABLE",
        condition_grade="A", serial_number="WN2409-57703", acquired_on=date(2024, 9, 5),
        acquisition_cost=Decimal("23100.00"), hour_meter_reading=480,
    ),
    PinnedAssetSeed(
        asset_tag="TSH-RM-0032", sku="RM-WACKER-BS604", branch_code="SMW", status="AVAILABLE",
        condition_grade="B", serial_number="WN2207-39015", acquired_on=date(2022, 7, 19),
        acquisition_cost=Decimal("21800.00"), hour_meter_reading=1890,
    ),
    # Mixers.
    PinnedAssetSeed(
        asset_tag="TSH-MX-0051", sku="MX-BAUMAX-140L", branch_code="CBD", status="AVAILABLE",
        condition_grade="B", serial_number="BX2301-10447", acquired_on=date(2023, 1, 12),
        acquisition_cost=Decimal("6300.00"), hour_meter_reading=None,
    ),
    PinnedAssetSeed(
        asset_tag="TSH-MX-0052", sku="MX-BAUMAX-140L", branch_code="BLV", status="AVAILABLE",
        condition_grade="A", serial_number="BX2504-13920", acquired_on=date(2025, 4, 8),
        acquisition_cost=Decimal("7100.00"), hour_meter_reading=None,
    ),
    PinnedAssetSeed(
        asset_tag="TSH-MX-0053", sku="MX-BAUMAX-140L", branch_code="SMW", status="AVAILABLE",
        condition_grade="C", serial_number="BX2110-07618", acquired_on=date(2021, 10, 30),
        acquisition_cost=Decimal("5900.00"), hour_meter_reading=None,
    ),
    # Pokers.
    PinnedAssetSeed(
        asset_tag="TSH-PV-0061", sku="PV-ENARCO-45MM", branch_code="CBD", status="AVAILABLE",
        condition_grade="A", serial_number="EN2411-30256", acquired_on=date(2024, 11, 21),
        acquisition_cost=Decimal("8900.00"), hour_meter_reading=None,
    ),
    PinnedAssetSeed(
        asset_tag="TSH-PV-0062", sku="PV-ENARCO-45MM", branch_code="BLV", status="AVAILABLE",
        condition_grade="B", serial_number="EN2303-27781", acquired_on=date(2023, 3, 14),
        acquisition_cost=Decimal("8400.00"), hour_meter_reading=None,
    ),
    # Cut-off saws.
    PinnedAssetSeed(
        asset_tag="TSH-CS-0071", sku="CS-STIHL-TS420", branch_code="CBD", status="AVAILABLE",
        condition_grade="A", serial_number="ST2506-91344", acquired_on=date(2025, 6, 2),
        acquisition_cost=Decimal("16200.00"), hour_meter_reading=180,
    ),
    PinnedAssetSeed(
        asset_tag="TSH-CS-0072", sku="CS-STIHL-TS420", branch_code="BLV", status="AVAILABLE",
        condition_grade="B", serial_number="ST2308-84019", acquired_on=date(2023, 8, 11),
        acquisition_cost=Decimal("15400.00"), hour_meter_reading=940,
    ),
    PinnedAssetSeed(
        asset_tag="TSH-CS-0073", sku="CS-STIHL-TS420", branch_code="SMW", status="QUARANTINED",
        condition_grade="C", serial_number="ST2204-76650", acquired_on=date(2022, 4, 25),
        acquisition_cost=Decimal("14900.00"), hour_meter_reading=2380,
    ),
    # Grinders.
    PinnedAssetSeed(
        asset_tag="TSH-AG-0081", sku="AG-BOSCH-GWS22230", branch_code="CBD", status="AVAILABLE",
        condition_grade="A", serial_number="BO2503-58831", acquired_on=date(2025, 3, 30),
        acquisition_cost=Decimal("3500.00"), hour_meter_reading=None,
    ),
    PinnedAssetSeed(
        asset_tag="TSH-AG-0082", sku="AG-BOSCH-GWS22230", branch_code="CBD", status="AVAILABLE",
        condition_grade="B", serial_number="BO2309-33907", acquired_on=date(2023, 9, 17),
        acquisition_cost=Decimal("3300.00"), hour_meter_reading=None,
    ),
    PinnedAssetSeed(
        asset_tag="TSH-AG-0083", sku="AG-BOSCH-GWS22230", branch_code="BLV", status="AVAILABLE",
        condition_grade="B", serial_number="BO2309-33911", acquired_on=date(2023, 9, 17),
        acquisition_cost=Decimal("3300.00"), hour_meter_reading=None,
    ),
    # Tower scaffolds. These carry no manufacturer serial.
    PinnedAssetSeed(
        asset_tag="TSH-SC-0091", sku="SC-INSTANT-TOWER6M", branch_code="CBD", status="AVAILABLE",
        condition_grade="A", serial_number=None, acquired_on=date(2024, 5, 14),
        acquisition_cost=Decimal("26800.00"), hour_meter_reading=None,
    ),
    PinnedAssetSeed(
        asset_tag="TSH-SC-0092", sku="SC-INSTANT-TOWER6M", branch_code="SMW", status="AVAILABLE",
        condition_grade="B", serial_number=None, acquired_on=date(2022, 12, 8),
        acquisition_cost=Decimal("25200.00"), hour_meter_reading=None,
    ),
    # Engine cranes.
    PinnedAssetSeed(
        asset_tag="TSH-EC-0101", sku="EC-SEALEY-CRANE1T", branch_code="BLV", status="AVAILABLE",
        condition_grade="B", serial_number="SE2306-64402", acquired_on=date(2023, 6, 27),
        acquisition_cost=Decimal("10600.00"), hour_meter_reading=None,
    ),
    # Brushcutters.
    PinnedAssetSeed(
        asset_tag="TSH-BC-0111", sku="BC-STIHL-FS240", branch_code="SMW", status="AVAILABLE",
        condition_grade="A", serial_number="ST2508-92710", acquired_on=date(2025, 8, 19),
        acquisition_cost=Decimal("8700.00"), hour_meter_reading=None,
    ),
    PinnedAssetSeed(
        asset_tag="TSH-BC-0112", sku="BC-STIHL-FS240", branch_code="SMW", status="RETIRED",
        condition_grade="C", serial_number="ST1903-51288", acquired_on=date(2019, 3, 5),
        acquisition_cost=Decimal("6900.00"), hour_meter_reading=None,
        retired_on=date(2025, 8, 19),
    ),
    # Generators.
    PinnedAssetSeed(
        asset_tag="TSH-GN-0131", sku="GN-HONDA-65KVA", branch_code="CBD", status="AVAILABLE",
        condition_grade="A", serial_number="HO2505-70015", acquired_on=date(2025, 5, 6),
        acquisition_cost=Decimal("32400.00"), hour_meter_reading=290,
    ),
    PinnedAssetSeed(
        asset_tag="TSH-GN-0132", sku="GN-HONDA-65KVA", branch_code="BLV", status="AVAILABLE",
        condition_grade="A", serial_number="HO2505-70016", acquired_on=date(2025, 5, 6),
        acquisition_cost=Decimal("32400.00"), hour_meter_reading=260,
    ),
    PinnedAssetSeed(
        asset_tag="TSH-GN-0133", sku="GN-HONDA-65KVA", branch_code="SMW", status="AVAILABLE",
        condition_grade="B", serial_number="HO2311-66482", acquired_on=date(2023, 11, 11),
        acquisition_cost=Decimal("30100.00"), hour_meter_reading=1120,
    ),
    # Tower lights.
    PinnedAssetSeed(
        asset_tag="TSH-TL-0141", sku="TL-GENERAC-LEDTOWER", branch_code="CBD", status="AVAILABLE",
        condition_grade="A", serial_number="GE2408-11739", acquired_on=date(2024, 8, 23),
        acquisition_cost=Decimal("18900.00"), hour_meter_reading=None,
    ),
)
# fmt: on
