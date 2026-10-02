"""Tests for geom.primvar_size and geom.extent."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from usdguard.checks.geom import ExtentCheck, PrimvarSizeCheck
from usdguard.runner import open_stage, run

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from pxr import Usd

    StageFactory = Callable[[str], Usd.Stage]

QUAD_TOPOLOGY = """
        int[] faceVertexCounts = [4]
        int[] faceVertexIndices = [0, 1, 2, 3]
        point3f[] points = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
"""


def quad(primvars: str, extent: str = "") -> str:
    return f'def Mesh "quad"\n{{\n{QUAD_TOPOLOGY}{extent}\n{primvars}\n}}\n'


def messages(stage: Usd.Stage, check: object) -> list[str]:
    report = run(stage, [check])  # type: ignore[list-item]
    return [issue.message for issue in report.issues]


def test_primvars_matching_every_interpolation_pass(
    make_stage: StageFactory,
) -> None:
    stage = make_stage(
        quad(
            """
            float primvars:constant = 1 (interpolation = "constant")
            float[] primvars:const_array = [1] (interpolation = "constant")
            float[] primvars:uniform = [1] (interpolation = "uniform")
            float[] primvars:vertex = [1, 2, 3, 4] (interpolation = "vertex")
            float[] primvars:varying = [1, 2, 3, 4] (interpolation = "varying")
            float[] primvars:fv = [1, 2, 3, 4] (interpolation = "faceVarying")
            float[] primvars:pairs = [1, 2, 3, 4, 5, 6, 7, 8] (
                interpolation = "vertex"
                elementSize = 2
            )
            texCoord2f[] primvars:st = [(0, 0), (1, 1)] (
                interpolation = "faceVarying"
            )
            int[] primvars:st:indices = [0, 1, 1, 0]
            """
        )
    )

    assert messages(stage, PrimvarSizeCheck()) == []


def test_primvar_sizes_not_matching_topology_are_reported(
    make_stage: StageFactory,
) -> None:
    stage = make_stage(
        quad(
            """
            color3f[] primvars:displayColor = [(1, 0, 0), (0, 1, 0)] (
                interpolation = "vertex"
            )
            float[] primvars:uniform = [1, 2] (interpolation = "uniform")
            float[] primvars:pairs = [1, 2, 3, 4] (
                interpolation = "vertex"
                elementSize = 2
            )
            """
        )
    )

    assert messages(stage, PrimvarSizeCheck()) == [
        "Primvar 'displayColor' (vertex) has 2 values; expected 4",
        "Primvar 'pairs' (vertex) has 4 values; expected 8 "
        "(4 x elementSize 2)",
        "Primvar 'uniform' (uniform) has 2 values; expected 1",
    ]


def test_indexed_primvars_with_bad_indices_are_reported(
    make_stage: StageFactory,
) -> None:
    stage = make_stage(
        quad(
            """
            texCoord2f[] primvars:st = [(0, 0), (1, 0), (1, 1)] (
                interpolation = "faceVarying"
            )
            int[] primvars:st:indices = [0, 1, 2, 5]
            float[] primvars:short = [1, 2] (interpolation = "vertex")
            int[] primvars:short:indices = [0, -1, 1]
            float[] primvars:odd = [1, 2, 3] (
                interpolation = "constant"
                elementSize = 2
            )
            int[] primvars:odd:indices = [0]
            """
        )
    )

    assert messages(stage, PrimvarSizeCheck()) == [
        "Primvar 'odd' (constant) has 3 values, which is not a multiple of "
        "its elementSize 2",
        "Primvar 'short' (vertex) has 1 out-of-range indices (valid: 0 to 1); "
        "first is -1 at position 1",
        "Primvar 'short' (vertex) has 3 indices; expected 4",
        "Primvar 'st' (faceVarying) has 1 out-of-range indices (valid: 0 to "
        "2); first is 5 at position 3",
    ]


def test_primvars_are_skipped_without_topology_or_values(
    make_stage: StageFactory,
) -> None:
    stage = make_stage(
        """
        def Mesh "animated"
        {
            point3f[] points.timeSamples = {1: [(0, 0, 0)]}
            float[] primvars:vertex = [1, 2] (interpolation = "vertex")
            float[] primvars:sampled (interpolation = "constant")
            float[] primvars:sampled.timeSamples = {1: [1]}
            float[] primvars:custom = [1] (interpolation = "instance")
        }
        def Xform "not_a_mesh"
        {
            float[] primvars:vertex = [1, 2] (interpolation = "vertex")
        }
        """
    )

    assert messages(stage, PrimvarSizeCheck()) == []


def test_matching_extent_passes(make_stage: StageFactory) -> None:
    extent = "float3[] extent = [(0, 0, 0), (1, 1, 0)]"
    stage = make_stage(quad("", extent))

    assert messages(stage, ExtentCheck()) == []


def test_missing_extent_is_reported(make_stage: StageFactory) -> None:
    stage = make_stage(quad(""))

    assert messages(stage, ExtentCheck()) == ["Mesh has no authored extent"]


def test_stale_extent_is_reported(make_stage: StageFactory) -> None:
    extent = "float3[] extent = [(0, 0, 0), (0.5, 1, 0)]"
    stage = make_stage(quad("", extent))

    assert messages(stage, ExtentCheck()) == [
        "Authored extent [(0, 0, 0), (0.5, 1, 0)] differs from the computed "
        "extent [(0, 0, 0), (1, 1, 0)]"
    ]


def test_extent_is_not_compared_when_it_cannot_be_computed(
    make_stage: StageFactory,
) -> None:
    stage = make_stage(
        """
        def Mesh "no_points"
        {
            float3[] extent = [(0, 0, 0), (1, 1, 1)]
        }
        """
    )

    assert messages(stage, ExtentCheck()) == []


def test_malformed_extent_is_reported(make_stage: StageFactory) -> None:
    stage = make_stage(quad("", "float3[] extent = [(0, 0, 0)]"))

    assert messages(stage, ExtentCheck()) == [
        "Authored extent [(0, 0, 0), ()] differs from the computed extent "
        "[(0, 0, 0), (1, 1, 0)]"
    ]


def test_tolerance_is_configurable(make_stage: StageFactory) -> None:
    extent = "float3[] extent = [(0, 0, 0), (1.001, 1, 0)]"
    stage = make_stage(quad("", extent))

    assert len(messages(stage, ExtentCheck())) == 1
    assert messages(stage, ExtentCheck(tolerance=0.01)) == []


def test_extent_of_implicit_shapes_is_computed(
    make_stage: StageFactory,
) -> None:
    stage = make_stage(
        """
        def Cube "box"
        {
            double size = 2
            float3[] extent = [(-1, -1, -1), (1, 1, 1)]
        }
        def Sphere "ball"
        {
            double radius = 1
            float3[] extent = [(-2, -2, -2), (2, 2, 2)]
        }
        """
    )

    assert messages(stage, ExtentCheck()) == [
        "Authored extent [(-2, -2, -2), (2, 2, 2)] differs from the computed "
        "extent [(-1, -1, -1), (1, 1, 1)]"
    ]


ANIMATED = """
def Mesh "tri"
{
    float3[] extent = [(0, 0, 0), (1, 1, 0)]
    int[] faceVertexCounts = [3]
    int[] faceVertexIndices = [0, 1, 2]
    point3f[] points = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    point3f[] points.timeSamples = {
        1: [(0, 0, 0), (1, 0, 0), (0, 1, 0)],
        2: [(0, 0, 0), (3, 0, 0), (0, 1, 0)],
    }
}
"""


def test_time_samples_are_ignored_by_default(make_stage: StageFactory) -> None:
    assert messages(make_stage(ANIMATED), ExtentCheck()) == []


def test_all_point_samples_are_compared_on_request(
    make_stage: StageFactory,
) -> None:
    check = ExtentCheck(sample_times="all")

    assert messages(make_stage(ANIMATED), check) == [
        "Authored extent [(0, 0, 0), (1, 1, 0)] differs from the computed "
        "extent [(0, 0, 0), (3, 1, 0)] at time 2"
    ]


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"tolerance": -1}, "tolerance must be a number >= 0"),
        ({"tolerance": "0.1"}, "tolerance must be a number"),
        ({"sample_times": "some"}, "sample_times must be one of"),
    ],
)
def test_invalid_extent_options_are_rejected(
    options: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ExtentCheck(**options)  # type: ignore[arg-type]


def test_geometry_behind_unloaded_payloads_is_not_checked(
    data_dir: Path,
) -> None:
    path = str(data_dir / "payload" / "asset.usda")
    checks = [PrimvarSizeCheck(), ExtentCheck()]

    loaded = run(open_stage(path, load="all"), checks)
    unloaded = run(open_stage(path, load="none"), checks)

    assert [issue.check_id for issue in loaded.issues] == [
        "geom.extent",
        "geom.primvar_size",
    ]
    assert unloaded.issues == ()
