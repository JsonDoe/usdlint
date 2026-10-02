# CLAUDE.md

Guidance for AI assistants and contributors working in this repository.

## Project

usdguard is a pluggable, DCC-agnostic framework that validates USD stages
against studio policy (naming, metadata, dependencies, bindings, model
hierarchy, geometry integrity). It offers a Python API, a CLI with
CI-friendly exit codes and text/JSON/JUnit reports. Checks are plugins
discovered through the `usdguard.checks` entry-point group, so studios
extend it without forking. No studio-specific names, paths, hosts or
schemas anywhere: examples stay generic.

The project is built milestone by milestone: M0 scaffold, M1 core
(core, runner, registry, errors), M2 check catalog, M3 profiles + CLI +
reporters, M4 docs + release, M5 optional Qt UI (`[ui]` extra, separate
branch). The full specification is kept by the maintainer outside the
repository; the design below condenses it. Ask when a detail is missing.

Status: M0 (scaffold) complete and awaiting review; M1 not started.

## Commands

```sh
uv sync                                  # .venv with runtime + dev deps
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest                            # includes the 90% coverage gate
uv run pytest --no-cov tests/test_x.py   # focused run, no coverage gate
uv run pre-commit run --all-files
uv run --isolated --python 3.14 pytest   # another interpreter
uv build                                 # sdist + wheel into dist/
```

A change is done only when `ruff check`, `ruff format --check`,
`mypy src` and `pytest` are all green. CI (`.github/workflows/ci.yml`)
runs pre-commit once, then mypy and pytest on ubuntu and windows for
Python 3.10 to 3.14.

## Working agreement

- Plan each milestone before writing code and list ambiguities. Ask one
  precise question if blocked; otherwise state the assumption and go.
- Verify every pxr API by introspection in the project venv; never rely
  on memory. usd-core ships no docstrings, so `help()` shows nothing.
  Call the function with dummy arguments to make Boost.Python list its
  C++ overloads (parameter names and defaults included), then confirm
  the behaviour with a small runtime experiment:
  `uv run python -c "from pxr import UsdGeom; UsdGeom.Boundable.ComputeExtentFromPlugins(*[object()] * 9)"`
- Conventional Commits, one logical change per commit.
- Runtime dependencies are `usd-core` and `tomli; python_version < "3.11"`
  only. Ask before adding any other.
- Stop at the end of each milestone: summarize, list deviations from the
  spec, and wait for the maintainer's go.
- Reflect public API changes in README.md and CHANGELOG.md. No TODO
  without a linked issue.

## Conventions

- Python 3.10+, PEP 8, 79-column lines, absolute imports only (ruff).
- Full type hints, mypy strict. Google-style docstrings on every public
  module, class and function, without repeating the types.
- `logging` only. `print` is allowed only in CLI reporters writing to
  stdout (ruff T20 enforces this; add per-file ignores there).
- Dataclasses for data, frozen where possible. No global mutable state
  and no module-level side effects beyond constants and logger creation.
- No DCC imports (`maya`, `pymel`, `hou`) and no network modules: ruff
  TID251 bans them; the package must never touch the network at runtime.
- Deterministic output: stable issue order, sorted JSON keys.
- Tests: `Usd.Stage.CreateInMemory()` fixtures for unit tests, small
  hand-written `.usda` files in `tests/data` for path-dependent checks,
  one passing and at least one failing fixture per check. CLI tests call
  `cli.main(argv)` directly (plus one subprocess smoke test).

## Architecture (target design for v0.1)

```
src/usdguard/
  __init__.py   __version__ (hatchling reads it), public API re-exports
  core.py       Severity, Issue, Context, Check, StageCheck, PrimCheck
  runner.py     run() -> Report, crash isolation
  registry.py   entry-point discovery, duplicate detection
  profiles.py   TOML profile loading, resolution, validation
  errors.py     UsdGuardError, ConfigError, DuplicateCheckError
  reporters/    text.py, json.py, junit.py
  checks/       naming, stage, deps, shading, model, geom, compliance
  profiles/     built-in profiles shipped as package data (default.toml)
  cli.py        argparse: check, list-checks, explain, --version
```

Core contracts:
- `Severity(IntEnum)`: INFO=10, WARNING=20, ERROR=30.
- `Issue` (frozen): `check_id`, `severity`, `message`, `prim_path=""`,
  `layer=""`.
- `Context`: `stage`, `stage_path` (empty for in-memory stages),
  `cache: dict[str, Any]` scratch space shared across checks.
- `Check(ABC)`: ClassVars `check_id`, `description`, `severity=ERROR`;
  helper `issue(message, prim=None, layer="")`. Constructor kwargs are
  the check's options. The class docstring (rationale, options, minimal
  failing example) feeds `usdguard explain`.
- `StageCheck.check_stage(context) -> Iterator[Issue]`;
  `PrimCheck.applies_to(prim) -> bool` (default True) and
  `PrimCheck.check_prim(prim, context) -> Iterator[Issue]`.
- `Report` (frozen): `issues: tuple[Issue, ...]`, `fail_on`,
  `exit_code` (1 if any issue >= fail_on, else 0), `counts()`.

Runner: stage checks first, then ONE `stage.Traverse()` dispatching all
prim checks. Each check invocation is isolated: its generator is
materialized inside try/except, a crash becomes an ERROR issue
`"Check crashed: <repr>"` logged with traceback, and the run continues.
Issues sort by severity desc, check_id, prim_path, message. Profile
severity overrides are applied by the runner, never by checks.

Registry: entry-point name == `check_id`. `DuplicateCheckError` when two
entry points or classes share a `check_id`, or a name differs from its
class `check_id`. Loading is lazy and cached.

Check catalog: `naming.prim_name` (regex per type), `stage.metadata`
(upAxis, metersPerUnit, defaultPrim), `deps.absolute_arc_path` and
`deps.absolute_asset_attr` (absolute if `posixpath.isabs` or
`ntpath.isabs`, never `os.path`), `deps.unresolved`,
`shading.material_binding` (batched `ComputeBoundMaterials`),
`model.hierarchy` (authored kind but `IsModel()` false),
`geom.primvar_size`, `geom.extent`, `compliance.usdchecker`.

Profiles: TOML (`fail_on`, `load`, `checks`, `[severity]`,
`[options."<check_id>"]`). `--profile` takes an existing file, else
`<name>.toml` from `USDGUARD_PROFILE_PATH` (os.pathsep, first match),
else the built-in profiles. Invalid input raises `ConfigError`.

CLI exit codes: 0 no issue at or above fail_on, 1 issues found, 2 usage,
config or stage-open error; with several stages, the max code wins.

## Decision log

- CI matrix is Python 3.10 to 3.14 on ubuntu and windows: usd-core 26.8
  ships cp310 to cp314 wheels. 3.14 goes beyond the spec (same rule as
  3.13).
- uv with a committed `uv.lock`; dev tools in the PEP 735 `dev` group.
  Plain pip: `pip install -e . --group dev` (pip >= 25.1).
- Version stays `0.1.0.dev0` until the 0.1.0 release. `[tool.uv]
  cache-keys` includes `__init__.py`, so a version bump refreshes the
  editable install metadata that `tests/test_package.py` compares.
- `.python-version` pins the dev venv to 3.10, the lowest supported
  version. mypy has no `python_version` pin, so CI checks each version.
- types-usd rejected (types-usd 24.5.2 vs usd-core 26.8): it flags the
  idiomatic `Prim.IsA(UsdGeom.Mesh)` and lacks `pxr.UsdValidation`.
  mypy ignores missing imports for `pxr` only.
- `UsdUtils.ComplianceChecker` was deprecated in usd-core 26.5 and
  removed in 26.8. Proposed for M2: build `compliance.usdchecker` on
  `pxr.UsdValidation` (Python API since usd-core 25.2); confirm with the
  maintainer first.
- The usd-core version floor is set in M2 with the real API usage
  (expected `>=25.2`); `tomli` is added in M3 with the profile loader.

## Gotchas

- pxr values are `Any` for mypy. Under strict mode, returning one from a
  typed function triggers `warn_return_any`: convert explicitly, for
  example `str(prim.GetName())`.
- `UsdGeom.PrimvarsAPI.GetPrimvars()` also returns schema built-ins such
  as `displayColor` and `displayOpacity` even when nothing is authored.
- `UsdUtils.ComputeAllDependencies` returns empty lists for a missing
  root layer instead of reporting it as unresolved.
- pytest turns warnings into errors. Add a targeted, commented
  `filterwarnings` entry only once a warning is understood.
- usd-core vendors its own `pxr`. Where USD is already provided (DCC,
  rez), install usdguard with `--no-deps` to avoid shadowing it.
- Keep the ruff and mypy revisions in `.pre-commit-config.yaml` in sync
  with the `dev` dependency group.
- Workflows: GitHub's own `actions/*` use major tags (`@v7`). Pin
  third-party actions to a full commit SHA with a `# vX.Y.Z` comment;
  `astral-sh/setup-uv` publishes no floating major tags after v7, so
  `@v10` does not resolve. Check that a ref exists before using it.
- Line endings are LF everywhere (`.gitattributes`), including Windows.
