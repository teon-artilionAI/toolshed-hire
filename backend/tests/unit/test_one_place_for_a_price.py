"""A hire price is worked out in one place, and this reads the source to keep it so.

BR-21 says the price comes from a pricing policy and not from arithmetic
scattered through the system. A test of the policy cannot prove that, because
a second calculation somewhere else would pass every test of the first. So
this one parses every module of the application and looks for the arithmetic
itself.

Three things are held.

1. `Money.times` and `Money.percent_of` are called only inside
   `app/domain/policies` and `app/domain/vat.py`. Those two methods are the
   only way an amount is multiplied, so nothing outside can scale a rate.
2. A rate is multiplied by a number of days in `StandardPricingPolicy` and
   nowhere else.
3. No module multiplies a bare number that is named after a rate, a deposit,
   a fee or VAT. The one `*` on an amount is inside `Money` itself.

The route and the policy are compared figure for figure in
tests/api/test_quote.py.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

APP_ROOT: Final[Path] = Path(__file__).resolve().parents[2] / "app"
POLICIES_PACKAGE: Final[str] = "domain/policies/"
STANDARD_POLICY_MODULE: Final[str] = "domain/policies/standard_pricing.py"
VAT_MODULE: Final[str] = "domain/vat.py"
MONEY_MODULE: Final[str] = "domain/money.py"
SCALING_METHODS: Final[frozenset[str]] = frozenset({"times", "percent_of"})
VAT_FUNCTION: Final[str] = "vat_on"
# A multiplication whose operands are named with one of these words is pricing
# arithmetic. A name is split at its underscores, so `daily_rate` is two words.
MONEY_WORDS: Final[frozenset[str]] = frozenset(
    {
        "daily",
        "weekly",
        "deposit",
        "fee",
        "price",
        "charge",
        "subtotal",
        "vat",
        "discount",
        "amount",
    }
)
DAY_WORDS: Final[frozenset[str]] = frozenset({"days", "weeks"})
WORD_SEPARATOR: Final[str] = "_"


def application_modules() -> dict[str, ast.Module]:
    """Return every module of the application, parsed, keyed by its path under `app`."""
    return {
        path.relative_to(APP_ROOT).as_posix(): ast.parse(path.read_text(encoding="utf-8"))
        for path in sorted(APP_ROOT.rglob("*.py"))
    }


def words_in(node: ast.AST) -> set[str]:
    """Return every word of every name and attribute inside a node, in lower case."""
    found: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            found.update(child.id.lower().split(WORD_SEPARATOR))
        elif isinstance(child, ast.Attribute):
            found.update(child.attr.lower().split(WORD_SEPARATOR))
    return found


def mentions(node: ast.AST, words: frozenset[str]) -> bool:
    """Return True when a name inside the node is written with one of the words."""
    return not words.isdisjoint(words_in(node))


def scaling_calls(tree: ast.Module) -> list[ast.Call]:
    """Return every call of `.times(...)` or `.percent_of(...)` in a module."""
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in SCALING_METHODS
    ]


MODULES: Final[dict[str, ast.Module]] = application_modules()


def test_the_source_was_found_and_read() -> None:
    assert STANDARD_POLICY_MODULE in MODULES
    assert len(MODULES) > 50, "The scan found too few modules to prove anything."


def test_an_amount_is_scaled_only_inside_the_policies_and_the_vat_module() -> None:
    callers = {name for name, tree in MODULES.items() if scaling_calls(tree)}
    outside = {
        name for name in callers if not name.startswith(POLICIES_PACKAGE) and name != VAT_MODULE
    }
    assert outside == set(), (
        f"These modules multiply an amount of money: {sorted(outside)}. A price is worked "
        "out by the pricing policy and nowhere else (BR-21)."
    )


def test_a_rate_is_multiplied_by_days_in_the_standard_policy_and_nowhere_else() -> None:
    by_days = {
        name
        for name, tree in MODULES.items()
        for call in scaling_calls(tree)
        if any(mentions(argument, DAY_WORDS) for argument in call.args)
    }
    assert by_days == {STANDARD_POLICY_MODULE}


def test_vat_is_worked_out_only_by_the_policies() -> None:
    callers = {
        name
        for name, tree in MODULES.items()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == VAT_FUNCTION
    }
    assert callers <= {name for name in MODULES if name.startswith(POLICIES_PACKAGE)}
    assert callers, "Nothing calls vat_on, so the scan is looking for the wrong name."


def test_no_module_multiplies_a_bare_rate_deposit_fee_or_vat_figure() -> None:
    offenders = sorted(
        f"{name}:{node.lineno}"
        for name, tree in MODULES.items()
        if name != MONEY_MODULE
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Mult | ast.Div)
        and mentions(node, MONEY_WORDS)
    )
    assert offenders == [], (
        f"These lines multiply or divide a figure named after money: {offenders}. Hold the "
        "figure as Money and let the pricing policy work the price out."
    )
