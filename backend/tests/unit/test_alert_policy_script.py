"""The prepared alert-policy recreation script (B3.2, B3.7, C-43).

The cloud policies are operational. This check protects the corrected policy
shape: summed counter values, a zero sustained duration and explicit comparison
operators for the thresholds that are documented as inclusive.
"""

from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "infra" / "scripts" / "create-alert-policies.sh"


def test_policies_sum_counter_values_not_samples() -> None:
    """A DELTA/INT64 counter is summed across its values, not counted as points."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "ALIGN_SUM" in text
    assert "REDUCE_SUM" in text
    assert '"perSeriesAligner":"ALIGN_COUNT"' not in text
    assert "--duration=0s" in text


def test_inclusive_thresholds_are_explicit_and_replacement_is_opt_in() -> None:
    """The documented five and twenty thresholds are inclusive, not off by one."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"auth_account_lockouts" 600 ">=" 5' in text
    assert '"api_refusals" 600 ">=" 20' in text
    assert "REPLACE_EXISTING" in text
