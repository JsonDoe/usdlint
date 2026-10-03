# Contributing to usdguard

Thanks for helping! This page covers setting up a development
environment, the project's conventions, adding a check, and releasing.

## Development environment

usdguard uses [uv](https://docs.astral.sh/uv/) and supports Python 3.10
to 3.14. The committed `uv.lock` pins every tool, so local runs match CI.

```sh
git clone https://github.com/JsonDoe/usdlint.git
cd usdlint
uv sync                     # .venv with usd-core and the dev tools
uv run pre-commit install   # lint and type-check on every commit
```

If you prefer plain pip (25.1 or newer):

```sh
python -m venv .venv
.venv/bin/pip install -e . --group dev   # .venv\Scripts\pip on Windows
```

The development environment uses Python 3.10, the oldest supported
version (see `.python-version`). To run the suite with another
interpreter:

```sh
uv run --isolated --python 3.14 pytest
```

## Checks to run before pushing

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest               # enforces the 90% coverage gate
```

`uv run pytest --no-cov tests/checks/test_geom.py` runs a subset without
the coverage gate. `uv run pre-commit run --all-files` runs every hook,
like the CI lint job.

The Qt UI tests are marked `ui` and skipped by default. To run them,
install the UI extra and test group; on headless machines, also set
`QT_QPA_PLATFORM=offscreen`:

```sh
uv sync --extra ui --group ui
uv run pytest -m ui --no-cov
```

They are excluded from the coverage gate. CI runs them with PySide6
(Linux and Windows) and with PySide2 (Python 3.10). A plain `uv sync`
removes the UI packages again.

## Conventions

- **Commits** follow [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat(checks): ...`, `fix(cli): ...`, `docs: ...`), with one logical
  change per commit.
- **Code style:** PEP 8 with 79-column lines (ruff), full type hints
  (mypy strict), and Google-style docstrings on every public module,
  class and function, without repeating types.
- **Output:** use `logging`, never `print`. Only the CLI writes to
  stdout.
- **Design:** use dataclasses for data, frozen where possible. Keep
  state out of the module level; constants and loggers are the only
  exceptions.
- **No DCC modules (`maya`, `hou`) and no network access.** Ruff
  enforces both.
- **pxr APIs:** usd-core ships neither docstrings nor type stubs, so do
  not write calls from memory. Get the real signatures from
  Boost.Python by calling with dummy arguments, then confirm the
  behaviour with a small experiment:

  ```sh
  uv run python -c "from pxr import UsdGeom; UsdGeom.Boundable.ComputeExtentFromPlugins(*[object()] * 9)"
  ```

- **Docs:** update `CHANGELOG.md` (Keep a Changelog format) and the
  README with every user-visible change.

## Adding a built-in check

1. **Pick the module.** Choose or create a module in
   `src/usdguard/checks/` named after the check family; the `check_id`
   is `<family>.<name>`.
2. **Write the class.** Subclass `StageCheck` or `PrimCheck` and set
   `check_id`, `description` and, if needed, `severity`. Constructor
   keyword arguments are the options; validate them with the helpers in
   `usdguard.checks._options`, so a bad profile raises `ValueError` with
   a clear message.
3. **Write the class docstring.** It feeds `usdguard explain`, so keep
   to this order: what is required, why it matters, an `Options:`
   section, and an `Example:` that fails the check.
4. **Register the entry point** in `pyproject.toml`, under
   `[project.entry-points."usdguard.checks"]`, then run `uv sync`.
5. **Test it** in `tests/checks/`. Include at least one passing and one
   failing fixture: an in-memory stage from the `make_stage` fixture,
   or a small `.usda` file in `tests/data/` when the check needs real
   files.
6. **Update the docs.** Add the check to the catalog in `README.md`
   and to `tests/checks/test_builtin.py`, and decide whether the
   default profile should enable it.

## Releasing

Releases are published from tags by `.github/workflows/release.yml`,
using PyPI trusted publishing, so no token is stored in the repository.

**One-time setup:**

1. On PyPI, add a trusted publisher for the project `usdguard` with:
   - repository `JsonDoe/usdlint`;
   - workflow `release.yml`;
   - environment `pypi`.
2. On GitHub, create an environment named `pypi`. Protect it with
   required reviewers if you want a manual approval step.

**Each release:**

1. **Bump the version.** Set `__version__` in
   `src/usdguard/__init__.py`, for example to `0.1.0`.
2. **Update the changelog.** In `CHANGELOG.md`, rename the `Unreleased`
   section to `[0.1.0] - YYYY-MM-DD` and add a new, empty `Unreleased`
   section above it.
3. **Commit and merge.** Commit with `chore(release): 0.1.0` and merge
   to `main`.
4. **Tag and push:**

   ```sh
   git tag v0.1.0 && git push origin v0.1.0
   ```

5. **The workflow takes over.** It checks that the tag matches
   `__version__`, builds and verifies the sdist and wheel, and
   publishes them to PyPI. It then creates the GitHub Release, using
   the changelog section as release notes.
