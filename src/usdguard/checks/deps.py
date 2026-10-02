"""Dependencies: composition arcs, asset paths and their resolution."""

from __future__ import annotations

import ntpath
import posixpath
from typing import TYPE_CHECKING, Any

from pxr import Sdf, Usd, UsdUtils

from usdguard.core import PrimCheck, Severity, StageCheck

if TYPE_CHECKING:
    from collections.abc import Iterator

    from usdguard.core import Context, Issue


def is_absolute_path(path: str) -> bool:
    r"""Return whether ``path`` is absolute on POSIX or on Windows.

    The answer does not depend on the platform running the check, so a
    Windows path authored on one machine is caught on a Linux farm and
    the other way round. A path is absolute if :func:`posixpath.isabs`
    or :func:`ntpath.isabs` says so, if it starts with a backslash
    (Windows root-relative paths such as ``\\assets\\a.usda``, which
    Python 3.13 no longer reports as absolute but which still depend on
    the current drive), or if it is a ``file:`` URL.

    Args:
        path: Asset path as authored.
    """
    return (
        posixpath.isabs(path)
        or ntpath.isabs(path)
        or path.startswith("\\")
        or path[:5].lower() == "file:"
    )


class AbsoluteArcPathCheck(StageCheck):
    """Composition arcs must use relative or search paths.

    Sublayers, references and payloads that point to absolute paths tie
    an asset to one machine, drive or mount point: the asset breaks as
    soon as it moves, is shipped to a vendor or is opened on another
    operating system. Every used, non-anonymous layer is inspected and
    the issue names the layer that authors the arc.

    Example:
        Both arcs are reported, whatever the platform::

            def Xform "chair" (
                references = @C:/assets/chair.usda@
                payload = @/mnt/assets/chair_geo.usda@
            ) {}
    """

    check_id = "deps.absolute_arc_path"
    description = "Sublayers, references and payloads use relative paths."

    def check_stage(self, context: Context) -> Iterator[Issue]:
        """Report absolute asset paths in the composition arcs of layers."""
        for layer in context.stage.GetUsedLayers():
            if layer.anonymous:
                continue
            for path in layer.GetCompositionAssetDependencies():
                if is_absolute_path(path):
                    yield self.issue(
                        f"Composition arc uses absolute path {path!r}",
                        layer=str(layer.identifier),
                    )


class AbsoluteAssetAttrCheck(PrimCheck):
    """Asset-valued attributes must use relative or search paths.

    Texture files, volume files and other asset attributes with absolute
    paths break as soon as the asset moves, for the same reasons as
    absolute composition arcs. Authored default values and every time
    sample are inspected, including each element of asset arrays.

    Example:
        Reported because the texture path is absolute::

            def Shader "albedo"
            {
                asset inputs:file = @D:/textures/albedo.png@
            }
    """

    check_id = "deps.absolute_asset_attr"
    description = "Asset-valued attributes use relative paths."

    def check_prim(self, prim: Usd.Prim, context: Context) -> Iterator[Issue]:
        """Report absolute paths in the prim's asset attributes."""
        asset_types = (Sdf.ValueTypeNames.Asset, Sdf.ValueTypeNames.AssetArray)
        for attribute in prim.GetAuthoredAttributes():
            if attribute.GetTypeName() not in asset_types:
                continue
            name = str(attribute.GetName())
            default = attribute.Get(Usd.TimeCode.Default())
            yield from self._report(prim, name, default, "")
            for time in attribute.GetTimeSamples():
                value = attribute.Get(time)
                yield from self._report(
                    prim, name, value, f" at time {time:g}"
                )

    def _report(
        self, prim: Usd.Prim, name: str, value: Any, when: str
    ) -> Iterator[Issue]:
        for label, path in _asset_paths(name, value):
            if is_absolute_path(path):
                yield self.issue(
                    f"{label} uses absolute asset path {path!r}{when}", prim
                )


def _asset_paths(name: str, value: Any) -> Iterator[tuple[str, str]]:
    """Yield ``(label, path)`` for an asset or asset array value."""
    if value is None:
        return
    if isinstance(value, Sdf.AssetPath):
        yield f"Attribute {name!r}", str(value.path)
        return
    for index, item in enumerate(value):
        yield f"Attribute {name!r}[{index}]", str(item.path)


class UnresolvedDependencyCheck(StageCheck):
    """Every layer, reference, payload and asset path must resolve.

    Dependencies are computed recursively from the root layer with
    ``UsdUtils.ComputeAllDependencies``, across all variants and
    including asset-valued attributes, so missing textures are caught as
    well as missing layers. Unresolved paths are reported as anchored by
    USD. In-memory stages have no file to start from: they get a single
    informational issue and are skipped.

    Example:
        Reported if ``./chair_geo.usda`` does not exist next to the
        layer::

            def Xform "chair" (payload = @./chair_geo.usda@) {}
    """

    check_id = "deps.unresolved"
    description = "Every layer and asset dependency resolves."

    def check_stage(self, context: Context) -> Iterator[Issue]:
        """Report each dependency of the root layer that does not resolve."""
        root = context.stage.GetRootLayer()
        if root.anonymous:
            yield self.issue(
                "Root layer is anonymous (in-memory stage); dependency "
                "resolution was skipped",
                severity=Severity.INFO,
            )
            return
        root_path = str(root.realPath or root.identifier)
        _layers, _assets, unresolved = UsdUtils.ComputeAllDependencies(
            Sdf.AssetPath(root_path)
        )
        for path in sorted({str(path) for path in unresolved}):
            yield self.issue(f"Unresolved dependency {path!r}")
