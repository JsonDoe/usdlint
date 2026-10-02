"""usdguard: a pluggable, DCC-agnostic validation framework for USD.

usdguard validates USD stages against studio policy (naming, metadata,
dependencies, material bindings, model hierarchy and geometry
integrity). Checks are plugins discovered through entry points, so
studios can extend the framework without forking it.

Typical use from Python::

    from usdguard import CheckRegistry, open_stage, run

    registry = CheckRegistry()
    checks = [registry.get("stage.metadata")()]
    report = run(open_stage("asset.usda"), checks)
    for issue in report.issues:
        print(issue.severity.label, issue.prim_path, issue.message)
"""

from usdguard.core import (
    Check,
    Context,
    Issue,
    PrimCheck,
    Report,
    Severity,
    StageCheck,
)
from usdguard.errors import (
    ConfigError,
    DuplicateCheckError,
    RegistryError,
    StageOpenError,
    UsdGuardError,
)
from usdguard.registry import CheckRegistry
from usdguard.runner import open_stage, run

__version__ = "0.1.0.dev0"

__all__ = [
    "Check",
    "CheckRegistry",
    "ConfigError",
    "Context",
    "DuplicateCheckError",
    "Issue",
    "PrimCheck",
    "RegistryError",
    "Report",
    "Severity",
    "StageCheck",
    "StageOpenError",
    "UsdGuardError",
    "__version__",
    "open_stage",
    "run",
]
