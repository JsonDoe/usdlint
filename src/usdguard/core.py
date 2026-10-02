"""Data model and base classes shared by checks, the runner and reporters.

A validation run applies :class:`Check` instances to a stage and
collects the :class:`Issue` objects they yield into a :class:`Report`.
:class:`StageCheck` subclasses look at the whole stage once;
:class:`PrimCheck` subclasses are called for every prim of a single
traversal shared by all prim checks.
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pxr import Usd


class Severity(enum.IntEnum):
    """How serious an issue is; a higher value is more severe."""

    INFO = 10
    WARNING = 20
    ERROR = 30

    @property
    def label(self) -> str:
        """Lower-case name used in profiles, reports and on the CLI."""
        return self.name.lower()

    @classmethod
    def from_label(cls, label: object) -> Severity:
        """Return the severity named by ``label``, ignoring case.

        Args:
            label: ``"info"``, ``"warning"`` or ``"error"``.

        Raises:
            ValueError: ``label`` does not name a severity.
        """
        if isinstance(label, str) and label.upper() in cls.__members__:
            return cls[label.upper()]
        choices = ", ".join(severity.label for severity in cls)
        msg = f"invalid severity {label!r}; expected one of: {choices}"
        raise ValueError(msg)


@dataclass(frozen=True)
class Issue:
    """A single finding reported by a check.

    Attributes:
        check_id: Identifier of the check that reported the issue.
        severity: How serious the issue is.
        message: Human-readable description of the problem.
        prim_path: Path of the offending prim; empty for stage-level
            issues.
        layer: Identifier of the offending layer, when known.
    """

    check_id: str
    severity: Severity
    message: str
    prim_path: str = ""
    layer: str = ""


@dataclass(frozen=True)
class Context:
    """What a check can look at during one validation run.

    Attributes:
        stage: The composed stage being validated.
        stage_path: Path the stage was opened from; empty for in-memory
            stages.
        cache: Scratch space shared by every check of the run, for
            results that are expensive to compute. Keys are prefixed
            with the ``check_id`` of the check that stores them.
    """

    stage: Usd.Stage
    stage_path: str = ""
    cache: dict[str, Any] = field(default_factory=dict)


class Check(ABC):
    """Base class of every check.

    Subclasses derive from :class:`StageCheck` or :class:`PrimCheck`,
    set the class attributes below and implement the matching method.
    Keyword arguments of the constructor are the check's options; a
    profile sets them from its ``[options."<check_id>"]`` table, so a
    constructor validates them and raises ``ValueError`` or
    ``TypeError`` for bad values.

    The docstring of a check class explains its rationale, its options
    and a minimal failing example; ``usdguard explain`` prints it.

    Attributes:
        check_id: Unique identifier, ``<family>.<name>``. Plugins
            register their checks under this name.
        description: One-line summary shown by ``usdguard list-checks``.
        severity: Default severity of the issues the check reports.
    """

    check_id: ClassVar[str]
    description: ClassVar[str]
    severity: ClassVar[Severity] = Severity.ERROR

    def issue(
        self,
        message: str,
        prim: Usd.Prim | None = None,
        layer: str = "",
        *,
        severity: Severity | None = None,
    ) -> Issue:
        """Build an issue attributed to this check.

        Args:
            message: Human-readable description of the problem.
            prim: Offending prim, if any; its path is recorded.
            layer: Identifier of the offending layer, if any.
            severity: Severity of this issue instead of the check's
                default, for instance to report an informational note.
                Profile severity overrides do not apply to it.
        """
        return Issue(
            check_id=self.check_id,
            severity=self.severity if severity is None else severity,
            message=message,
            prim_path=str(prim.GetPath()) if prim is not None else "",
            layer=layer,
        )


class StageCheck(Check):
    """A check that inspects the stage as a whole, once per run."""

    @abstractmethod
    def check_stage(self, context: Context) -> Iterator[Issue]:
        """Yield the issues found on ``context.stage``."""


class PrimCheck(Check):
    """A check called for every prim of the shared traversal."""

    def applies_to(self, prim: Usd.Prim) -> bool:
        """Return whether :meth:`check_prim` should be called for ``prim``.

        The default accepts every prim; filtering here keeps
        :meth:`check_prim` focused on the prims it understands.
        """
        return True

    @abstractmethod
    def check_prim(self, prim: Usd.Prim, context: Context) -> Iterator[Issue]:
        """Yield the issues found on ``prim``."""


@dataclass(frozen=True)
class Report:
    """Outcome of validating one stage.

    Attributes:
        issues: Every issue found, most severe first (see
            :func:`usdguard.runner.run` for the exact order).
        fail_on: Lowest severity that makes the report fail.
        check_ids: Sorted identifiers of the checks that ran.
    """

    issues: tuple[Issue, ...] = ()
    fail_on: Severity = Severity.ERROR
    check_ids: tuple[str, ...] = ()

    @property
    def exit_code(self) -> int:
        """1 if any issue is at or above :attr:`fail_on`, else 0."""
        return int(
            any(issue.severity >= self.fail_on for issue in self.issues)
        )

    def counts(self) -> dict[Severity, int]:
        """Return the number of issues per severity, most severe first.

        Every severity is present, with a count of zero if needed.
        """
        counts = dict.fromkeys(sorted(Severity, reverse=True), 0)
        for issue in self.issues:
            counts[issue.severity] += 1
        return counts
