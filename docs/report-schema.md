# JSON report schema

`usdguard check --format json` writes one JSON document per invocation.
This page describes **schema version 1**.

## Stability and determinism

- `schema_version` changes only for incompatible changes, such as a
  removed or renamed field or a changed meaning. New optional fields
  can appear without a version bump, so consumers should ignore unknown
  keys.
- Keys are sorted and indentation is fixed, and issues keep a stable
  order. The same files checked with the same profile and usdguard
  version produce byte-identical documents, so reports can be diffed or
  committed.
- Files written with `-o` are UTF-8 with LF line endings on every
  platform. Non-ASCII characters are escaped (`\uXXXX`).

## Example

```json
{
  "profile": "default",
  "runs": [
    {
      "issues": [
        {
          "check_id": "stage.metadata",
          "layer": "",
          "message": "upAxis is not authored; expected 'Y'",
          "prim_path": "",
          "severity": "error"
        },
        {
          "check_id": "naming.prim_name",
          "layer": "",
          "message": "Mesh name 'Leg1' does not match '^[a-z][a-zA-Z0-9]*_GEO$'",
          "prim_path": "/chair/Leg1",
          "severity": "warning"
        }
      ],
      "stage": "assets/chair/chair.usda",
      "summary": {
        "error": 1,
        "info": 0,
        "warning": 1
      }
    }
  ],
  "schema_version": 1,
  "tool": {
    "name": "usdguard",
    "version": "0.1.0"
  }
}
```

## Fields

### Document

| Field | Type | Description |
|---|---|---|
| `schema_version` | integer | Version of this schema, currently `1`. |
| `tool.name` | string | Always `"usdguard"`. |
| `tool.version` | string | usdguard version that wrote the report. |
| `profile` | string | Profile name: the built-in name, the name found in `USDGUARD_PROFILE_PATH`, or the stem of the profile file. |
| `runs` | array of run | One entry per stage, in command-line order after glob expansion. |

### Run

| Field | Type | Description |
|---|---|---|
| `stage` | string | Stage path as given on the command line, with forward slashes. |
| `summary` | object | Number of issues per severity. Keys are always `error`, `warning` and `info`, even when the count is zero. |
| `issues` | array of issue | Every issue found in the stage. See *Issue order* below. |

### Issue

| Field | Type | Description |
|---|---|---|
| `check_id` | string | Check that reported the issue, such as `geom.extent`. See *Pseudo checks* below. |
| `severity` | string | `"error"`, `"warning"` or `"info"`, after the profile's severity overrides. |
| `message` | string | Human-readable description. |
| `prim_path` | string | Path of the offending prim. Empty for stage-level issues. Prims inside instancing prototypes are reported with their prototype path (`/__Prototype_1/...`). |
| `layer` | string | Identifier of the offending layer when the check knows it, else empty. |

## Issue order

Issues are sorted by:

1. severity, most severe first;
2. `check_id`;
3. `prim_path`;
4. `message`;
5. `layer`.

## Pseudo checks

| `check_id` | Meaning |
|---|---|
| `usdguard.open` | The stage could not be opened, or a glob pattern matched no file. The run contains only this issue, and the command exits with code 2. |

A check that crashes is reported under its own `check_id`, as an
`error` whose message starts with `Check crashed:`.

## Exit codes

The JSON document does not carry the exit code. The process exits with:

- `0` when no issue reaches the `fail_on` severity;
- `1` when at least one does;
- `2` for usage, configuration or stage-open errors.

When several stages are checked, the highest code wins.
