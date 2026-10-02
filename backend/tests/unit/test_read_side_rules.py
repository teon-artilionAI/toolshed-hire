"""The rules of the read side, with no database and no HTTP.

Browsing the catalogue and searching availability depend on ports, so three
small fakes are all it takes to run them here. What is proved is what the two
services decide for themselves. Which question may be asked, which parameter a
refusal names, and that a refused question never reaches the query object.

The SQL behind the ports is proved against PostgreSQL in tests/integration,
and the HTTP shapes in tests/api.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.application.availability.read_models import (
    AvailabilityPage,
    AvailabilitySearch,
    BranchAvailability,
)
from app.application.availability.search import SearchAvailability
from app.application.catalogue.browse import BrowseCatalogue
from app.application.catalogue.read_models import (
    CategoryEntry,
    ModelDetail,
    ModelPage,
    ModelSearch,
    ModelSort,
)
from app.application.identity.read_models import BranchListing
from app.application.refusal import REFUSED_PARAMETER, refused, refused_parameter_of
from app.domain.errors import NotFound, ValidationFailure
from app.domain.period import BookingPeriod
from tests.support.clock import FixedClock
from tests.support.factories import CLOSES_AT, OPENS_AT

RAMMER = ModelDetail(
    sku="TSH-PM-0001",
    slug="trench-rammer",
    name="Trench Rammer",
    manufacturer="Wacker Neuson",
    model_number="BS60-2",
    category_code="COMPACTION",
    category_name="Compaction",
    short_description="A two stroke trench rammer.",
    daily_rate=Decimal("380.00"),
    weekly_rate=Decimal("1520.00"),
    deposit_amount=Decimal("1500.00"),
    min_hire_days=2,
    max_hire_days=5,
    image_path=None,
    long_description=None,
    late_fee_per_day=Decimal("250.00"),
)
BELLVILLE = BranchListing(
    code="BLV",
    name="Bellville",
    suburb="Stikland",
    city="Cape Town",
    phone="021 555 0157",
    opens_at=OPENS_AT,
    closes_at=CLOSES_AT,
)
FREE_AT_BELLVILLE = BranchAvailability(branch_code="BLV", branch_name="Bellville", available=True)
# The fixed clock says today is Monday the second of March 2026.
NINTH = date(2026, 3, 9)
TWELFTH = date(2026, 3, 12)


@dataclass
class FakeCatalogue:
    """A catalogue of one category and one model, which remembers its searches."""

    searches: list[ModelSearch] = field(default_factory=list)

    def list_categories(self) -> list[CategoryEntry]:
        """Return the one category."""
        return [CategoryEntry("COMPACTION", "Compaction", "compaction", "", None, 20, 1)]

    def category_exists(self, slug: str) -> bool:
        """Return True for the one category."""
        return slug == "compaction"

    def search_models(self, search: ModelSearch) -> ModelPage:
        """Remember the search and return the one model."""
        self.searches.append(search)
        return ModelPage(items=(RAMMER,), page=search.page, page_size=search.page_size, total=1)

    def find_model(self, slug: str) -> ModelDetail | None:
        """Return the one model when asked for by its slug."""
        return RAMMER if slug == RAMMER.slug else None


@dataclass
class FakeAvailability:
    """An availability port that says yes and remembers what it was asked."""

    searches: list[AvailabilitySearch] = field(default_factory=list)
    model_questions: list[tuple[str, BookingPeriod, int]] = field(default_factory=list)

    def search(self, search: AvailabilitySearch) -> AvailabilityPage:
        """Remember the search and return an empty page for it."""
        self.searches.append(search)
        return AvailabilityPage(
            period=search.period,
            items=(),
            page=search.models.page,
            page_size=search.models.page_size,
            total=0,
        )

    def for_model(
        self, model_slug: str, period: BookingPeriod, quantity: int
    ) -> list[BranchAvailability]:
        """Remember the question and answer that Bellville is free."""
        self.model_questions.append((model_slug, period, quantity))
        return [FREE_AT_BELLVILLE]


class FakeBranches:
    """A directory holding Bellville and nothing else."""

    def list_active(self) -> list[BranchListing]:
        """Return the one branch."""
        return [BELLVILLE]


@pytest.fixture
def availability() -> FakeAvailability:
    """Return the availability port the service under test asks."""
    return FakeAvailability()


@pytest.fixture
def service(availability: FakeAvailability) -> SearchAvailability:
    """Return the availability search on the fakes and a clock that stands still."""
    return SearchAvailability(availability, FakeCatalogue(), FakeBranches(), FixedClock())


def refusal_of(raised: pytest.ExceptionInfo[ValidationFailure]) -> str | None:
    """Return the parameter a caught refusal names."""
    return refused_parameter_of(raised.value)


class TestSearchingAcrossTheCatalogue:
    """The period, the category and the branch are checked before anything is read."""

    def test_an_accepted_search_reaches_the_port_as_a_validated_period(
        self, service: SearchAvailability, availability: FakeAvailability
    ) -> None:
        models = ModelSearch(category_slug="compaction", sort=ModelSort.DAILY_RATE_ASC)
        page = service.across_catalogue(NINTH, TWELFTH, models, "BLV")

        assert availability.searches == [
            AvailabilitySearch(
                period=BookingPeriod(NINTH, TWELFTH), models=models, branch_code="BLV"
            )
        ]
        assert page.period.days == 3

    @pytest.mark.parametrize(
        ("start", "end", "parameter"),
        [
            (TWELFTH, NINTH, "to"),
            (NINTH, NINTH, "to"),
            (NINTH, date(2026, 4, 7), "to"),
            (date(2026, 3, 1), NINTH, "from"),
            (date(2026, 6, 1), date(2026, 6, 3), "from"),
        ],
    )
    def test_a_period_a_booking_would_refuse_names_the_date_that_is_wrong(
        self,
        service: SearchAvailability,
        availability: FakeAvailability,
        start: date,
        end: date,
        parameter: str,
    ) -> None:
        with pytest.raises(ValidationFailure) as raised:
            service.across_catalogue(start, end, ModelSearch())
        assert refusal_of(raised) == parameter
        assert availability.searches == []

    def test_an_unknown_category_and_an_unknown_branch_are_named(
        self, service: SearchAvailability, availability: FakeAvailability
    ) -> None:
        with pytest.raises(ValidationFailure) as category:
            service.across_catalogue(NINTH, TWELFTH, ModelSearch(category_slug="welding"))
        with pytest.raises(ValidationFailure) as branch:
            service.across_catalogue(NINTH, TWELFTH, ModelSearch(), "CBD")
        assert refusal_of(category) == "category"
        assert refusal_of(branch) == "branch"
        assert availability.searches == []

    def test_the_day_it_is_comes_from_the_business_time_zone(
        self, availability: FakeAvailability
    ) -> None:
        """Half past midnight on the second in Cape Town is still the first in UTC."""
        clock = FixedClock(datetime(2026, 3, 1, 22, 30, tzinfo=UTC))
        service = SearchAvailability(availability, FakeCatalogue(), FakeBranches(), clock)
        with pytest.raises(ValidationFailure) as raised:
            service.across_catalogue(date(2026, 3, 1), NINTH, ModelSearch())
        assert refusal_of(raised) == "from"


class TestAskingAboutOneModel:
    """The hire limits of the model, and a quantity a booking could carry."""

    def test_an_accepted_question_is_answered_with_its_period_and_quantity(
        self, service: SearchAvailability, availability: FakeAvailability
    ) -> None:
        answer = service.for_model(RAMMER.slug, NINTH, TWELFTH, 2)
        assert availability.model_questions == [(RAMMER.slug, BookingPeriod(NINTH, TWELFTH), 2)]
        assert answer.quantity == 2
        assert answer.branches == (FREE_AT_BELLVILLE,)

    @pytest.mark.parametrize(
        ("end", "quantity", "parameter"),
        [
            (date(2026, 3, 15), 1, "to"),
            (date(2026, 3, 10), 1, "to"),
            (TWELFTH, 0, "quantity"),
            (TWELFTH, 11, "quantity"),
        ],
    )
    def test_a_hire_outside_the_limits_of_the_model_and_a_bad_quantity_are_refused(
        self,
        service: SearchAvailability,
        availability: FakeAvailability,
        end: date,
        quantity: int,
        parameter: str,
    ) -> None:
        with pytest.raises(ValidationFailure) as raised:
            service.for_model(RAMMER.slug, NINTH, end, quantity)
        assert refusal_of(raised) == parameter
        assert availability.model_questions == []

    def test_a_slug_no_published_model_carries_is_not_found(
        self, service: SearchAvailability
    ) -> None:
        with pytest.raises(NotFound):
            service.for_model("no-such-model", NINTH, TWELFTH, 1)


class TestBrowsingTheCatalogue:
    """Two rules that are not SQL."""

    def test_a_search_in_a_known_category_reaches_the_port(self) -> None:
        catalogue = FakeCatalogue()
        search = ModelSearch(category_slug="compaction", page=2, page_size=10)
        page = BrowseCatalogue(catalogue).models(search)
        assert catalogue.searches == [search]
        assert (page.page, page.page_size, page.total) == (2, 10, 1)

    def test_a_search_in_an_unknown_category_is_refused_before_it_is_run(self) -> None:
        catalogue = FakeCatalogue()
        with pytest.raises(ValidationFailure) as raised:
            BrowseCatalogue(catalogue).models(ModelSearch(category_slug="welding"))
        assert refusal_of(raised) == "category"
        assert catalogue.searches == []

    def test_the_categories_and_one_model_are_handed_through(self) -> None:
        browse = BrowseCatalogue(FakeCatalogue())
        assert [entry.slug for entry in browse.categories()] == ["compaction"]
        assert browse.model(RAMMER.slug) is RAMMER
        with pytest.raises(NotFound):
            browse.model("no-such-model")


class TestAModelSearchChecksItself:
    """The second line behind the HTTP boundary."""

    @pytest.mark.parametrize(
        "arguments",
        [
            {"page": 0},
            {"page": 10_001},
            {"page_size": 0},
            {"page_size": 51},
            {"text": "x"},
            {"text": "x" * 121},
        ],
    )
    def test_a_search_out_of_range_cannot_be_built(self, arguments: dict[str, int | str]) -> None:
        with pytest.raises(ValueError, match="Attempted to search the catalogue"):
            ModelSearch(**arguments)

    def test_the_offset_is_the_models_before_the_page(self) -> None:
        assert ModelSearch().offset == 0
        assert ModelSearch(page=3, page_size=10).offset == 20


class TestHowARefusalNamesItsParameter:
    """One agreed key in the detail bag."""

    def test_the_parameter_travels_with_the_other_detail(self) -> None:
        failure = refused("to", "The return day is wrong.", {"hire_days": 0})
        assert failure.detail == {"hire_days": 0, REFUSED_PARAMETER: "to"}
        assert refused_parameter_of(failure) == "to"

    def test_a_failure_that_names_no_parameter_says_so(self) -> None:
        assert refused_parameter_of(ValidationFailure("The quantity is wrong.")) is None
        assert refused_parameter_of(ValidationFailure("Odd.", {REFUSED_PARAMETER: 7})) is None
