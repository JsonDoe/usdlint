# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Core data model: `Severity`, frozen `Issue` and `Report` (with
  `exit_code` and `counts()`), the per-run `Context` and its shared
  cache, and the `Check`, `StageCheck` and `PrimCheck` base classes.
- `usdguard.run()`: stage checks first, then one shared traversal for
  prim checks (instancing prototypes are checked once), crash isolation,
  profile severity overrides and deterministic issue order.
  `usdguard.open_stage()` applies the payload load policy.
- `CheckRegistry`: lazy, cached discovery of checks registered in the
  `usdguard.checks` entry-point group, with duplicate and consistency
  checks.
- Built-in checks: `naming.prim_name`, `stage.metadata`,
  `deps.absolute_arc_path`, `deps.absolute_asset_attr`,
  `deps.unresolved`, `shading.material_binding`, `model.hierarchy`,
  `geom.primvar_size`, `geom.extent` and `compliance.usdchecker`.
- Error hierarchy rooted at `UsdGuardError`: `ConfigError`,
  `RegistryError`, `DuplicateCheckError`, `StageOpenError`.
- `usdguard` package with a hatchling build and a `src/` layout. The
  version is single-sourced in `usdguard.__version__`.
- PEP 561 `py.typed` marker, so plugin authors type-check against the
  package.
- Development tooling: ruff (lint and format), strict mypy, pytest with
  a 90% coverage gate, and pre-commit hooks.
- Continuous integration on Ubuntu and Windows for Python 3.10 to 3.14.
