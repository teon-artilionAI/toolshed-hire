"""The asset locator query object, which finds a unit at any branch by its tag or its model.

It implements the `AssetLocatorQuery` port and returns the frozen read models
of `app.application.catalogue.locator`. It runs on the session of the request
and takes no lock. Two statements answer a search whatever it finds, the count
and the page.

HOW A SEARCH STANDS ON THE INDEXES

The text is matched two ways, and the two are joined with UNION so that each
way can use its own index and the count and the page run the same condition.

1. Part of the asset tag, case blind, anywhere in it. `ix_asset_tag_trgm` of
   revision 0004 is a trigram index on the tag, which serves `ILIKE '%text%'`.
   The unique btree on the tag only finds a tag typed in full.
2. Part of the model name. The catalogue holds a few hundred models, so the
   name is matched by reading `product_model`, the way the catalogue search
   does, and the units of the models found are reached through
   `ix_asset_product_model` of revision 0004.

The page is joined to its model, category and branch by their keys. A unit on
hire is joined to the rental it is out on through `ix_rental_item_asset`, and
only a unit whose status is ON_HIRE carries the day it is due back and the
rental reference.

The text travels as a bound value with the two LIKE wildcards and the
backslash taken out, so a search for `%` finds nothing.

What degrades first as the fleet grows is a two character search. A trigram
index cannot narrow a pattern shorter than three characters, so `DR` reads the
whole index and sorts every match to find the page. The page is found with
OFFSET, so a deep page reads every match before it, which is why a page holds
at most fifty units.
"""

from __future__ import annotations

import logging
from typing import Final

from sqlalchemy import Executable, RowMapping, and_, func, union
from sqlalchemy import select as select_columns
from sqlmodel import Session, col

from app.application.catalogue.locator import AssetLocation, AssetLocationPage, AssetSearch
from app.domain.enums import AssetStatus
from app.infrastructure.customer_search import ANY_TEXT, LIKE_SPECIALS
from app.infrastructure.models import (
    Asset,
    Branch,
    Category,
    ProductModel,
    Rental,
    RentalItem,
)
from app.infrastructure.query_log import logged_query

logger = logging.getLogger(__name__)

MATCHING_SUBQUERY_NAME: Final[str] = "matching"
MATCHED_ASSET_ID: Final[str] = "asset_id"


class SqlAssetLocator:
    """Finds units at every branch through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the query object to the session of the request."""
        self._session = session

    def search(self, search: AssetSearch) -> AssetLocationPage:
        """Return one page of the units whose tag or model name holds the text, in tag order."""
        text = search.text.translate(LIKE_SPECIALS).strip()
        filters: dict[str, object] = {
            "text_length": len(search.text),
            "page": search.page,
            "page_size": search.page_size,
        }
        if not text:
            logger.info("asset.locator_search_skipped", extra=filters)
            return AssetLocationPage(
                items=(), page=search.page, page_size=search.page_size, total=0
            )
        pattern = f"{ANY_TEXT}{text}{ANY_TEXT}"
        matching = union(
            select_columns(col(Asset.id).label(MATCHED_ASSET_ID)).where(
                col(Asset.asset_tag).ilike(pattern)
            ),
            select_columns(col(Asset.id).label(MATCHED_ASSET_ID))
            .join(ProductModel, col(ProductModel.id) == col(Asset.product_model_id))
            .where(col(ProductModel.name).ilike(pattern)),
        ).subquery(MATCHING_SUBQUERY_NAME)
        current_rental = (
            select_columns(col(RentalItem.rental_id))
            .where(col(RentalItem.asset_id) == col(Asset.id), col(RentalItem.returned_at).is_(None))
            .order_by(col(RentalItem.checked_out_at).desc())
            .limit(1)
            .correlate(Asset)
            .scalar_subquery()
        )
        page_statement: Executable = (
            select_columns(
                col(Asset.asset_tag).label("asset_tag"),
                col(ProductModel.name).label("model_name"),
                col(ProductModel.slug).label("model_slug"),
                col(Category.name).label("category_name"),
                col(Branch.code).label("branch_code"),
                col(Branch.name).label("branch_name"),
                col(Asset.status).label("status"),
                col(Asset.condition_grade).label("condition_grade"),
                col(Rental.due_back_on).label("due_back_on"),
                col(Rental.reference).label("rental_reference"),
            )
            .select_from(Asset)
            .join(matching, matching.c[MATCHED_ASSET_ID] == col(Asset.id))
            .join(ProductModel, col(ProductModel.id) == col(Asset.product_model_id))
            .join(Category, col(Category.id) == col(ProductModel.category_id))
            .join(Branch, col(Branch.id) == col(Asset.branch_id))
            .outerjoin(
                Rental,
                and_(col(Asset.status) == AssetStatus.ON_HIRE, col(Rental.id) == current_rental),
            )
            .order_by(col(Asset.asset_tag))
            .limit(search.page_size)
            .offset(search.offset)
        )
        count_statement = select_columns(func.count()).select_from(matching)
        with logged_query(logger, "asset.locator_search", filters) as outcome:
            total = int(self._session.execute(count_statement).scalar_one())
            rows = self._session.execute(page_statement).mappings().all()
            outcome.row_count = len(rows)
        return AssetLocationPage(
            items=tuple(_location_of(row) for row in rows),
            page=search.page,
            page_size=search.page_size,
            total=total,
        )


def _location_of(row: RowMapping) -> AssetLocation:
    """Return where one unit is, from a row of the page."""
    return AssetLocation(
        asset_tag=row["asset_tag"],
        model_name=row["model_name"],
        model_slug=row["model_slug"],
        category_name=row["category_name"],
        branch_code=row["branch_code"],
        branch_name=row["branch_name"],
        status=row["status"],
        condition_grade=row["condition_grade"],
        due_back_on=row["due_back_on"],
        rental_reference=row["rental_reference"],
    )
