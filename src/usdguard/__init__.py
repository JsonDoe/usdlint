"""usdguard: a pluggable, DCC-agnostic validation framework for USD.

usdguard validates USD stages against studio policy (naming, metadata,
dependencies, material bindings, model hierarchy and geometry
integrity). Checks are plugins discovered through entry points, so
studios can extend the framework without forking it.
"""

__version__ = "0.1.0.dev0"

__all__ = ["__version__"]
