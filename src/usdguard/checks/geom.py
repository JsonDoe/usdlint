"""Geometry integrity: primvar sizes and extents."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pxr import Usd, UsdGeom

from usdguard.checks import _options
from usdguard.core import PrimCheck

if TYPE_CHECKING:
    from collections.abc import Iterator

    from usdguard.core import Context, Issue

_SAMPLE_TIMES = ("default", "all")


class PrimvarSizeCheck(PrimCheck):
    """Mesh primvars must have as many elements as their interpolation needs.

    A primvar whose size does not match the mesh topology is ignored or
    misread by renderers and DCCs, typically showing up as scrambled UVs
    or colors. The expected number of elements depends on the
    interpolation: ``constant`` needs 1, ``uniform`` one per face,
    ``vertex`` and ``varying`` one per point, and ``faceVarying`` one
    per face-vertex. Each element holds ``elementSize`` values.

    For indexed primvars, the indices array must have the expected
    number of elements and every index must address an existing element
    of the values array. Values and topology are evaluated at the
    default time; primvars or meshes that only have time samples are not
    checked.

    Example:
        Reported because a ``vertex`` primvar on a 4-point mesh has 2
        values::

            def Mesh "quad"
            {
                point3f[] points = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
                int[] faceVertexCounts = [4]
                int[] faceVertexIndices = [0, 1, 2, 3]
                color3f[] primvars:displayColor = [(1, 0, 0), (0, 1, 0)] (
                    interpolation = "vertex"
                )
            }
    """

    check_id = "geom.primvar_size"
    description = "Mesh primvar sizes match their interpolation and topology."

    def applies_to(self, prim: Usd.Prim) -> bool:
        """Return whether the prim is a mesh."""
        return bool(prim.IsA(UsdGeom.Mesh))

    def check_prim(self, prim: Usd.Prim, context: Context) -> Iterator[Issue]:
        """Report primvars whose size does not match the mesh topology."""
        time = Usd.TimeCode.Default()
        expected = _element_counts(UsdGeom.Mesh(prim), time)
        api = UsdGeom.PrimvarsAPI(prim)
        for primvar in api.GetPrimvarsWithAuthoredValues():
            interpolation = str(primvar.GetInterpolation())
            elements = expected.get(interpolation)
            values = primvar.Get(time)
            if (
                elements is None
                or values is None
                or not primvar.GetTypeName().isArray
            ):
                continue
            name = str(primvar.GetPrimvarName())
            element_size = int(primvar.GetElementSize())
            label = f"Primvar {name!r} ({interpolation})"
            if primvar.IsIndexed():
                indices = primvar.GetIndices(time)
                yield from self._check_indexed(
                    prim, label, values, indices, elements, element_size
                )
            elif len(values) != elements * element_size:
                yield self.issue(
                    f"{label} has {len(values)} values; expected "
                    f"{_describe(elements, element_size)}",
                    prim,
                )

    def _check_indexed(
        self,
        prim: Usd.Prim,
        label: str,
        values: Any,
        indices: Any,
        elements: int,
        element_size: int,
    ) -> Iterator[Issue]:
        if len(indices) != elements:
            yield self.issue(
                f"{label} has {len(indices)} indices; expected {elements}",
                prim,
            )
        if len(values) % element_size:
            yield self.issue(
                f"{label} has {len(values)} values, which is not a multiple "
                f"of its elementSize {element_size}",
                prim,
            )
        available = len(values) // element_size
        invalid = [
            position
            for position, index in enumerate(indices)
            if not 0 <= index < available
        ]
        if invalid:
            first = invalid[0]
            yield self.issue(
                f"{label} has {len(invalid)} out-of-range indices (valid: 0 "
                f"to {available - 1}); first is {indices[first]} at "
                f"position {first}",
                prim,
            )


class ExtentCheck(PrimCheck):
    """Boundable prims must author an extent that matches their geometry.

    Renderers and viewers use ``extent`` for culling and bounding boxes
    without recomputing it. A missing extent makes every bounds query
    expensive; a stale one makes geometry disappear from renders or
    frames the camera on the wrong bounds. The authored extent is
    compared with ``UsdGeomBoundable.ComputeExtentFromPlugins`` at the
    default time; prims whose type has no extent plugin are only checked
    for an authored extent.

    Options:
        tolerance: Largest accepted difference between an authored and a
            computed extent component.
        sample_times: ``"default"`` compares at the default time only;
            ``"all"`` also compares at every authored time sample of
            ``points``, which catches animated geometry with a static
            extent.

    Example:
        Reported because the authored extent misses the point at x=2::

            def Mesh "tri"
            {
                float3[] extent = [(0, 0, 0), (1, 1, 0)]
                point3f[] points = [(0, 0, 0), (2, 0, 0), (0, 1, 0)]
                int[] faceVertexCounts = [3]
                int[] faceVertexIndices = [0, 1, 2]
            }
    """

    check_id = "geom.extent"
    description = "Boundables author an extent that matches their geometry."

    def __init__(
        self, *, tolerance: float = 1e-4, sample_times: str = "default"
    ) -> None:
        self.tolerance = _options.number("tolerance", tolerance)
        self.sample_times = _options.one_of(
            "sample_times", sample_times, _SAMPLE_TIMES
        )

    def applies_to(self, prim: Usd.Prim) -> bool:
        """Return whether the prim is boundable."""
        return bool(prim.IsA(UsdGeom.Boundable))

    def check_prim(self, prim: Usd.Prim, context: Context) -> Iterator[Issue]:
        """Report a missing extent, or one that differs from the geometry."""
        boundable = UsdGeom.Boundable(prim)
        if not boundable.GetExtentAttr().HasAuthoredValue():
            yield self.issue(
                f"{prim.GetTypeName()} has no authored extent", prim
            )
            return
        yield from self._compare(prim, boundable, Usd.TimeCode.Default())
        if self.sample_times == "all" and prim.IsA(UsdGeom.PointBased):
            points = UsdGeom.PointBased(prim).GetPointsAttr()
            for time in points.GetTimeSamples():
                yield from self._compare(prim, boundable, Usd.TimeCode(time))

    def _compare(
        self, prim: Usd.Prim, boundable: Any, time: Any
    ) -> Iterator[Issue]:
        authored = boundable.GetExtentAttr().Get(time)
        computed = UsdGeom.Boundable.ComputeExtentFromPlugins(boundable, time)
        if authored is None or computed is None:
            return
        authored_bounds = _bounds(authored)
        computed_bounds = _bounds(computed)
        if len(authored_bounds) != len(computed_bounds) or any(
            abs(a - c) > self.tolerance
            for a, c in zip(authored_bounds, computed_bounds, strict=True)
        ):
            when = "" if time.IsDefault() else f" at time {time.GetValue():g}"
            yield self.issue(
                f"Authored extent {_format_extent(authored_bounds)} differs "
                f"from the computed extent "
                f"{_format_extent(computed_bounds)}{when}",
                prim,
            )


def _element_counts(mesh: Any, time: Any) -> dict[str, int | None]:
    """Return the expected element count per interpolation of ``mesh``.

    A count is ``None`` when the topology needed to compute it is not
    authored at ``time``.
    """
    points = mesh.GetPointsAttr().Get(time)
    counts = mesh.GetFaceVertexCountsAttr().Get(time)
    indices = mesh.GetFaceVertexIndicesAttr().Get(time)
    n_points = None if points is None else len(points)
    return {
        "constant": 1,
        "uniform": None if counts is None else len(counts),
        "vertex": n_points,
        "varying": n_points,
        "faceVarying": None if indices is None else len(indices),
    }


def _describe(elements: int, element_size: int) -> str:
    if element_size == 1:
        return str(elements)
    return (
        f"{elements * element_size} ({elements} x elementSize {element_size})"
    )


def _bounds(extent: Any) -> tuple[float, ...]:
    """Flatten an extent (two 3D points) to a tuple of floats."""
    return tuple(float(value) for point in extent for value in point)


def _format_extent(bounds: tuple[float, ...]) -> str:
    low = ", ".join(f"{value:g}" for value in bounds[:3])
    high = ", ".join(f"{value:g}" for value in bounds[3:])
    return f"[({low}), ({high})]"
