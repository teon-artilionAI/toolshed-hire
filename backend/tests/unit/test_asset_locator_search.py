"""The asset locator's search, with no database anywhere (FR-15, US-10).

A search is bounded the way the customer search is, so these pin the bounds of
`AssetSearch` and that `LocateAssets` hands the search to its query object and
answers with what came back. The statement itself is proved on the in memory
database in tests/api/test_asset_locator.py and on PostgreSQL, with the index
it stands on, in tests/integration/test_counter_read_indexes.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Final
from uuid import uuid4

import pytest

from app.application.catalogue.locator import (
    MAXIMUM_LOCATOR_SEARCH_LENGTH,
    MINIMUM_LOCATOR_SEARCH_LENGTH,
    AssetLocation,
    AssetLocationPage,
    AssetSearch,
    LocateAssets,
)
from app.domain.enums import AssetStatus, ConditionGrade, UserRole
from app.domain.identity import Actor

ON_HIRE_UNIT: Final[AssetLocation] = AssetLocation(
    asset_tag="TSH-DR-0042",
    model_name="Bosch GBH 2-26",
    model_slug="bosch-gbh-2-26",
    category_name="Drilling and Demolition",
    branch_code="BLV",
    branch_name="Bellville",
    status=AssetStatus.ON_HIRE,
    condition_grade=ConditionGrade.A,
    due_back_on=date(2026, 3, 5),
    rental_reference="TSH-H-26-000099",
)


@dataclass
class FakeLocator:
    """A query object that answers every search with one unit and notes what it was asked."""

    asked: list[AssetSearch] = field(default_factory=list)

    def search(self, search: AssetSearch) -> AssetLocationPage:
        """Note the search and answer with the one unit on hire."""
        self.asked.append(search)
        return AssetLocationPage(
            items=(ON_HIRE_UNIT,), page=search.page, page_size=search.page_size, total=1
        )


class TestTheBoundsOfASearch:
    """Two to eighty characters, a page from one, and one to fifty units a page."""

    @pytest.mark.parametrize(
        "text", ["x", "x" * (MAXIMUM_LOCATOR_SEARCH_LENGTH + 1)], ids=["too short", "too long"]
    )
    def test_a_text_outside_the_bounds_is_refused(self, text: str) -> None:
        with pytest.raises(ValueError, match="characters"):
            AssetSearch(text=text)

    @pytest.mark.parametrize("page", [0, 10_001])
    def test_a_page_outside_the_bounds_is_refused(self, page: int) -> None:
        with pytest.raises(ValueError, match="page"):
            AssetSearch(text="DR", page=page)

    @pytest.mark.parametrize("page_size", [0, 51])
    def test_a_page_size_outside_the_bounds_is_refused(self, page_size: int) -> None:
        with pytest.raises(ValueError, match="page size"):
            AssetSearch(text="DR", page_size=page_size)

    def test_the_offset_skips_the_pages_before_the_one_wanted(self) -> None:
        assert AssetSearch(text="DR", page=3, page_size=20).offset == 40
        assert len("DR") == MINIMUM_LOCATOR_SEARCH_LENGTH


class TestLocatingUnits:
    """The search is handed to the query object, and its answer is handed back."""

    def test_the_search_reaches_the_query_object_and_its_answer_comes_back(self) -> None:
        locator = FakeLocator()
        search = AssetSearch(text="0042", page=2, page_size=5)
        actor = Actor(user_id=uuid4(), role=UserRole.COUNTER_STAFF, branch_id=uuid4())

        found = LocateAssets(locator).search(actor, search)

        assert locator.asked == [search]
        assert found.items == (ON_HIRE_UNIT,)
        assert (found.page, found.page_size, found.total) == (2, 5, 1)
