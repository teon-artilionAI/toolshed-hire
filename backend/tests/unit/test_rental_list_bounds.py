"""The second line of the rental lists and of a change to a rental, with no database.

The HTTP boundary keeps a page from one to fifty rentals and a page number in
range, and answers 422 otherwise. `RentalSearch` refuses the same out of range
values again, so a caller inside the system cannot hand the repository a
negative offset or an unbounded page. And a rental whose reservation cannot be
read is a fault in the data, which is reported as one and never passed over.
"""

from __future__ import annotations

from datetime import date
from typing import Final
from uuid import UUID

import pytest

from app.application.hire.list_models import RentalSearch
from app.application.hire.rental_access import reservation_of
from app.application.unit_of_work import UnitOfWork
from app.domain.enums import UserRole
from app.domain.identity import Actor
from tests.support.memory import InMemoryUnitOfWork, MemoryStore
from tests.support.return_domain import a_hire

TODAY: Final[date] = date(2026, 3, 2)
ADMINISTRATOR: Final[Actor] = Actor(user_id=UUID(int=1), role=UserRole.ADMIN)


@pytest.mark.parametrize(("page", "page_size"), [(0, 20), (10_001, 20), (1, 0), (1, 51)])
def test_a_page_out_of_range_is_refused(page: int, page_size: int) -> None:
    with pytest.raises(ValueError, match="Attempted to list rentals"):
        RentalSearch(today=TODAY, page=page, page_size=page_size)


def test_the_offset_counts_the_rentals_before_the_page() -> None:
    assert RentalSearch(today=TODAY, page=3, page_size=20).offset == 40


def test_a_rental_whose_reservation_cannot_be_read_is_a_fault_in_the_data() -> None:
    unit_of_work: UnitOfWork = InMemoryUnitOfWork(MemoryStore())
    with unit_of_work as uow, pytest.raises(LookupError, match="could not be read"):
        reservation_of(uow, ADMINISTRATOR, a_hire().rental)
