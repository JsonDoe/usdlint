# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `usdguard` package with a hatchling build and a `src/` layout. The
  version is single-sourced in `usdguard.__version__`.
- PEP 561 `py.typed` marker, so plugin authors type-check against the
  package.
- Development tooling: ruff (lint and format), strict mypy, pytest with
  a 90% coverage gate, and pre-commit hooks.
- Continuous integration on Ubuntu and Windows for Python 3.10 to 3.14.
