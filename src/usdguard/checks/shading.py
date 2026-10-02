"""Shading: material bindings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pxr import Usd, UsdGeom, UsdShade

from usdguard.core import StageCheck

if TYPE_CHECKING:
    from collections.abc import Iterator

    from usdguard.core import Context, Issue

_RENDERABLE_PURPOSES = frozenset({"default", "render"})


class MaterialBindingCheck(StageCheck):
    """Renderable gprims must have a bound material.

    A gprim whose computed purpose is ``default`` or ``render`` ends up
    in final renders; without a material it renders with the renderer's
    fallback shading, which is easy to miss in review. ``proxy`` and
    ``guide`` gprims are ignored.

    Bindings are resolved for the ``allPurpose`` material purpose with
    the batched ``UsdShadeMaterialBindingAPI.ComputeBoundMaterials``,
    which honours inherited and collection-based bindings. Instance
    proxies are included, so a binding authored on an instance applies
    to its prototype's gprims, and issues name the instance proxy
    paths. The resolved bindings are stored in ``context.cache`` under
    this check's id, as a mapping of gprim path to material path (empty
    when unbound), for other checks to reuse.

    Example:
        Reported because nothing binds a material to the mesh::

            def Xform "chair"
            {
                def Mesh "seat" {}
            }
    """

    check_id = "shading.material_binding"
    description = "Renderable gprims have a bound material."

    def check_stage(self, context: Context) -> Iterator[Issue]:
        """Report renderable gprims without a bound material."""
        predicate = Usd.TraverseInstanceProxies()
        gprims = [
            prim
            for prim in context.stage.Traverse(predicate)
            if prim.IsA(UsdGeom.Gprim)
            and UsdGeom.Imageable(prim).ComputePurpose()
            in _RENDERABLE_PURPOSES
        ]
        if not gprims:
            context.cache[self.check_id] = {}
            return
        materials, _relationships = (
            UsdShade.MaterialBindingAPI.ComputeBoundMaterials(
                gprims, UsdShade.Tokens.allPurpose
            )
        )
        bound: dict[str, str] = {}
        for prim, material in zip(gprims, materials, strict=True):
            bound[str(prim.GetPath())] = (
                str(material.GetPath()) if material else ""
            )
            if not material:
                yield self.issue(
                    f"{prim.GetTypeName()} has no bound material", prim
                )
        context.cache[self.check_id] = bound
