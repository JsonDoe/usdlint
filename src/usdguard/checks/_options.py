"""Validation helpers for check options.

Options usually come from TOML profiles, so their values are checked at
runtime. Each helper returns the value converted to its expected type,
or raises ``ValueError`` with a message naming the option.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Collection


def _fail(name: str, expected: str, value: object) -> ValueError:
    return ValueError(f"{name} must be {expected}, not {value!r}")


def number(name: str, value: object, *, minimum: float = 0.0) -> float:
    """Return ``value`` as a float, requiring a number >= ``minimum``."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _fail(name, "a number", value)
    if value < minimum:
        raise _fail(name, f"a number >= {minimum:g}", value)
    return float(value)


def positive_number(name: str, value: object) -> float:
    """Return ``value`` as a float, requiring a number > 0."""
    result = number(name, value)
    if result <= 0:
        raise _fail(name, "a positive number", value)
    return result


def boolean(name: str, value: object) -> bool:
    """Return ``value``, requiring ``True`` or ``False``."""
    if not isinstance(value, bool):
        raise _fail(name, "true or false", value)
    return value


def one_of(name: str, value: object, choices: Collection[str]) -> str:
    """Return ``value``, requiring one of the string ``choices``."""
    if not isinstance(value, str) or value not in choices:
        expected = "one of " + ", ".join(repr(choice) for choice in choices)
        raise _fail(name, expected, value)
    return value


def string_list(name: str, value: object) -> tuple[str, ...]:
    """Return ``value`` as a tuple, requiring a list of strings."""
    if isinstance(value, str) or not isinstance(value, list | tuple):
        raise _fail(name, "a list of strings", value)
    if not all(isinstance(item, str) for item in value):
        raise _fail(name, "a list of strings", value)
    return tuple(value)


def string_mapping(name: str, value: object) -> dict[str, str]:
    """Return ``value`` as a dict, requiring a string-to-string mapping."""
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) and isinstance(item, str)
        for key, item in value.items()
    ):
        raise _fail(name, "a table of strings", value)
    return dict(value)
