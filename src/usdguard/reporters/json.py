"""Machine-readable JSON report (schema in ``docs/report-schema.md``)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import usdguard

if TYPE_CHECKING:
    from usdguard.core import Issue
    from usdguard.reporters import StageResult

SCHEMA_VERSION = 1
"""Version of the report schema; bumped on incompatible changes."""


def render_json(results: list[StageResult], *, profile: str) -> str:
    """Render the results as a JSON document.

    Keys are sorted and issues keep the report's deterministic order,
    so two runs over the same files produce identical documents and
    diffs between runs are meaningful.

    Args:
        results: One entry per validated stage.
        profile: Name of the profile used.
    """
    document = {
        "schema_version": SCHEMA_VERSION,
        "tool": {"name": "usdguard", "version": usdguard.__version__},
        "profile": profile,
        "runs": [
            {
                "stage": result.stage,
                "summary": {
                    severity.label: count
                    for severity, count in result.report.counts().items()
                },
                "issues": [_issue(issue) for issue in result.report.issues],
            }
            for result in results
        ],
    }
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def _issue(issue: Issue) -> dict[str, Any]:
    return {
        "check_id": issue.check_id,
        "severity": issue.severity.label,
        "message": issue.message,
        "prim_path": issue.prim_path,
        "layer": issue.layer,
    }
