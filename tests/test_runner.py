"""Tests for the runner: execution order, isolation, ordering, opening."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from usdguard import runner as runner_module
from usdguard.core import Context, Issue, PrimCheck, Severity, StageCheck
from usdguard.errors import StageOpenError
from usdguard.runner import open_stage, run

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from pxr import Usd

    StageFactory = Callable[[str], Usd.Stage]

SCENE = """
def Xform "root"
{
    def Mesh "body" {}
    def Scope "looks" {}
}
"""

INSTANCED_SCENE = """
def Xform "set"
{
    def Xform "tree_1" (instanceable = true
        prepend references = </tree_src>) {}
    def Xform "tree_2" (instanceable = true
        prepend references = </tree_src>) {}
}
over "tree_src"
{
    def Mesh "leaves" {}
}
"""


class RecordingStageCheck(StageCheck):
    check_id = "test.stage"
    description = "Records when it runs."

    def __init__(self, log: list[str]) -> None:
        self.log = log

    def check_stage(self, context: Context) -> Iterator[Issue]:
        self.log.append(self.check_id)
        yield self.issue("stage issue")


class RecordingPrimCheck(PrimCheck):
    check_id = "test.prim"
    description = "Records every prim it sees."

    def __init__(self, log: list[str], suffix: str = "") -> None:
        self.log = log
        self.suffix = suffix

    def check_prim(self, prim: Usd.Prim, context: Context) -> Iterator[Issue]:
        self.log.append(f"{prim.GetPath()}{self.suffix}")
        yield from ()


class MeshOnlyCheck(PrimCheck):
    check_id = "test.mesh_only"
    description = "Reports every mesh."

    def applies_to(self, prim: Usd.Prim) -> bool:
        return prim.GetTypeName() == "Mesh"

    def check_prim(self, prim: Usd.Prim, context: Context) -> Iterator[Issue]:
        yield self.issue("mesh found", prim)


class CrashingStageCheck(StageCheck):
    check_id = "test.crash_stage"
    description = "Yields one issue, then crashes."

    def check_stage(self, context: Context) -> Iterator[Issue]:
        yield self.issue("reported before the crash")
        message = "boom"
        raise RuntimeError(message)


class CrashOnBodyCheck(PrimCheck):
    check_id = "test.crash_prim"
    description = "Crashes on the body prim only."

    def check_prim(self, prim: Usd.Prim, context: Context) -> Iterator[Issue]:
        if prim.GetName() == "body":
            raise KeyError(prim.GetName())
        yield self.issue("visited", prim)


class CrashInAppliesToCheck(PrimCheck):
    check_id = "test.crash_applies_to"
    description = "Crashes while filtering."

    def applies_to(self, prim: Usd.Prim) -> bool:
        return 1 / 0 > 0

    def check_prim(self, prim: Usd.Prim, context: Context) -> Iterator[Issue]:
        yield from ()


class MixedSeverityCheck(StageCheck):
    check_id = "test.mixed"
    description = "Reports a default-severity issue and an explicit note."

    def check_stage(self, context: Context) -> Iterator[Issue]:
        yield self.issue("default severity")
        yield self.issue("note", severity=Severity.INFO)


class ScrambledCheck(StageCheck):
    check_id = "test.scrambled"
    description = "Yields issues in no particular order."

    def check_stage(self, context: Context) -> Iterator[Issue]:
        yield self.issue("z", severity=Severity.INFO)
        yield Issue("a.other", Severity.ERROR, "b", "/b")
        yield Issue("a.other", Severity.ERROR, "a", "/b")
        yield Issue("a.other", Severity.ERROR, "c", "/a")
        yield self.issue("w", severity=Severity.WARNING)
        yield Issue("z.last", Severity.ERROR, "m", "/a")


def test_stage_checks_run_before_prim_checks(make_stage: StageFactory) -> None:
    log: list[str] = []
    checks = [RecordingPrimCheck(log), RecordingStageCheck(log)]

    run(make_stage(SCENE), checks)

    assert log[0] == "test.stage"
    assert log[1:] == ["/root", "/root/body", "/root/looks"]


def test_prim_checks_share_one_traversal(make_stage: StageFactory) -> None:
    log: list[str] = []
    checks = [RecordingPrimCheck(log, "#a"), RecordingPrimCheck(log, "#b")]

    run(make_stage(SCENE), checks)

    assert log == [
        "/root#a",
        "/root#b",
        "/root/body#a",
        "/root/body#b",
        "/root/looks#a",
        "/root/looks#b",
    ]


def test_applies_to_filters_prims(make_stage: StageFactory) -> None:
    report = run(make_stage(SCENE), [MeshOnlyCheck()])

    assert [issue.prim_path for issue in report.issues] == ["/root/body"]


def test_stage_check_crash_is_isolated(
    make_stage: StageFactory, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.ERROR, logger="usdguard")
    checks = [CrashingStageCheck(), MeshOnlyCheck()]

    report = run(make_stage(SCENE), checks)

    assert report.issues == (
        Issue(
            "test.crash_stage",
            Severity.ERROR,
            "Check crashed: RuntimeError('boom')",
        ),
        Issue("test.mesh_only", Severity.ERROR, "mesh found", "/root/body"),
    )
    (record,) = caplog.records
    assert "test.crash_stage crashed" in record.getMessage()
    assert record.exc_info is not None


def test_prim_check_crash_is_reported_on_its_prim(
    make_stage: StageFactory,
) -> None:
    report = run(make_stage(SCENE), [CrashOnBodyCheck()])

    assert [(i.prim_path, i.message) for i in report.issues] == [
        ("/root", "visited"),
        ("/root/body", "Check crashed: KeyError('body')"),
        ("/root/looks", "visited"),
    ]


def test_crash_in_applies_to_is_isolated(make_stage: StageFactory) -> None:
    report = run(make_stage(SCENE), [CrashInAppliesToCheck()])

    assert len(report.issues) == 3
    assert {issue.message for issue in report.issues} == {
        "Check crashed: ZeroDivisionError('division by zero')"
    }


def test_issues_are_sorted_deterministically(make_stage: StageFactory) -> None:
    report = run(make_stage(SCENE), [ScrambledCheck()])

    assert [
        (i.severity, i.check_id, i.prim_path, i.message) for i in report.issues
    ] == [
        (Severity.ERROR, "a.other", "/a", "c"),
        (Severity.ERROR, "a.other", "/b", "a"),
        (Severity.ERROR, "a.other", "/b", "b"),
        (Severity.ERROR, "z.last", "/a", "m"),
        (Severity.WARNING, "test.scrambled", "", "w"),
        (Severity.INFO, "test.scrambled", "", "z"),
    ]


def test_severity_override_replaces_the_default_severity_only(
    make_stage: StageFactory,
) -> None:
    report = run(
        make_stage(SCENE),
        [MixedSeverityCheck(), CrashingStageCheck()],
        severity_overrides={
            "test.mixed": Severity.WARNING,
            "test.crash_stage": Severity.INFO,
        },
    )

    assert [(i.check_id, i.severity, i.message) for i in report.issues] == [
        (
            "test.crash_stage",
            Severity.ERROR,
            "Check crashed: RuntimeError('boom')",
        ),
        ("test.mixed", Severity.WARNING, "default severity"),
        ("test.mixed", Severity.INFO, "note"),
    ]


def test_report_records_checks_and_fail_on(make_stage: StageFactory) -> None:
    log: list[str] = []
    report = run(
        make_stage(SCENE),
        [RecordingStageCheck(log), MeshOnlyCheck()],
        fail_on=Severity.WARNING,
    )

    assert report.check_ids == ("test.mesh_only", "test.stage")
    assert report.fail_on is Severity.WARNING
    assert report.exit_code == 1


def test_context_exposes_stage_path(make_stage: StageFactory) -> None:
    seen: list[str] = []

    class PathCheck(StageCheck):
        check_id = "test.path"
        description = "Records the stage path."

        def check_stage(self, context: Context) -> Iterator[Issue]:
            seen.append(context.stage_path)
            yield from ()

    run(make_stage(SCENE), [PathCheck()], stage_path="assets/a.usda")

    assert seen == ["assets/a.usda"]


def test_prototype_prims_are_checked_once_with_prototype_paths(
    make_stage: StageFactory,
) -> None:
    log: list[str] = []

    run(make_stage(INSTANCED_SCENE), [RecordingPrimCheck(log)])

    assert log == [
        "/set",
        "/set/tree_1",
        "/set/tree_2",
        "/__Prototype_1/leaves",
    ]


def test_open_stage_reads_a_file(tmp_path: Path) -> None:
    path = tmp_path / "asset.usda"
    path.write_text('#usda 1.0\ndef Xform "root" {}\n', encoding="utf-8")

    stage = open_stage(str(path))

    assert stage.GetPrimAtPath("/root").IsValid()


def test_open_stage_reports_missing_files_cleanly(tmp_path: Path) -> None:
    path = tmp_path / "missing.usda"

    with pytest.raises(StageOpenError) as excinfo:
        open_stage(str(path))

    message = str(excinfo.value)
    assert message.startswith(f"Cannot open stage {str(path)!r}: ")
    assert "Failed to open layer" in message
    assert "Error in" not in message


def test_open_stage_reports_invalid_files(tmp_path: Path) -> None:
    path = tmp_path / "garbage.usda"
    path.write_text("this is not usd\n", encoding="utf-8")

    with pytest.raises(StageOpenError, match="is not a valid usda layer"):
        open_stage(str(path))


def test_open_stage_reports_a_null_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage_api = SimpleNamespace(
        Open=lambda *_: None, LoadAll="all", LoadNone="none"
    )
    monkeypatch.setattr(runner_module, "Usd", SimpleNamespace(Stage=stage_api))

    with pytest.raises(StageOpenError) as excinfo:
        open_stage("x.usda")

    assert str(excinfo.value) == "Cannot open stage 'x.usda'"


def test_open_stage_rejects_unknown_load_policies(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid load policy 'some'"):
        open_stage(str(tmp_path / "a.usda"), load="some")  # type: ignore[arg-type]


def test_load_none_hides_payload_contents(tmp_path: Path) -> None:
    (tmp_path / "geo.usda").write_text(
        '#usda 1.0\n(defaultPrim = "geo")\n'
        'def Xform "geo"\n{\n    def Mesh "m" {}\n}\n',
        encoding="utf-8",
    )
    root = tmp_path / "root.usda"
    root.write_text(
        '#usda 1.0\ndef Xform "asset" (prepend payload = @./geo.usda@) {}\n',
        encoding="utf-8",
    )

    def paths(load: str) -> list[str]:
        stage = open_stage(str(root), load=load)  # type: ignore[arg-type]
        return [str(prim.GetPath()) for prim in stage.Traverse()]

    assert paths("all") == ["/asset", "/asset/m"]
    # A prim whose payload is unloaded is itself unloaded, so the default
    # traversal skips it along with everything the payload brings in.
    assert paths("none") == []
