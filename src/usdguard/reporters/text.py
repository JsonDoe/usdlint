"""Human-readable report with aligned columns and a summary line."""

from __future__ import annotations

from typing import TYPE_CHECKING

from usdguard.core import Severity

if TYPE_CHECKING:
    from usdguard.core import Issue
    from usdguard.reporters import StageResult

_COLORS = {
    Severity.ERROR: "\033[31m",
    Severity.WARNING: "\033[33m",
    Severity.INFO: "\033[36m",
}
_BOLD = "\033[1m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_RESET = "\033[0m"


def render_text(results: list[StageResult], *, color: bool = False) -> str:
    """Render one block per stage, then a summary line.

    Issues are listed in report order, one per line, with the severity,
    check id, prim path (``-`` for stage-level issues) and message in
    aligned columns; the layer, when known, follows on its own line.

    Args:
        results: One entry per validated stage.
        color: Color severities and the verdict with ANSI codes.
    """
    lines: list[str] = []
    for result in results:
        title = result.stage
        lines.append(f"{_BOLD}{title}{_RESET}" if color else title)
        lines.extend(_issue_lines(result.report.issues, color=color))
        lines.append("")
    lines.append(_summary(results, color=color))
    return "\n".join(lines) + "\n"


def _issue_lines(issues: tuple[Issue, ...], *, color: bool) -> list[str]:
    if not issues:
        return ["  no issues"]
    severity_width = max(len(issue.severity.label) for issue in issues)
    check_width = max(len(issue.check_id) for issue in issues)
    prim_width = max(len(issue.prim_path or "-") for issue in issues)
    lines = []
    for issue in issues:
        severity = issue.severity.label.ljust(severity_width)
        if color:
            severity = f"{_COLORS[issue.severity]}{severity}{_RESET}"
        line = (
            f"  {severity}  {issue.check_id.ljust(check_width)}  "
            f"{(issue.prim_path or '-').ljust(prim_width)}  {issue.message}"
        )
        lines.append(line.rstrip())
        if issue.layer:
            lines.append(f"  {' ' * severity_width}  in layer {issue.layer}")
    return lines


def _summary(results: list[StageResult], *, color: bool) -> str:
    totals = dict.fromkeys(Severity, 0)
    for result in results:
        for severity, count in result.report.counts().items():
            totals[severity] += count
    failed = any(result.report.exit_code for result in results)
    fail_on = results[0].report.fail_on if results else Severity.ERROR
    verdict = "FAILED" if failed else "PASSED"
    if color:
        verdict = f"{_RED if failed else _GREEN}{verdict}{_RESET}"
    counts = ", ".join(
        _plural(totals[severity], severity.label)
        for severity in sorted(Severity, reverse=True)
    )
    return (
        f"{_plural(len(results), 'stage')} checked: {counts}. "
        f"{verdict} (fail on {fail_on.label})"
    )


def _plural(count: int, noun: str) -> str:
    if noun == "info":
        return f"{count} info"
    return f"{count} {noun}{'' if count == 1 else 's'}"
