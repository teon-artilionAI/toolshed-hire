"""Catalogue and fleet seed data for Toolshed Hire.

I keep this package as data only. It opens no files and no database connection,
so a loader can import it, read the four tuples below and decide for itself how
to write them. Product models are grouped into one module per catalogue area and
joined here in catalogue order.
"""

from .branches import BRANCHES
from .categories import CATEGORIES
from .models_access_lifting import ACCESS_LIFTING_MODELS
from .models_breaking_drilling import BREAKING_DRILLING_MODELS
from .models_cleaning import CLEANING_MODELS
from .models_compaction import COMPACTION_MODELS
from .models_concrete_mixing import CONCRETE_MIXING_MODELS
from .models_cutting_grinding import CUTTING_GRINDING_MODELS
from .models_floor_prep import FLOOR_PREP_MODELS
from .models_gardening import GARDENING_MODELS
from .models_power_lighting import POWER_LIGHTING_MODELS
from .models_pumps import PUMPS_MODELS
from .models_site_equipment import SITE_EQUIPMENT_MODELS
from .models_welding import WELDING_MODELS
from .pinned_assets import PINNED_ASSETS
from .types import BranchSeed, CategorySeed, PinnedAssetSeed, ProductModelSeed

PRODUCT_MODELS: tuple[ProductModelSeed, ...] = (
    *BREAKING_DRILLING_MODELS,
    *COMPACTION_MODELS,
    *CONCRETE_MIXING_MODELS,
    *CUTTING_GRINDING_MODELS,
    *FLOOR_PREP_MODELS,
    *ACCESS_LIFTING_MODELS,
    *GARDENING_MODELS,
    *POWER_LIGHTING_MODELS,
    *PUMPS_MODELS,
    *WELDING_MODELS,
    *CLEANING_MODELS,
    *SITE_EQUIPMENT_MODELS,
)

__all__ = [
    "BRANCHES",
    "CATEGORIES",
    "PINNED_ASSETS",
    "PRODUCT_MODELS",
    "BranchSeed",
    "CategorySeed",
    "PinnedAssetSeed",
    "ProductModelSeed",
]
