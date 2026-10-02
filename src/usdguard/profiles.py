"""Validation profiles: which checks run, with which options and severity.

A profile is a TOML file::

    fail_on = "error"      # lowest severity that fails a run
    load = "all"           # payload policy: "all" or "none"
    checks = ["stage.metadata", "naming.prim_name"]

    [severity]
    "naming.prim_name" = "warning"

    [options."naming.prim_name".rules]
    Mesh = '^[a-z][a-zA-Z0-9]*_GEO$'

Every key is optional; without ``checks``, every registered check runs.
Write regular expressions as single-quoted TOML literal strings, so
backslashes reach the regular expression engine unchanged.

``--profile`` accepts a file path or a profile name. A name is looked up
as ``<name>.toml`` in each directory of ``USDGUARD_PROFILE_PATH`` (first
match wins), then among the profiles shipped with usdguard.
"""

from __future__ import annotations

import inspect
import os
import sys
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Any

from usdguard.core import Severity
from usdguard.errors import ConfigError
from usdguard.runner import LOAD_POLICIES, LoadPolicy

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised by the Python 3.10 CI jobs
    import tomli as tomllib

if TYPE_CHECKING:
    from collections.abc import Mapping

    from usdguard.core import Check
    from usdguard.registry import CheckRegistry

    if sys.version_info >= (3, 11):
        from importlib.resources.abc import Traversable
    else:
        from importlib.abc import Traversable

PROFILE_PATH_ENV = "USDGUARD_PROFILE_PATH"
"""Environment variable listing directories that hold named profiles."""

DEFAULT_PROFILE = "default"
"""Name of the profile used when none is given."""

_KEYS = ("fail_on", "load", "checks", "severity", "options")


@dataclass(frozen=True)
class Profile:
    """A parsed and validated profile.

    Attributes:
        name: Profile name: the file stem, or the built-in name.
        source: Where the profile was read from, for error messages.
        fail_on: Lowest severity that fails a run.
        load: Payload policy used to open stages.
        checks: Ids of the checks to run; empty means every registered
            check.
        severity: Severity overrides per check id.
        options: Constructor options per check id.
    """

    name: str
    source: str
    fail_on: Severity = Severity.ERROR
    load: LoadPolicy = "all"
    checks: tuple[str, ...] = ()
    severity: Mapping[str, Severity] = field(default_factory=dict)
    options: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)


def builtin_profiles() -> list[str]:
    """Return the sorted names of the profiles shipped with usdguard."""
    return sorted(
        entry.name.removesuffix(".toml")
        for entry in _builtin_dir().iterdir()
        if entry.name.endswith(".toml")
    )


def load_profile(
    value: str = DEFAULT_PROFILE, *, environ: Mapping[str, str] | None = None
) -> Profile:
    """Find, read and validate the profile named or located by ``value``.

    Args:
        value: Path of a profile file, or a profile name.
        environ: Environment to read ``USDGUARD_PROFILE_PATH`` from;
            defaults to ``os.environ``.

    Raises:
        ConfigError: The profile cannot be found, is not valid TOML or
            does not follow the profile format.
    """
    name, location = _resolve(
        value, os.environ if environ is None else environ
    )
    source = str(location)
    try:
        data = tomllib.loads(location.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        msg = f"profile {source} is not valid TOML: {exc}"
        raise ConfigError(msg) from exc
    return parse_profile(data, name=name, source=source)


def parse_profile(
    data: Mapping[str, Any], *, name: str, source: str = "<memory>"
) -> Profile:
    """Validate the content of a profile file.

    Check ids and options are validated later, by :func:`build_checks`,
    against the checks that are actually installed.

    Args:
        data: Parsed TOML document.
        name: Name to give the profile.
        source: Where the data comes from, for error messages.

    Raises:
        ConfigError: A key is unknown or a value has the wrong type.
    """
    unknown = sorted(set(data) - set(_KEYS))
    if unknown:
        msg = (
            f"profile {source}: unknown key {unknown[0]!r}; expected "
            f"{', '.join(_KEYS)}"
        )
        raise ConfigError(msg)
    return Profile(
        name=name,
        source=source,
        fail_on=_severity(data.get("fail_on", "error"), "fail_on", source),
        load=_load_policy(data.get("load", "all"), source),
        checks=_check_list(data.get("checks"), source),
        severity={
            check_id: _severity(value, f"severity.{check_id}", source)
            for check_id, value in _table(
                data.get("severity", {}), "severity", source
            ).items()
        },
        options={
            check_id: _table(value, f"options.{check_id}", source)
            for check_id, value in _table(
                data.get("options", {}), "options", source
            ).items()
        },
    )


def build_checks(profile: Profile, registry: CheckRegistry) -> list[Check]:
    """Instantiate the checks enabled by ``profile`` with their options.

    Args:
        profile: The profile to apply.
        registry: Where check classes are looked up.

    Returns:
        Configured checks, in the order the profile lists them (sorted
        by id when the profile does not list any).

    Raises:
        ConfigError: The profile names an unknown check, configures a
            check it does not enable, or gives invalid options.
        RegistryError: A check plugin cannot be loaded.
    """
    check_ids = profile.checks or tuple(registry.ids())
    configured = [*profile.severity, *profile.options]
    unknown = [
        check_id
        for check_id in dict.fromkeys([*check_ids, *configured])
        if check_id not in registry
    ]
    if unknown:
        reasons = "; ".join(registry.unknown_check_message(c) for c in unknown)
        msg = f"profile {profile.source}: {reasons}"
        raise ConfigError(msg)
    for check_id in configured:
        if check_id not in check_ids:
            msg = (
                f"profile {profile.source}: {check_id!r} is configured but "
                "not listed in 'checks'"
            )
            raise ConfigError(msg)
    return [
        _instantiate(registry.get(check_id), profile) for check_id in check_ids
    ]


def option_defaults(cls: type[Check]) -> dict[str, Any]:
    """Return the options of a check class with their default values."""
    return {
        name: parameter.default
        for name, parameter in inspect.signature(cls).parameters.items()
        if parameter.kind
        in (parameter.KEYWORD_ONLY, parameter.POSITIONAL_OR_KEYWORD)
    }


def _instantiate(cls: type[Check], profile: Profile) -> Check:
    options = profile.options.get(cls.check_id, {})
    try:
        return cls(**options)
    except TypeError as exc:
        valid = ", ".join(option_defaults(cls)) or "none"
        msg = (
            f"profile {profile.source}: invalid options for "
            f"{cls.check_id!r}: {exc}. Valid options: {valid}"
        )
        raise ConfigError(msg) from exc
    except ValueError as exc:
        msg = (
            f"profile {profile.source}: invalid options for "
            f"{cls.check_id!r}: {exc}"
        )
        raise ConfigError(msg) from exc


def _resolve(
    value: str, environ: Mapping[str, str]
) -> tuple[str, Path | Traversable]:
    path = Path(value)
    if path.is_file():
        return path.stem, path
    if path.suffix == ".toml" or len(path.parts) > 1:
        msg = f"profile file {value!r} does not exist"
        raise ConfigError(msg)
    searched: list[str] = []
    for directory in environ.get(PROFILE_PATH_ENV, "").split(os.pathsep):
        if not directory:
            continue
        candidate = Path(directory) / f"{value}.toml"
        if candidate.is_file():
            return value, candidate
        searched.append(directory)
    builtin = _builtin_dir() / f"{value}.toml"
    if builtin.is_file():
        return value, builtin
    where = f"in {', '.join(searched)} or " if searched else ""
    msg = (
        f"profile {value!r} not found {where}among the built-in profiles "
        f"({', '.join(builtin_profiles())}); set {PROFILE_PATH_ENV} or "
        "pass a file path"
    )
    raise ConfigError(msg)


def _builtin_dir() -> Traversable:
    return files("usdguard") / "profiles"


def _severity(value: object, key: str, source: str) -> Severity:
    try:
        return Severity.from_label(value)
    except ValueError as exc:
        msg = f"profile {source}: {key}: {exc}"
        raise ConfigError(msg) from exc


def _load_policy(value: object, source: str) -> LoadPolicy:
    if value not in LOAD_POLICIES:
        msg = f"profile {source}: load must be 'all' or 'none', not {value!r}"
        raise ConfigError(msg)
    return value


def _check_list(value: object, source: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        msg = f"profile {source}: checks must be a list of check ids"
        raise ConfigError(msg)
    if not value:
        msg = f"profile {source}: checks is empty; list at least one check"
        raise ConfigError(msg)
    duplicates = sorted({item for item in value if value.count(item) > 1})
    if duplicates:
        msg = f"profile {source}: checks lists {duplicates[0]!r} twice"
        raise ConfigError(msg)
    return tuple(value)


def _table(value: object, key: str, source: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        msg = f"profile {source}: {key} must be a table"
        raise ConfigError(msg)
    return value
