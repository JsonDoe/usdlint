"""Report renderers: text for people, JSON and JUnit XML for machines.

Every renderer takes the results of one ``usdguard check`` invocation
and returns the whole document as a string, so output is easy to test
and the CLI decides where it goes. Output is deterministic: the same
stages and checks always render byte for byte the same.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from usdguard.core import Report

FORMATS = ("text", "json", "junit")
"""Names accepted by :func:`render` and by ``usdguard check --format``."""


@dataclass(frozen=True)
class StageResult:
    """The report of one stage, labelled for display.

    Attributes:
        stage: Path of the stage as given on the command line, with
            forward slashes.
        report: Result of validating the stage. A stage that could not
            be opened has a single ``usdguard.open`` issue.
    """

    stage: str
    report: Report


def render(
    fmt: str,
    results: list[StageResult],
    *,
    profile: str,
    color: bool = False,
) -> str:
    """Render ``results`` in format ``fmt``.

    Args:
        fmt: One of :data:`FORMATS`.
        results: One entry per validated stage, in command-line order.
        profile: Name of the profile used, recorded in machine formats.
        color: Use ANSI colors (text format only).

    Raises:
        ValueError: ``fmt`` is not a known format.
    """
    from usdguard.reporters import json, junit, text

    if fmt == "text":
        return text.render_text(results, color=color)
    if fmt == "json":
        return json.render_json(results, profile=profile)
    if fmt == "junit":
        return junit.render_junit(results, profile=profile)
    msg = f"unknown format {fmt!r}; expected one of {', '.join(FORMATS)}"
    raise ValueError(msg)
