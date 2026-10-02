"""The built-in checks are registered and usable with default options."""

from __future__ import annotations

import pytest

from usdguard.core import Check
from usdguard.registry import CheckRegistry

BUILTIN_CHECKS = [
    "compliance.usdchecker",
    "deps.absolute_arc_path",
    "deps.absolute_asset_attr",
    "deps.unresolved",
    "geom.extent",
    "geom.primvar_size",
    "model.hierarchy",
    "naming.prim_name",
    "shading.material_binding",
    "stage.metadata",
]


def test_builtin_checks_are_registered_as_entry_points() -> None:
    assert set(BUILTIN_CHECKS) <= set(CheckRegistry().ids())


@pytest.mark.parametrize("check_id", BUILTIN_CHECKS)
def test_builtin_checks_are_documented_and_have_valid_defaults(
    check_id: str,
) -> None:
    cls = CheckRegistry().get(check_id)

    assert isinstance(cls(), Check)
    assert cls.check_id == check_id
    assert cls.__doc__
    assert "Example:" in cls.__doc__
