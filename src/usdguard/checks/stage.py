"""Stage-level metadata."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from pxr import UsdGeom

from usdguard.checks import _options
from usdguard.core import StageCheck

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pxr import Usd

    from usdguard.core import Context, Issue

_UP_AXES = ("Y", "Z")


class StageMetadataCheck(StageCheck):
    """The stage must author its up axis, linear unit and default prim.

    ``upAxis`` and ``metersPerUnit`` have fallback values, so a layer
    that omits them silently takes whatever the consuming application
    assumes, and assets end up rotated or scaled by 100. ``defaultPrim``
    is the prim that a reference or payload without a prim path targets;
    without it, referencing the asset fails.

    Options:
        up_axis: Required ``upAxis``, ``"Y"`` or ``"Z"``. ``None``
            skips the test.
        meters_per_unit: Required ``metersPerUnit``, compared with
            ``math.isclose``. ``None`` skips the test.
        require_default_prim: Whether ``defaultPrim`` must be authored
            and name an existing prim.

    Example:
        This layer is reported three times: no ``upAxis``, no
        ``metersPerUnit`` and no ``defaultPrim``::

            #usda 1.0
            def Xform "asset" {}
    """

    check_id = "stage.metadata"
    description = "The stage authors upAxis, metersPerUnit and defaultPrim."

    def __init__(
        self,
        *,
        up_axis: str | None = "Y",
        meters_per_unit: float | None = 0.01,
        require_default_prim: bool = True,
    ) -> None:
        self.up_axis = (
            None
            if up_axis is None
            else _options.one_of("up_axis", up_axis, _UP_AXES)
        )
        self.meters_per_unit = (
            None
            if meters_per_unit is None
            else _options.positive_number("meters_per_unit", meters_per_unit)
        )
        self.require_default_prim = _options.boolean(
            "require_default_prim", require_default_prim
        )

    def check_stage(self, context: Context) -> Iterator[Issue]:
        """Report missing or unexpected stage metadata."""
        stage = context.stage
        if self.up_axis is not None:
            yield from self._check_up_axis(stage, self.up_axis)
        if self.meters_per_unit is not None:
            yield from self._check_meters_per_unit(stage, self.meters_per_unit)
        if self.require_default_prim:
            yield from self._check_default_prim(stage)

    def _check_up_axis(
        self, stage: Usd.Stage, expected: str
    ) -> Iterator[Issue]:
        if not stage.HasAuthoredMetadata(UsdGeom.Tokens.upAxis):
            yield self.issue(f"upAxis is not authored; expected {expected!r}")
            return
        actual = str(UsdGeom.GetStageUpAxis(stage))
        if actual != expected:
            yield self.issue(f"upAxis is {actual!r}; expected {expected!r}")

    def _check_meters_per_unit(
        self, stage: Usd.Stage, expected: float
    ) -> Iterator[Issue]:
        if not stage.HasAuthoredMetadata(UsdGeom.Tokens.metersPerUnit):
            yield self.issue(
                f"metersPerUnit is not authored; expected {expected:g}"
            )
            return
        actual = float(UsdGeom.GetStageMetersPerUnit(stage))
        if not math.isclose(actual, expected):
            yield self.issue(
                f"metersPerUnit is {actual:g}; expected {expected:g}"
            )

    def _check_default_prim(self, stage: Usd.Stage) -> Iterator[Issue]:
        if not stage.HasDefaultPrim():
            yield self.issue("defaultPrim is not authored")
        elif not stage.GetDefaultPrim():
            name = str(stage.GetRootLayer().defaultPrim)
            yield self.issue(
                f"defaultPrim {name!r} does not name an existing prim"
            )
