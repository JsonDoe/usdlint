# usdguard

usdguard validates USD stages against studio policy: naming, metadata,
dependencies, material bindings, model hierarchy and geometry
integrity. It is DCC-agnostic and pluggable: checks are discovered
through Python entry points, so studios can add their own without
forking the project.

> **Status: pre-alpha.** Version 0.1 is under active development and
> nothing has been released yet. The Python API, the command-line
> interface and the reports are being built milestone by milestone;
> see the [changelog](CHANGELOG.md) for what exists today.

## Development

The project uses [uv](https://docs.astral.sh/uv/) and targets
Python 3.10 and newer.

```sh
uv sync                      # create .venv with runtime and dev deps
uv run pre-commit install    # run the linters on every commit
uv run pytest                # tests with the coverage gate
```

## License

Licensed under the [Apache License 2.0](LICENSE).
