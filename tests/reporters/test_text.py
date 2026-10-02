"""Tests for the text reporter."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from usdguard.core import Report, Severity
from usdguard.reporters import StageResult, render
from usdguard.reporters.text import render_text

if TYPE_CHECKING:
    from usdguard.reporters import StageResult as Result

EXPECTED = """\
assets/chair/chair.usda
  error    stage.metadata    -            upAxis is not authored; expected 'Y'
  warning  geom.extent       /chair/seat  Mesh has no authored extent
           in layer assets/chair/geo.usda
  info     naming.prim_name  /chair/Leg1  Mesh name 'Leg1' does not match rule

assets/table.usda
  no issues

missing.usda
  error  usdguard.open  -  Cannot open stage 'missing.usda'

3 stages checked: 2 errors, 1 warning, 1 info. FAILED (fail on error)
"""


def test_text_report_aligns_columns_and_summarises(
    results: list[Result],
) -> None:
    assert render_text(results) == EXPECTED


def test_text_report_is_the_default_format(results: list[Result]) -> None:
    assert render("text", results, profile="default") == EXPECTED


def test_passing_runs_say_so() -> None:
    results = [StageResult("a.usda", Report(fail_on=Severity.WARNING))]

    assert render_text(results).splitlines()[-1] == (
        "1 stage checked: 0 errors, 0 warnings, 0 info. "
        "PASSED (fail on warning)"
    )


def test_colors_are_ansi_codes(results: list[Result]) -> None:
    text = render_text(results, color=True)

    assert "\033[1massets/chair/chair.usda\033[0m" in text
    assert "\033[31merror  \033[0m" in text
    assert "\033[33mwarning\033[0m" in text
    assert "\033[36minfo   \033[0m" in text
    assert text.rstrip().endswith("\033[31mFAILED\033[0m (fail on error)")
    assert "\033" not in render_text(results)


def test_empty_results_render_a_summary_only() -> None:
    assert render_text([]) == (
        "0 stages checked: 0 errors, 0 warnings, 0 info. "
        "PASSED (fail on error)\n"
    )


def test_unknown_formats_are_rejected(results: list[Result]) -> None:
    with pytest.raises(ValueError, match="unknown format 'yaml'"):
        render("yaml", results, profile="default")
