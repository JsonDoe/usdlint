# Example stages

Small, generic assets to try usdguard on. The test suite runs them, so
what this page says stays true.

| File | What it shows |
|---|---|
| `chair.usda` | A clean `component`: metadata, names, materials, extents and model kind all pass the default profile. |
| `table.usda` | Another clean component, loaded as a payload by `room_layout.usda`. |
| `room_layout.usda` | An `assembly` with a `group` of three instanced chairs and a payloaded table. Prims inside the chair prototype are checked once and reported under `/__Prototype_1/...`. With `--load none`, the table and its payload are not traversed. |
| `chair_broken.usda` | Fails every built-in check: missing and wrong metadata, bad names, absolute and unresolved paths, unbound geometry, a component nested in a component, wrong primvar sizes, out-of-range indices, missing and stale extents, and nested gprims. |

Try them from the repository root:

```sh
uv run usdguard check "examples/stages/*.usda"
uv run usdguard check examples/stages/chair_broken.usda --format json
uv run usdguard check examples/stages/room_layout.usda --load none -v
uv run usdguard check examples/stages/chair_broken.usda --profile examples/profiles/lenient.toml
```

`chair_broken.usda` exits with code 1, and the clean stages with 0.

Or browse them in the desktop UI:

```sh
uv sync --extra ui
uv run usdguard-ui examples/stages/chair_broken.usda
```
