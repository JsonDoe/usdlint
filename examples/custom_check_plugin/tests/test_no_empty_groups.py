"""Tests for example.no_empty_groups."""

from __future__ import annotations

import pytest
from pxr import Usd, UsdGeom
from usdguard_example_plugin.checks import NoEmptyGroupsCheck

from usdguard import CheckRegistry, Severity, run


def make_stage() -> Usd.Stage:
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/chair")
    UsdGeom.Mesh.Define(stage, "/chair/seat")
    UsdGeom.Xform.Define(stage, "/chair/old_geo")
    UsdGeom.Scope.Define(stage, "/looks")
    return stage


def test_empty_groups_are_reported() -> None:
    report = run(make_stage(), [NoEmptyGroupsCheck()])

    assert [(i.prim_path, i.message) for i in report.issues] == [
        ("/chair/old_geo", "Xform has no children"),
        ("/looks", "Scope has no children"),
    ]
    assert {issue.severity for issue in report.issues} == {Severity.WARNING}


def test_group_types_are_configurable() -> None:
    report = run(make_stage(), [NoEmptyGroupsCheck(types=["Scope"])])

    assert [issue.prim_path for issue in report.issues] == ["/looks"]


def test_invalid_types_are_rejected() -> None:
    with pytest.raises(ValueError, match="types must be a list"):
        NoEmptyGroupsCheck(types="Xform")


def test_plugin_is_discovered_through_its_entry_point() -> None:
    assert CheckRegistry().get("example.no_empty_groups") is NoEmptyGroupsCheck
