"""Exceptions raised by usdguard.

Every error derives from :class:`UsdGuardError`, so callers embedding
usdguard can catch a single type. The CLI maps all of them to exit
code 2.
"""


class UsdGuardError(Exception):
    """Base class of every error raised by usdguard."""


class ConfigError(UsdGuardError):
    """A profile, a check option or a command-line value is invalid."""


class RegistryError(UsdGuardError):
    """A check plugin cannot be loaded or is declared inconsistently."""


class DuplicateCheckError(RegistryError):
    """Two registered checks share the same ``check_id``."""


class StageOpenError(UsdGuardError):
    """A USD stage could not be opened."""
