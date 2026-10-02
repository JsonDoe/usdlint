"""Naming conventions."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from usdguard.checks import _options
from usdguard.core import PrimCheck

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from pxr import Usd

    from usdguard.core import Context, Issue


class PrimNameCheck(PrimCheck):
    """Prim names must follow the naming convention of their type.

    Consistent names keep scenes readable, keep tools that look prims up
    by name working, and catch default names such as ``Mesh1`` left
    behind by DCC exports.

    Options:
        rules: Mapping of prim type name (``Mesh``, ``Xform``...) to a
            regular expression that the whole prim name must match.
            Prims of other types are not checked. In TOML profiles,
            write the expressions as single-quoted literal strings so
            that backslashes are kept as they are.

    Example:
        With ``rules = {Mesh = '^[a-z][a-zA-Z0-9]*_GEO$'}``, this prim
        is reported because its name should look like ``body_GEO``::

            def Mesh "Body" {}
    """

    check_id = "naming.prim_name"
    description = "Prim names match a regular expression per prim type."

    def __init__(self, *, rules: Mapping[str, str] | None = None) -> None:
        patterns = _options.string_mapping("rules", rules or {})
        self.rules: dict[str, re.Pattern[str]] = {
            type_name: _compile(type_name, pattern)
            for type_name, pattern in patterns.items()
        }

    def applies_to(self, prim: Usd.Prim) -> bool:
        """Return whether a rule exists for the prim's type."""
        return str(prim.GetTypeName()) in self.rules

    def check_prim(self, prim: Usd.Prim, context: Context) -> Iterator[Issue]:
        """Report the prim if its name does not match its type's rule."""
        type_name = str(prim.GetTypeName())
        pattern = self.rules[type_name]
        name = str(prim.GetName())
        if pattern.fullmatch(name) is None:
            yield self.issue(
                f"{type_name} name {name!r} does not match "
                f"{pattern.pattern!r}",
                prim,
            )


def _compile(type_name: str, pattern: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern)
    except re.error as exc:
        msg = (
            f"invalid regular expression for {type_name!r}: "
            f"{pattern!r} ({exc})"
        )
        raise ValueError(msg) from exc
