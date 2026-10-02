# usdguard example plugin

A minimal, complete usdguard plugin: one custom check, the entry point
that registers it, and its tests. Copy this directory to start a studio
plugin.

```text
custom_check_plugin/
├── pyproject.toml                    # entry point in "usdguard.checks"
├── src/usdguard_example_plugin/
│   └── checks.py                     # NoEmptyGroupsCheck
└── tests/
    └── test_no_empty_groups.py
```

Try it from the repository root:

```sh
uv pip install ./examples/custom_check_plugin
uv run usdguard list-checks           # lists example.no_empty_groups
uv run usdguard explain example.no_empty_groups
uv run pytest examples/custom_check_plugin
```

Enable it in a profile like any built-in check:

```toml
checks = ["stage.metadata", "example.no_empty_groups"]

[options."example.no_empty_groups"]
types = ["Xform"]
```
