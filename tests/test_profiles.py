"""Tests for profile resolution, parsing and check instantiation."""

from __future__ import annotations

import os
import textwrap
from typing import TYPE_CHECKING

import pytest

from usdguard.checks.naming import PrimNameCheck
from usdguard.checks.stage import StageMetadataCheck
from usdguard.core import Severity
from usdguard.errors import ConfigError
from usdguard.profiles import (
    PROFILE_PATH_ENV,
    Profile,
    build_checks,
    builtin_profiles,
    load_profile,
)
from usdguard.registry import CheckRegistry

if TYPE_CHECKING:
    from pathlib import Path

DEFAULT_CHECKS = [
    "stage.metadata",
    "naming.prim_name",
    "deps.absolute_arc_path",
    "deps.absolute_asset_attr",
    "deps.unresolved",
    "shading.material_binding",
    "model.hierarchy",
    "geom.primvar_size",
    "geom.extent",
    "compliance.usdchecker",
]


@pytest.fixture
def registry() -> CheckRegistry:
    return CheckRegistry.from_classes([PrimNameCheck, StageMetadataCheck])


def write(directory: Path, name: str, text: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


def test_builtin_default_profile_loads() -> None:
    profile = load_profile("default", environ={})

    assert profile.name == "default"
    assert profile.fail_on is Severity.ERROR
    assert profile.load == "all"
    assert list(profile.checks) == DEFAULT_CHECKS
    assert profile.severity["naming.prim_name"] is Severity.WARNING
    assert profile.options["naming.prim_name"]["rules"]["Mesh"] == (
        "^[a-z][a-zA-Z0-9]*_GEO$"
    )


def test_builtin_profiles_are_listed() -> None:
    assert builtin_profiles() == ["default"]


def test_default_profile_builds_every_builtin_check() -> None:
    checks = build_checks(load_profile(environ={}), CheckRegistry())

    assert [check.check_id for check in checks] == DEFAULT_CHECKS


def test_existing_files_are_used_directly(tmp_path: Path) -> None:
    path = write(tmp_path, "studio.toml", 'fail_on = "warning"\nload = "none"')

    profile = load_profile(str(path), environ={})

    assert (profile.name, profile.source) == ("studio", str(path))
    assert (profile.fail_on, profile.load) == (Severity.WARNING, "none")


def test_names_are_searched_in_the_profile_path_first(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    write(first, "studio.toml", 'fail_on = "warning"')
    write(second, "studio.toml", 'fail_on = "info"')
    (tmp_path / "empty").mkdir()
    search = ["", str(tmp_path / "empty"), str(first), str(second)]

    profile = load_profile(
        "studio", environ={PROFILE_PATH_ENV: os.pathsep.join(search)}
    )

    assert profile.fail_on is Severity.WARNING
    assert profile.source == str(first / "studio.toml")


def test_profile_path_can_shadow_builtin_profiles(tmp_path: Path) -> None:
    write(tmp_path, "default.toml", 'fail_on = "info"')

    profile = load_profile(
        "default", environ={PROFILE_PATH_ENV: str(tmp_path)}
    )

    assert profile.fail_on is Severity.INFO


def test_unknown_names_say_where_they_were_searched(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as excinfo:
        load_profile("studio", environ={PROFILE_PATH_ENV: str(tmp_path)})

    message = str(excinfo.value)
    assert message.startswith(f"profile 'studio' not found in {tmp_path}")
    assert "built-in profiles (default)" in message
    assert PROFILE_PATH_ENV in message


@pytest.mark.parametrize("name", ["missing.toml", "dir/missing"])
def test_missing_profile_files_are_reported(name: str) -> None:
    with pytest.raises(ConfigError, match="does not exist"):
        load_profile(name, environ={})


def test_invalid_toml_is_reported(tmp_path: Path) -> None:
    path = write(tmp_path, "broken.toml", "fail_on = ")

    with pytest.raises(ConfigError, match="is not valid TOML"):
        load_profile(str(path), environ={})


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('fail_on = "fatal"', "fail_on: invalid severity 'fatal'"),
        ('load = "some"', "load must be 'all' or 'none', not 'some'"),
        ('checks = "stage.metadata"', "checks must be a list of check ids"),
        ("checks = [1]", "checks must be a list of check ids"),
        ("checks = []", "checks is empty"),
        ('checks = ["a.b", "a.b"]', "checks lists 'a.b' twice"),
        ('severity = "error"', "severity must be a table"),
        ('[severity]\n"a.b" = "loud"', "severity.a.b: invalid severity"),
        ("options = 1", "options must be a table"),
        ('[options]\n"a.b" = 1', "options.a.b must be a table"),
        ("unknown = 1", "unknown key 'unknown'"),
    ],
)
def test_invalid_profiles_are_rejected(
    tmp_path: Path, text: str, message: str
) -> None:
    path = write(tmp_path, "bad.toml", text)

    with pytest.raises(ConfigError, match=message):
        load_profile(str(path), environ={})


def profile(**fields: object) -> Profile:
    return Profile(name="test", source="test.toml", **fields)  # type: ignore[arg-type]


def test_checks_follow_profile_order_with_their_options(
    registry: CheckRegistry,
) -> None:
    checks = build_checks(
        profile(
            checks=("stage.metadata", "naming.prim_name"),
            options={"stage.metadata": {"up_axis": "Z"}},
        ),
        registry,
    )

    assert [check.check_id for check in checks] == [
        "stage.metadata",
        "naming.prim_name",
    ]
    assert isinstance(checks[0], StageMetadataCheck)
    assert checks[0].up_axis == "Z"


def test_without_checks_every_registered_check_runs(
    registry: CheckRegistry,
) -> None:
    checks = build_checks(profile(), registry)

    assert [check.check_id for check in checks] == [
        "naming.prim_name",
        "stage.metadata",
    ]


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        (
            {"checks": ("stage.metadat",)},
            "unknown check 'stage.metadat'; did you mean 'stage.metadata'",
        ),
        (
            {"severity": {"nope.check": Severity.INFO}},
            "unknown check 'nope.check'",
        ),
        (
            {
                "checks": ("stage.metadata",),
                "options": {"naming.prim_name": {}},
            },
            "'naming.prim_name' is configured but not listed in 'checks'",
        ),
        (
            {"options": {"stage.metadata": {"upaxis": "Y"}}},
            "Valid options: up_axis, meters_per_unit, require_default_prim",
        ),
        (
            {"options": {"stage.metadata": {"up_axis": "X"}}},
            "up_axis must be one of",
        ),
        (
            {"options": {"naming.prim_name": {"rules": {"Mesh": "("}}}},
            "invalid regular expression",
        ),
    ],
)
def test_invalid_configurations_are_rejected(
    registry: CheckRegistry, fields: dict[str, object], message: str
) -> None:
    with pytest.raises(ConfigError, match=message):
        build_checks(profile(**fields), registry)
