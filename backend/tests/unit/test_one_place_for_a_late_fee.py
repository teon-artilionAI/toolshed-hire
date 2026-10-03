"""A late fee is worked out in one place, and this reads the source to keep it so.

BR-30 says a late fee comes from a late fee policy, the second Strategy the
design document names. A test of the policy cannot prove that, because a
second calculation somewhere else would pass every test of the first. So this
parses every module of the application, as tests/unit/test_one_place_for_a_price.py
does for the hire price, and looks for the calculation itself.

Four things are held.

1. Every call of `.late_fee(...)` outside `app/domain/policies` is a call on a
   policy, an object whose name says it is one, so every late fee the system
   shows or charges came from the policy it was handed.
2. Nothing outside `app/domain/policies` takes the smaller or the larger of a
   number of days, which is how the fourteen day limit of BR-31 would be
   written a second time.
3. The fourteen days themselves are written once, in the standard policy, in
   any module that has anything to do with a late fee.
4. The function the counter's dashboard used before the policy existed is gone.
"""

from __future__ import annotations

import ast
from typing import Final

from tests.unit.test_one_place_for_a_price import (
    MODULES,
    POLICIES_PACKAGE,
    words_in,
)

LATE_FEE_METHOD: Final[str] = "late_fee"
POLICY_WORD: Final[str] = "policy"
DAY_WORDS: Final[frozenset[str]] = frozenset({"days", "day"})
LIMIT_FUNCTIONS: Final[frozenset[str]] = frozenset({"min", "max"})
LATE_FEE_WORDS: Final[frozenset[str]] = frozenset({"late"})
STANDARD_LATE_FEE_MODULE: Final[str] = "domain/policies/standard_late_fee.py"
ACCRUAL_LIMIT: Final[int] = 14
RETIRED_FUNCTION: Final[str] = "late_fee_accrued"


def outside_the_policies() -> dict[str, ast.Module]:
    """Return every module of the application that is not a policy."""
    return {name: tree for name, tree in MODULES.items() if not name.startswith(POLICIES_PACKAGE)}


def late_fee_calls(tree: ast.Module) -> list[ast.Call]:
    """Return every call of a method named `late_fee` in a module."""
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == LATE_FEE_METHOD
    ]


def test_the_scan_finds_the_callers_of_the_policy() -> None:
    callers = {name for name, tree in outside_the_policies().items() if late_fee_calls(tree)}
    assert {"application/hire/overview.py", "application/hire/progress.py"} <= callers
    assert "domain/returns.py" in callers


def test_every_late_fee_outside_the_policies_is_asked_of_a_policy() -> None:
    offenders = sorted(
        f"{name}:{call.lineno}"
        for name, tree in outside_the_policies().items()
        for call in late_fee_calls(tree)
        if isinstance(call.func, ast.Attribute)
        and POLICY_WORD not in words_in(call.func.value)
    )
    assert offenders == [], (
        f"These lines work out a late fee from something that is not a policy: {offenders}. "
        "A late fee comes from the late fee policy and nowhere else (BR-30)."
    )


def test_nothing_outside_the_policies_caps_a_number_of_days() -> None:
    offenders = sorted(
        f"{name}:{node.lineno}"
        for name, tree in outside_the_policies().items()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in LIMIT_FUNCTIONS
        and any(not DAY_WORDS.isdisjoint(words_in(argument)) for argument in node.args)
    )
    assert offenders == [], (
        f"These lines limit a number of days outside the policies: {offenders}. The days a "
        "late fee is charged for stop where the late fee policy says (BR-31)."
    )


def test_the_fourteen_days_are_written_once_among_the_modules_of_a_late_fee() -> None:
    writers = {
        name
        for name, tree in MODULES.items()
        if not LATE_FEE_WORDS.isdisjoint(words_in(tree))
        and any(
            isinstance(node, ast.Constant)
            and type(node.value) is int
            and node.value == ACCRUAL_LIMIT
            for node in ast.walk(tree)
        )
    }
    assert writers == {STANDARD_LATE_FEE_MODULE}


def test_the_function_the_policy_replaced_is_gone() -> None:
    defined = {
        name
        for name, tree in MODULES.items()
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == RETIRED_FUNCTION
    }
    assert defined == set()
