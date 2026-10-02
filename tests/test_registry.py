"""Tests for check discovery, validation and duplicate detection."""

from __future__ import annotations

import re
import sys
import textwrap
from importlib.metadata import EntryPoint
from typing import TYPE_CHECKING

import pytest

from usdguard import registry as registry_module
from usdguard.core import Context, Issue, PrimCheck, StageCheck
from usdguard.errors import DuplicateCheckError, RegistryError
from usdguard.registry import ENTRY_POINT_GROUP, CheckRegistry

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from pxr import Usd

PLUGIN_MODULE = "usdguard_fake_plugin"

PLUGIN_SOURCE = """
from usdguard.core import StageCheck


class GoodCheck(StageCheck):
    check_id = "fake.good"
    description = "Valid plugin check."

    def check_stage(self, context):
        yield from ()


def not_a_check():
    return None
"""


class AlphaCheck(StageCheck):
    check_id = "test.alpha"
    description = "First test check."

    def check_stage(self, context: Context) -> Iterator[Issue]:
        yield from ()


class BetaCheck(PrimCheck):
    check_id = "test.beta"
    description = "Second test check."

    def check_prim(self, prim: Usd.Prim, context: Context) -> Iterator[Issue]:
        yield from ()


class AlphaTwinCheck(StageCheck):
    check_id = "test.alpha"
    description = "Collides with AlphaCheck."

    def check_stage(self, context: Context) -> Iterator[Issue]:
        yield from ()


def plugin(name: str, value: str) -> EntryPoint:
    return EntryPoint(name=name, value=value, group=ENTRY_POINT_GROUP)


@pytest.fixture
def plugin_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[str]:
    """Make a throwaway plugin module importable; return its name."""
    (tmp_path / f"{PLUGIN_MODULE}.py").write_text(
        textwrap.dedent(PLUGIN_SOURCE), encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    yield PLUGIN_MODULE
    sys.modules.pop(PLUGIN_MODULE, None)


def test_ids_are_sorted_and_import_nothing() -> None:
    registry = CheckRegistry(
        plugins=[plugin("zz.lazy", "not_imported_module:Check")],
        classes=[BetaCheck, AlphaCheck],
    )

    assert registry.ids() == ["test.alpha", "test.beta", "zz.lazy"]
    assert "zz.lazy" in registry
    assert "missing" not in registry
    assert "not_imported_module" not in sys.modules


def test_get_returns_registered_classes() -> None:
    registry = CheckRegistry.from_classes([AlphaCheck, BetaCheck])

    assert registry.get("test.beta") is BetaCheck
    assert registry.load_all() == {
        "test.alpha": AlphaCheck,
        "test.beta": BetaCheck,
    }


def test_unknown_check_suggests_close_matches() -> None:
    registry = CheckRegistry.from_classes([AlphaCheck])

    with pytest.raises(KeyError, match=re.escape("did you mean 'test.alpha'")):
        registry.get("test.alpah")


def test_unknown_check_without_close_match() -> None:
    registry = CheckRegistry.from_classes([AlphaCheck])

    assert registry.unknown_check_message("zzz") == "unknown check 'zzz'"


def test_duplicate_classes_are_rejected() -> None:
    with pytest.raises(DuplicateCheckError, match=re.escape("'test.alpha'")):
        CheckRegistry.from_classes([AlphaCheck, AlphaTwinCheck])


def test_duplicate_entry_points_are_rejected() -> None:
    plugins = [plugin("x.dup", "a_mod:A"), plugin("x.dup", "b_mod:B")]

    with pytest.raises(
        DuplicateCheckError, match="'a_mod:A' and by 'b_mod:B'"
    ):
        CheckRegistry(plugins=plugins)


def test_class_clashing_with_an_entry_point_is_rejected() -> None:
    with pytest.raises(DuplicateCheckError, match="registered twice"):
        CheckRegistry(
            plugins=[plugin("test.alpha", "a_mod:A")], classes=[AlphaCheck]
        )


def test_entry_points_load_lazily_and_once(
    plugin_module: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    loads: list[str] = []
    original_load = EntryPoint.load

    def counting_load(self: EntryPoint) -> object:
        loads.append(self.name)
        return original_load(self)

    monkeypatch.setattr(EntryPoint, "load", counting_load)
    registry = CheckRegistry(
        plugins=[plugin("fake.good", f"{plugin_module}:GoodCheck")]
    )
    assert plugin_module not in sys.modules

    first = registry.get("fake.good")
    second = registry.get("fake.good")

    assert first is second
    assert first.check_id == "fake.good"
    assert loads == ["fake.good"]


def test_entry_point_name_must_equal_check_id(plugin_module: str) -> None:
    registry = CheckRegistry(
        plugins=[plugin("fake.renamed", f"{plugin_module}:GoodCheck")]
    )

    with pytest.raises(RegistryError, match="must equal the check_id"):
        registry.get("fake.renamed")


def test_unimportable_entry_point_raises_registry_error() -> None:
    registry = CheckRegistry(plugins=[plugin("x.y", "no_such_module_xyz:C")])

    with pytest.raises(RegistryError, match=re.escape("check 'x.y' from")):
        registry.get("x.y")


def test_entry_point_must_name_a_check_class(plugin_module: str) -> None:
    registry = CheckRegistry(
        plugins=[plugin("fake.bad", f"{plugin_module}:not_a_check")]
    )

    with pytest.raises(RegistryError, match="not a subclass of StageCheck"):
        registry.get("fake.bad")


def test_abstract_check_classes_are_rejected() -> None:
    class Abstract(PrimCheck):
        check_id = "test.abstract"
        description = "Does not implement check_prim."

    with pytest.raises(RegistryError, match="abstract method"):
        CheckRegistry.from_classes([Abstract])


@pytest.mark.parametrize(
    ("attributes", "message"),
    [
        ({"description": "Has no id."}, "non-empty string check_id"),
        ({"check_id": "", "description": "Empty id."}, "check_id"),
        ({"check_id": "test.nodesc"}, "non-empty string description"),
    ],
)
def test_check_classes_need_an_id_and_a_description(
    attributes: dict[str, str], message: str
) -> None:
    def check_stage(self: StageCheck, context: Context) -> Iterator[Issue]:
        yield from ()

    cls = type(
        "Incomplete", (StageCheck,), {**attributes, "check_stage": check_stage}
    )

    with pytest.raises(RegistryError, match=message):
        CheckRegistry.from_classes([cls])


def test_default_registry_reads_the_installed_entry_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    groups: list[str] = []

    def fake_entry_points(*, group: str) -> list[EntryPoint]:
        groups.append(group)
        return [plugin("fake.installed", "some_module:Check")]

    monkeypatch.setattr(registry_module, "entry_points", fake_entry_points)

    assert CheckRegistry().ids() == ["fake.installed"]
    assert groups == ["usdguard.checks"]
