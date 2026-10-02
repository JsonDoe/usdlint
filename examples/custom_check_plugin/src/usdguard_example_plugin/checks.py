"""Checks provided by the example plugin."""

from __future__ import annotations

from typing import TYPE_CHECKING

from usdguard import Context, Issue, PrimCheck, Severity

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from pxr import Usd


class NoEmptyGroupsCheck(PrimCheck):
    """Grouping prims must not be empty.

    Empty ``Xform`` and ``Scope`` prims are usually leftovers of deleted
    geometry. They clutter outliners and scene graphs and cost a little
    at every traversal.

    Options:
        types: Prim type names treated as groups.

    Example:
        Reported because ``old_geo`` has no children::

            def Xform "chair"
            {
                def Xform "old_geo" {}
            }
    """

    check_id = "example.no_empty_groups"
    description = "Xform and Scope prims have at least one child."
    severity = Severity.WARNING

    def __init__(self, *, types: Sequence[str] = ("Xform", "Scope")) -> None:
        if isinstance(types, str) or not all(
            isinstance(name, str) for name in types
        ):
            msg = f"types must be a list of prim type names, not {types!r}"
            raise ValueError(msg)
        self.types = frozenset(types)

    def applies_to(self, prim: Usd.Prim) -> bool:
        """Return whether the prim is one of the group types."""
        return str(prim.GetTypeName()) in self.types

    def check_prim(self, prim: Usd.Prim, context: Context) -> Iterator[Issue]:
        """Report the prim when it has no children."""
        if not prim.GetChildren():
            yield self.issue(f"{prim.GetTypeName()} has no children", prim)
