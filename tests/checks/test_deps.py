"""Tests for the deps.* checks and the absolute path rule."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pxr import Usd

from usdguard.checks.deps import (
    AbsoluteArcPathCheck,
    AbsoluteAssetAttrCheck,
    UnresolvedDependencyCheck,
    is_absolute_path,
)
from usdguard.core import Severity
from usdguard.runner import run

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    StageFactory = Callable[[str], Usd.Stage]


@pytest.mark.parametrize(
    "path",
    [
        "/mnt/assets/chair.usda",
        "C:/assets/chair.usda",
        "C:\\assets\\chair.usda",
        "d:\\textures\\wood.png",
        "\\\\server\\share\\chair.usda",
        "//server/share/chair.usda",
        "\\assets\\chair.usda",
        "file:///C:/assets/chair.usda",
        "FILE:/mnt/chair.usda",
    ],
)
def test_absolute_paths_are_detected_on_every_platform(path: str) -> None:
    assert is_absolute_path(path)


@pytest.mark.parametrize(
    "path",
    [
        "chair.usda",
        "./chair.usda",
        "../shared/chair.usda",
        "textures\\wood.png",
        "C:relative.usda",
        "omniverse://server/chair.usda",
        "",
    ],
)
def test_relative_and_resolver_paths_are_not_absolute(path: str) -> None:
    assert not is_absolute_path(path)


def test_relative_arcs_pass(data_dir: Path) -> None:
    stage = Usd.Stage.Open(str(data_dir / "deps" / "relative.usda"))

    assert run(stage, [AbsoluteArcPathCheck()]).issues == ()


def test_absolute_arcs_of_both_platforms_are_reported(data_dir: Path) -> None:
    stage = Usd.Stage.Open(str(data_dir / "deps" / "absolute.usda"))
    layer = stage.GetRootLayer().identifier

    report = run(stage, [AbsoluteArcPathCheck()])

    assert [(i.message, i.layer) for i in report.issues] == [
        (
            "Composition arc uses absolute path "
            "'/mnt/assets/shared/overrides.usda'",
            layer,
        ),
        (
            "Composition arc uses absolute path 'C:/assets/chair/chair.usda'",
            layer,
        ),
    ]


def test_anonymous_layers_are_not_inspected(make_stage: StageFactory) -> None:
    stage = make_stage('def Xform "a" (references = @/abs/a.usda@) {}')

    assert run(stage, [AbsoluteArcPathCheck()]).issues == ()


ASSET_SCENE = """
def Shader "albedo"
{
    asset inputs:file = @/textures/albedo.png@
    asset inputs:relative = @./textures/albedo.png@
    asset inputs:animated.timeSamples = {
        1: @./frame1.png@,
        2: @D:/frames/frame2.png@,
    }
    asset[] inputs:layers = [@./a.png@, @C:/b.png@]
    string notAnAsset = "/textures/not_an_asset.png"
}
"""


def test_absolute_asset_values_are_reported(make_stage: StageFactory) -> None:
    report = run(make_stage(ASSET_SCENE), [AbsoluteAssetAttrCheck()])

    assert [(i.prim_path, i.message) for i in report.issues] == [
        (
            "/albedo",
            "Attribute 'inputs:animated' uses absolute asset path "
            "'D:/frames/frame2.png' at time 2",
        ),
        (
            "/albedo",
            "Attribute 'inputs:file' uses absolute asset path "
            "'/textures/albedo.png'",
        ),
        (
            "/albedo",
            "Attribute 'inputs:layers'[1] uses absolute asset path 'C:/b.png'",
        ),
    ]


def test_relative_asset_values_pass(make_stage: StageFactory) -> None:
    stage = make_stage(
        """
        def Shader "albedo"
        {
            asset inputs:file = @./textures/albedo.png@
            asset[] inputs:layers = [@a.png@]
        }
        """
    )

    assert run(stage, [AbsoluteAssetAttrCheck()]).issues == ()


def test_resolving_dependencies_pass(data_dir: Path) -> None:
    stage = Usd.Stage.Open(str(data_dir / "deps" / "relative.usda"))

    assert run(stage, [UnresolvedDependencyCheck()]).issues == ()


def test_unresolved_dependencies_are_reported(data_dir: Path) -> None:
    stage = Usd.Stage.Open(str(data_dir / "deps" / "missing.usda"))

    report = run(stage, [UnresolvedDependencyCheck()])

    messages = [issue.message for issue in report.issues]
    assert len(messages) == 2
    assert messages[0].startswith("Unresolved dependency '")
    assert messages[0].endswith("deps/does_not_exist.usda'")
    assert messages[1].endswith("deps/textures/missing.png'")


def test_in_memory_stages_skip_resolution_with_a_note(
    make_stage: StageFactory,
) -> None:
    stage = make_stage('def Xform "a" (references = @./missing.usda@) {}')

    report = run(stage, [UnresolvedDependencyCheck()])

    (issue,) = report.issues
    assert issue.severity is Severity.INFO
    assert "anonymous" in issue.message
    assert report.exit_code == 0
