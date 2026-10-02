"""Sample results shared by the reporter tests."""

from __future__ import annotations

import pytest

from usdguard.core import Issue, Report, Severity
from usdguard.errors import StageOpenError
from usdguard.reporters import StageResult
from usdguard.runner import open_failure_report

CHECKS = ("geom.extent", "naming.prim_name", "stage.metadata")


@pytest.fixture
def results() -> list[StageResult]:
    """A failing stage, a clean stage and a stage that did not open."""
    failing = Report(
        issues=(
            Issue(
                "stage.metadata",
                Severity.ERROR,
                "upAxis is not authored; expected 'Y'",
            ),
            Issue(
                "geom.extent",
                Severity.WARNING,
                "Mesh has no authored extent",
                "/chair/seat",
                "assets/chair/geo.usda",
            ),
            Issue(
                "naming.prim_name",
                Severity.INFO,
                "Mesh name 'Leg1' does not match rule",
                "/chair/Leg1",
            ),
        ),
        fail_on=Severity.ERROR,
        check_ids=CHECKS,
    )
    clean = Report(fail_on=Severity.ERROR, check_ids=CHECKS)
    missing = open_failure_report(
        StageOpenError("Cannot open stage 'missing.usda'")
    )
    return [
        StageResult("assets/chair/chair.usda", failing),
        StageResult("assets/table.usda", clean),
        StageResult("missing.usda", missing),
    ]
