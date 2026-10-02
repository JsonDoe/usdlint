"""Open stages and run checks against them.

The runner owns the execution model: stage checks run first, then all
prim checks share one traversal of the stage. Every check invocation is
isolated, so a crashing check is reported as an issue instead of
aborting the run, and the resulting issues are sorted deterministically.
"""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, Literal

from pxr import Tf, Usd

from usdguard.core import (
    Check,
    Context,
    Issue,
    PrimCheck,
    Report,
    Severity,
    StageCheck,
)
from usdguard.errors import StageOpenError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence

logger = logging.getLogger(__name__)

LoadPolicy = Literal["all", "none"]
"""Payload policy when opening a stage: load every payload, or none."""

LOAD_POLICIES: tuple[LoadPolicy, ...] = ("all", "none")

_TF_ERROR_MESSAGE = re.compile(r" : '(?P<message>.*)'$")


def open_stage(path: str, *, load: LoadPolicy = "all") -> Usd.Stage:
    """Open the stage whose root layer is ``path``.

    Args:
        path: File path or asset path of the root layer.
        load: ``"all"`` loads every payload. ``"none"`` loads none: a
            prim carrying a payload is then unloaded, so neither it nor
            anything its payload brings in is traversed, and prim checks
            do not see them.

    Raises:
        StageOpenError: The stage cannot be opened.
        ValueError: ``load`` is not a known payload policy.
    """
    if load not in LOAD_POLICIES:
        msg = f"invalid load policy {load!r}; expected 'all' or 'none'"
        raise ValueError(msg)
    load_set = Usd.Stage.LoadAll if load == "all" else Usd.Stage.LoadNone
    try:
        stage = Usd.Stage.Open(path, load_set)
    except Tf.ErrorException as exc:
        msg = f"Cannot open stage {path!r}: {_describe_tf_error(exc)}"
        raise StageOpenError(msg) from exc
    if not stage:
        msg = f"Cannot open stage {path!r}"
        raise StageOpenError(msg)
    return stage


def run(
    stage: Usd.Stage,
    checks: Sequence[Check],
    *,
    stage_path: str = "",
    fail_on: Severity = Severity.ERROR,
    severity_overrides: Mapping[str, Severity] | None = None,
) -> Report:
    """Validate ``stage`` with ``checks`` and return the report.

    Stage checks run first, in the given order. Prim checks then share a
    single traversal of the stage, followed by one traversal of each
    instancing prototype. Prims inside a prototype are therefore checked
    once, not once per instance, and are reported under their prototype
    path (``/__Prototype_1/...``).

    Each check invocation is isolated: the issues it yields are
    collected inside ``try``/``except``. When a check raises, the
    traceback is logged, the issues it yielded during that invocation
    are discarded, and a single ERROR issue ``"Check crashed: <repr>"``
    replaces them. The run then continues with the next invocation.

    Args:
        stage: The stage to validate.
        checks: Configured check instances.
        stage_path: Path the stage was opened from, exposed to checks
            through :attr:`Context.stage_path`.
        fail_on: Lowest severity that makes the report fail.
        severity_overrides: Severity per ``check_id`` that replaces the
            check's default severity. Issues a check reports with an
            explicit severity, and crash issues, keep their severity.

    Returns:
        The report. Issues are sorted by severity (most severe first),
        then check_id, prim path, message and layer.
    """
    overrides = dict(severity_overrides or {})
    context = Context(stage=stage, stage_path=stage_path)
    issues: list[Issue] = []
    for check in checks:
        if isinstance(check, StageCheck):
            stage_issues = partial(check.check_stage, context)
            issues += _invoke(check, stage_issues, overrides)
    prim_checks = [check for check in checks if isinstance(check, PrimCheck)]
    if prim_checks:
        for prim in _traverse(stage):
            prim_path = str(prim.GetPath())
            for prim_check in prim_checks:
                prim_issues = partial(_check_prim, prim_check, prim, context)
                issues += _invoke(
                    prim_check, prim_issues, overrides, prim_path=prim_path
                )
    return Report(
        issues=tuple(sorted(issues, key=_sort_key)),
        fail_on=fail_on,
        check_ids=tuple(sorted({check.check_id for check in checks})),
    )


def _check_prim(
    check: PrimCheck, prim: Usd.Prim, context: Context
) -> Iterable[Issue]:
    if not check.applies_to(prim):
        return ()
    return check.check_prim(prim, context)


def _invoke(
    check: Check,
    produce: Callable[[], Iterable[Issue]],
    overrides: Mapping[str, Severity],
    *,
    prim_path: str = "",
) -> list[Issue]:
    """Collect the issues of one check invocation, isolating crashes."""
    try:
        issues = list(produce())
    except Exception as exc:
        logger.exception(
            "Check %s crashed%s",
            check.check_id,
            f" on prim {prim_path}" if prim_path else "",
        )
        return [
            Issue(
                check_id=check.check_id,
                severity=Severity.ERROR,
                message=f"Check crashed: {exc!r}",
                prim_path=prim_path,
            )
        ]
    override = overrides.get(check.check_id)
    if override is None:
        return issues
    return [
        replace(issue, severity=override)
        if issue.severity == check.severity
        else issue
        for issue in issues
    ]


def _traverse(stage: Usd.Stage) -> Iterator[Usd.Prim]:
    """Yield the stage's prims, then the prims inside each prototype.

    Prototype roots are skipped: they mirror instance prims, which the
    stage traversal already yields.
    """
    yield from stage.Traverse()
    for prototype in stage.GetPrototypes():
        for prim in Usd.PrimRange(prototype):
            if not prim.IsPrototype():
                yield prim


def _sort_key(issue: Issue) -> tuple[int, str, str, str, str]:
    return (
        -issue.severity,
        issue.check_id,
        issue.prim_path,
        issue.message,
        issue.layer,
    )


def _describe_tf_error(exc: Exception) -> str:
    """Return the messages of a ``Tf.ErrorException`` without source info.

    USD formats each error as ``Error in '<function>' at line <n> in file
    <source> : '<message>'``; only the messages help the user.
    """
    messages = [
        match.group("message")
        for line in str(exc).splitlines()
        if (match := _TF_ERROR_MESSAGE.search(line.strip()))
    ]
    return "; ".join(messages) or str(exc).strip()
