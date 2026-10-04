"""The two ports the reporting module reads through.

Both are reads. They write nothing, so they need no unit of work, and each
takes a bounded number of statements however many units, hires or charges
there are. The query objects behind them are in the infrastructure layer.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from app.application.reporting.evidence import FleetEvidence, ReportScope
from app.application.reporting.report_models import AttentionCounts, BranchPosition


class FleetReportQuery(Protocol):
    """What the utilisation report reads about the fleet."""

    def evidence(self, scope: ReportScope) -> FleetEvidence:
        """Return every unit in scope and everything dated about them that touches the period."""
        ...

    def category_exists(self, slug: str) -> bool:
        """Return True when a category, active or not, has this slug."""
        ...


class AdminDashboardQuery(Protocol):
    """What the admin dashboard counts across the business."""

    def branch_positions(self, today: date) -> tuple[BranchPosition, ...]:
        """Return what is due today at each trading branch and where its units stand."""
        ...

    def attention_counts(self) -> AttentionCounts:
        """Return the open damage reports, the customers on hold and the failed messages."""
        ...
