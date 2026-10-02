"""Model hierarchy."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pxr import Kind, Usd

from usdguard.core import PrimCheck

if TYPE_CHECKING:
    from collections.abc import Iterator

    from usdguard.core import Context, Issue


class ModelHierarchyCheck(PrimCheck):
    """Prims with a model kind must belong to a valid model hierarchy.

    USD only treats a prim as a model when every ancestor is a model
    group (``group`` or ``assembly``). A prim that authors a model kind
    (``component``, ``group``, ``assembly`` or a custom model kind) but
    breaks that rule is silently not a model: model traversals, payload
    tooling and asset resolution that rely on kinds skip it. This
    happens when a component is nested under another component, or when
    an ancestor in the group chain has no kind.

    Example:
        ``leg`` is reported because a component cannot contain models,
        and ``lamp`` because its parent ``loose`` is not a group::

            def Xform "set" (kind = "assembly")
            {
                def Xform "chair" (kind = "component")
                {
                    def Xform "leg" (kind = "component") {}
                }
                def Xform "loose"
                {
                    def Xform "lamp" (kind = "component") {}
                }
            }
    """

    check_id = "model.hierarchy"
    description = "Prims with a model kind form a contiguous model hierarchy."

    def applies_to(self, prim: Usd.Prim) -> bool:
        """Return whether the prim authors a model kind."""
        kind = Usd.ModelAPI(prim).GetKind()
        return bool(kind) and bool(Kind.Registry.IsA(kind, Kind.Tokens.model))

    def check_prim(self, prim: Usd.Prim, context: Context) -> Iterator[Issue]:
        """Report the prim if USD does not consider it a model."""
        if prim.IsModel():
            return
        kind = str(Usd.ModelAPI(prim).GetKind())
        yield self.issue(
            f"Prim has kind {kind!r} but is not a model: {_reason(prim)}",
            prim,
        )


def _reason(prim: Usd.Prim) -> str:
    """Explain why the parent of ``prim`` breaks the model hierarchy."""
    parent = prim.GetParent()
    path = str(parent.GetPath())
    kind = str(Usd.ModelAPI(parent).GetKind())
    if parent.IsModel():
        return f"its parent {path} is a {kind}, which cannot contain models"
    if kind and Kind.Registry.IsA(kind, Kind.Tokens.group):
        return f"its parent group {path} is itself outside the hierarchy"
    described = f"kind {kind!r}" if kind else "no kind"
    return f"its parent {path} has {described} instead of a group kind"
