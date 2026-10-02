"""Discovery of check classes, built in or provided by plugins.

Checks are registered as entry points in the ``usdguard.checks`` group,
named after their ``check_id``::

    [project.entry-points."usdguard.checks"]
    "studio.no_empty_xforms" = "studio_checks.xforms:NoEmptyXforms"

Discovery is lazy: listing entry points imports nothing, and a check
module is imported the first time one of its checks is requested. The
registry instance caches loaded classes, so no module is imported twice.
"""

from __future__ import annotations

import difflib
import inspect
from importlib.metadata import EntryPoint, entry_points
from typing import TYPE_CHECKING

from usdguard.core import Check, PrimCheck, StageCheck
from usdguard.errors import DuplicateCheckError, RegistryError

if TYPE_CHECKING:
    from collections.abc import Iterable

ENTRY_POINT_GROUP = "usdguard.checks"


class CheckRegistry:
    """The check classes available to validation runs.

    Args:
        plugins: Entry points to register. Defaults to every entry point
            of the ``usdguard.checks`` group installed in the current
            environment.
        classes: Check classes to register directly, without an entry
            point, for instance from tests or embedding applications.

    Raises:
        DuplicateCheckError: Two entry points or classes share a
            ``check_id``.
        RegistryError: A class in ``classes`` is not a valid check.
    """

    def __init__(
        self,
        plugins: Iterable[EntryPoint] | None = None,
        classes: Iterable[type[Check]] = (),
    ) -> None:
        if plugins is None:
            plugins = entry_points(group=ENTRY_POINT_GROUP)
        self._entry_points: dict[str, EntryPoint] = {}
        self._classes: dict[str, type[Check]] = {}
        for entry_point in plugins:
            known = self._entry_points.get(entry_point.name)
            if known is not None:
                msg = (
                    f"check_id {entry_point.name!r} is registered twice: "
                    f"by {known.value!r} and by {entry_point.value!r}"
                )
                raise DuplicateCheckError(msg)
            self._entry_points[entry_point.name] = entry_point
        for cls in classes:
            check_id = _validate_class(cls).check_id
            if check_id in self._entry_points or check_id in self._classes:
                msg = (
                    f"check_id {check_id!r} is registered twice; the second "
                    f"registration is {cls.__module__}.{cls.__qualname__}"
                )
                raise DuplicateCheckError(msg)
            self._classes[check_id] = cls

    @classmethod
    def from_classes(cls, classes: Iterable[type[Check]]) -> CheckRegistry:
        """Return a registry holding exactly ``classes``.

        Installed plugins are ignored, which keeps tests hermetic.
        """
        return cls(plugins=(), classes=classes)

    def __contains__(self, check_id: object) -> bool:
        return check_id in self._entry_points or check_id in self._classes

    def ids(self) -> list[str]:
        """Return the sorted ids of every registered check.

        Nothing is imported.
        """
        return sorted(self._entry_points.keys() | self._classes.keys())

    def get(self, check_id: str) -> type[Check]:
        """Return the class registered as ``check_id``, loading it once.

        Raises:
            KeyError: No check is registered as ``check_id``; the message
                suggests close matches.
            RegistryError: The entry point cannot be loaded, does not
                name a concrete check class, or its name differs from
                the class ``check_id``.
        """
        cls = self._classes.get(check_id)
        if cls is not None:
            return cls
        entry_point = self._entry_points.get(check_id)
        if entry_point is None:
            raise KeyError(self.unknown_check_message(check_id))
        cls = _load(entry_point)
        self._classes[check_id] = cls
        return cls

    def load_all(self) -> dict[str, type[Check]]:
        """Load every registered check; the mapping is sorted by id."""
        return {check_id: self.get(check_id) for check_id in self.ids()}

    def unknown_check_message(self, check_id: str) -> str:
        """Describe an unknown ``check_id``, suggesting close matches."""
        message = f"unknown check {check_id!r}"
        matches = difflib.get_close_matches(check_id, self.ids(), n=3)
        if matches:
            message += f"; did you mean {' or '.join(map(repr, matches))}?"
        return message


def _load(entry_point: EntryPoint) -> type[Check]:
    try:
        loaded = entry_point.load()
    except Exception as exc:
        msg = (
            f"cannot load check {entry_point.name!r} from "
            f"{entry_point.value!r}: {exc!r}"
        )
        raise RegistryError(msg) from exc
    cls = _validate_class(loaded, origin=entry_point.value)
    if cls.check_id != entry_point.name:
        msg = (
            f"entry point {entry_point.name!r} loads {entry_point.value!r}, "
            f"whose check_id is {cls.check_id!r}; the entry point name must "
            "equal the check_id"
        )
        raise RegistryError(msg)
    return cls


def _validate_class(cls: object, origin: str = "") -> type[Check]:
    """Return ``cls`` narrowed to a check class, after validating it."""
    name = origin or getattr(cls, "__qualname__", repr(cls))
    if not (isinstance(cls, type) and issubclass(cls, StageCheck | PrimCheck)):
        msg = f"{name} is not a subclass of StageCheck or PrimCheck"
        raise RegistryError(msg)
    if inspect.isabstract(cls):
        msg = f"{name} does not implement every abstract method"
        raise RegistryError(msg)
    check_id = getattr(cls, "check_id", None)
    description = getattr(cls, "description", None)
    if not (isinstance(check_id, str) and check_id):
        msg = f"{name} must define a non-empty string check_id"
        raise RegistryError(msg)
    if not (isinstance(description, str) and description):
        msg = f"{name} must define a non-empty string description"
        raise RegistryError(msg)
    return cls
