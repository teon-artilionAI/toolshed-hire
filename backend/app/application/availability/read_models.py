"""What an availability search is asked with and what it hands back.

The answer for a branch is one boolean and nothing else. US-07 says a customer
is told where a machine is free and never how many there are or which tagged
unit it is, so these types have no field a tag or a count could travel in.
The counting happens inside the database and only the comparison comes out.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.catalogue.read_models import ModelSearch, ModelSummary
from app.domain.period import BookingPeriod


@dataclass(frozen=True, slots=True)
class AvailabilitySearch:
    """An availability search across the catalogue, already validated.

    Attributes:
        period: The half open hire period being asked about.
        models: Which models to answer for, in what order, and which page.
        branch_code: When set, only models free at this branch are listed.

    """

    period: BookingPeriod
    models: ModelSearch
    branch_code: str | None = None


@dataclass(frozen=True, slots=True)
class BranchAvailability:
    """Whether one branch can supply a model for the whole period asked about.

    Attributes:
        branch_code: The short code of the branch.
        branch_name: The display name of the branch.
        available: True when enough units are free there for the whole period.

    """

    branch_code: str
    branch_name: str
    available: bool


@dataclass(frozen=True, slots=True)
class ModelAvailability:
    """One model of a search, with an answer from every active branch.

    Attributes:
        model: The catalogue entry.
        branches: One answer per active branch, in the same order for every
            model, including the branches that hold no unit of it.

    """

    model: ModelSummary
    branches: tuple[BranchAvailability, ...]


@dataclass(frozen=True, slots=True)
class AvailabilityPage:
    """One page of an availability search.

    Attributes:
        period: The period that was asked about.
        items: The models on the page with their answers.
        page: The page this is, counted from one.
        page_size: How many models a page holds.
        total: How many models match the search across every page.

    """

    period: BookingPeriod
    items: tuple[ModelAvailability, ...]
    page: int
    page_size: int
    total: int


@dataclass(frozen=True, slots=True)
class ModelAvailabilityAnswer:
    """Where one model is free for a period, in the quantity asked for.

    Attributes:
        period: The period that was asked about.
        quantity: How many units were asked for.
        branches: One answer per active branch.

    """

    period: BookingPeriod
    quantity: int
    branches: tuple[BranchAvailability, ...]
