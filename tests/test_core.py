"""Tests for the core data model and check base classes."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import pytest

from usdguard.core import (
    Check,
    Context,
    Issue,
    PrimCheck,
    Report,
    Severity,
    StageCheck,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from pxr import Usd


class WarningCheck(StageCheck):
    check_id = "test.warning"
    description = "Reports nothing; used to build issues."
    severity = Severity.WARNING

    def check_stage(self, context: Context) -> Iterator[Issue]:
        yield from ()


class AnyPrimCheck(PrimCheck):
    check_id = "test.any_prim"
    description = "Accepts every prim and reports nothing."

    def check_prim(self, prim: Usd.Prim, context: Context) -> Iterator[Issue]:
        yield from ()


def test_severity_orders_by_seriousness() -> None:
    assert Severity.INFO < Severity.WARNING < Severity.ERROR


def test_severity_labels_are_lower_case_names() -> None:
    assert [severity.label for severity in Severity] == [
        "info",
        "warning",
        "error",
    ]


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("info", Severity.INFO),
        ("WARNING", Severity.WARNING),
        ("Error", Severity.ERROR),
    ],
)
def test_severity_from_label_ignores_case(
    label: str, expected: Severity
) -> None:
    assert Severity.from_label(label) is expected


@pytest.mark.parametrize("label", ["fatal", "", 30, None])
def test_severity_from_label_rejects_unknown_values(label: object) -> None:
    with pytest.raises(ValueError, match="expected one of: info, warning"):
        Severity.from_label(label)


def test_issue_defaults_to_no_location_and_is_frozen() -> None:
    issue = Issue("test.id", Severity.ERROR, "message")

    assert (issue.prim_path, issue.layer) == ("", "")
    with pytest.raises(dataclasses.FrozenInstanceError):
        issue.message = "changed"  # type: ignore[misc]


def test_context_cache_is_private_to_each_context() -> None:
    first = Context(stage=None)
    second = Context(stage=None)
    first.cache["key"] = 1

    assert second.cache == {}


def test_report_exit_code_follows_fail_on() -> None:
    issues = (Issue("test.id", Severity.WARNING, "w"),)

    assert Report(issues, fail_on=Severity.ERROR).exit_code == 0
    assert Report(issues, fail_on=Severity.WARNING).exit_code == 1
    assert Report(issues, fail_on=Severity.INFO).exit_code == 1
    assert Report((), fail_on=Severity.INFO).exit_code == 0


def test_report_counts_every_severity_most_severe_first() -> None:
    report = Report(
        (
            Issue("test.id", Severity.INFO, "a"),
            Issue("test.id", Severity.INFO, "b"),
            Issue("test.id", Severity.ERROR, "c"),
        )
    )

    assert list(report.counts().items()) == [
        (Severity.ERROR, 1),
        (Severity.WARNING, 0),
        (Severity.INFO, 2),
    ]


def test_issue_helper_records_prim_layer_and_default_severity(
    make_stage: Callable[[str], Usd.Stage],
) -> None:
    stage = make_stage('def Xform "root" {}')

    issue = WarningCheck().issue(
        "message", stage.GetPrimAtPath("/root"), layer="a.usda"
    )

    assert issue == Issue(
        "test.warning", Severity.WARNING, "message", "/root", "a.usda"
    )


def test_issue_helper_accepts_an_explicit_severity() -> None:
    issue = WarningCheck().issue("note", severity=Severity.INFO)

    assert issue.severity is Severity.INFO
    assert issue.prim_path == ""


def test_prim_check_applies_to_every_prim_by_default(
    make_stage: Callable[[str], Usd.Stage],
) -> None:
    stage = make_stage(
        """
        def Xform "root"
        {
            def Scope "child" {}
        }
        """
    )

    assert all(AnyPrimCheck().applies_to(prim) for prim in stage.Traverse())


def test_base_check_cannot_skip_its_abstract_method() -> None:
    class Incomplete(StageCheck):
        check_id = "test.incomplete"
        description = "Missing check_stage."

    with pytest.raises(TypeError, match="abstract"):
        Incomplete()  # type: ignore[abstract]


def test_check_base_class_declares_default_severity() -> None:
    assert Check.severity is Severity.ERROR
