# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Optional Qt desktop UI, `usdguard-ui`, installed with the `ui` extra.
  - Built on Qt.py; works with PySide6 and PySide2.
  - Pick a stage and a profile, filter by severity or check, sort, and
    see the details of each issue.
  - Validation runs in a worker thread, and only the immutable `Report`
    crosses threads.
- `usdguard check`: validates stages, or glob patterns expanded by
  usdguard itself, against a profile.
  - Writes a text, JSON or JUnit report to stdout or to a file.
  - Exits with 0 (no failing issue), 1 (issues at or above `fail_on`)
    or 2 (usage, configuration or stage-open error).
  - `--fail-on` and `--load` override the profile.
  - `-v` and `-q` set the log level.
- `usdguard list-checks`, `usdguard explain CHECK_ID` and
  `usdguard --version`; `python -m usdguard` runs the same CLI.
- TOML profiles.
  - They set `fail_on`, the payload `load` policy, the checks to run,
    per-check severity overrides and per-check options.
  - `--profile` takes a file path, a name found in
    `USDGUARD_PROFILE_PATH`, or a built-in profile name.
  - Mistakes raise `ConfigError` with an actionable message and exit
    with code 2.
  - A built-in `default` profile ships with the package.
- Reporters:
  - aligned text with a summary line, colored on terminals unless
    `NO_COLOR` is set;
  - deterministic JSON following schema version 1
    ([docs/report-schema.md](docs/report-schema.md));
  - JUnit XML with one test suite per stage and one test case per
    check.
- Ten built-in checks:
  - `naming.prim_name`
  - `stage.metadata`
  - `deps.absolute_arc_path`
  - `deps.absolute_asset_attr`
  - `deps.unresolved`
  - `shading.material_binding`
  - `model.hierarchy`
  - `geom.primvar_size`
  - `geom.extent`
  - `compliance.usdchecker`, built on OpenUSD's `UsdValidation`
    framework
- `usdguard.run()` runs stage checks first, then one shared traversal
  for prim checks. Instancing prototypes are checked once, each check
  invocation is isolated from crashes, profile severity overrides are
  applied, and issues come out in a deterministic order.
- `usdguard.open_stage()` applies the payload load policy. USD
  diagnostics are routed to `logging` instead of stderr.
- `CheckRegistry` discovers checks registered in the `usdguard.checks`
  entry-point group, lazily and with caching. It rejects duplicate and
  inconsistent registrations.
- Core data model:
  - `Severity`;
  - frozen `Issue` and `Report`, with `exit_code` and `counts()`;
  - the per-run `Context` with its shared cache;
  - the `Check`, `StageCheck` and `PrimCheck` base classes.
- An error hierarchy rooted at `UsdGuardError`: `ConfigError`,
  `RegistryError`, `DuplicateCheckError` and `StageOpenError`.
- Examples:
  - a complete plugin package with its own tests
    ([examples/custom_check_plugin](examples/custom_check_plugin));
  - clean and broken sample stages;
  - a commented studio profile.
- Documentation:
  - a README with the architecture, check catalog, profiles, plugin
    guide, CI integration and design trade-offs;
  - a contributing guide;
  - the report schema.
- Packaging and CI:
  - a hatchling build with a `src/` layout, PEP 561 typing and the
    version single-sourced in `usdguard.__version__`;
  - CI with ruff, strict mypy, pytest and a 90% coverage gate on Linux
    and Windows, for Python 3.10 to 3.14;
  - CI jobs that test the oldest supported `usd-core` (25.11) and the
    example plugin;
  - a release workflow that publishes to PyPI through trusted
    publishing and creates the GitHub Release.
