# Mascot Generator

Static browser tool for creating and previewing PSVitaAlive protection-mode mascot packages.

## Scope

This tool is **web-only**. It does not modify the PS Vita client, catalog generators, application records, authors, categories or generated catalogs.

Path:

```text
web/tools/mascot-generator/
```

## Features

- Create `mascot.json` schema version 1 files.
- Import an existing `mascot.json`.
- Import a complete mascot ZIP.
- Import PNG files separately and automatically match missing frame names when possible.
- Create multiple Idle and Run animations.
- Reorder frames with buttons or drag and drop.
- Configure frame timing, Idle range, Run timeout and movement speed.
- Validate required fields, PNG dimensions, duplicate frame names and missing assets.
- Preview the mascot inside a 960 × 544 PS Vita simulation.
- Simulate automatic Idle/Run transitions, diagonal movement and horizontal sprite mirroring.
- Force Idle or Run in the preview for testing.
- Show optional safe-area, sprite-bound and run-target overlays.
- Export `mascot.json` alone.
- Export a ready ZIP containing `<id>/mascot.json` and `<id>/*.png`.

## Privacy / hosting

The tool is fully client-side and works on GitHub Pages. Imported files are read locally by the browser and are not uploaded anywhere.

No server, database or API is required.

## Manifest format

```json
{
  "schema_version": 1,
  "name": "Vita Cat",
  "native_facing": "right",
  "width": 100,
  "height": 100,
  "behavior": {
    "run_speed": 150,
    "idle_min_ms": 2000,
    "idle_max_ms": 5000,
    "run_max_ms": 4000
  },
  "animations": {
    "idle": [
      {
        "name": "normal",
        "frame_ms": 150,
        "frames": ["idle_01_00.png", "idle_01_01.png"]
      }
    ],
    "run": [
      {
        "name": "run",
        "frame_ms": 90,
        "frames": ["run_01_00.png", "run_01_01.png"]
      }
    ]
  }
}
```

The internal mascot ID is the ZIP/folder name and is intentionally not duplicated inside `mascot.json`.

## Version 1 rules

- `schema_version` is `1`.
- One mascot per package.
- PNG frames only.
- Every frame must be exactly `100 × 100` pixels.
- `native_facing` is `left` or `right`.
- At least one Idle animation and one Run animation are required.
- Every animation requires a positive `frame_ms` and at least one frame.
- `run_speed`, `idle_min_ms`, `idle_max_ms` and `run_max_ms` must be positive.
- `idle_max_ms` must be greater than or equal to `idle_min_ms`.
- Frame file names must be unique inside the mascot folder.

## ZIP implementation

The exporter writes standard ZIP archives using the `STORE` method (no compression). PNG images are already compressed, so extra DEFLATE compression would provide little value and would add an external dependency.

The importer supports:

- ZIP `STORE` entries directly.
- ZIP `DEFLATE` entries when the browser provides `DecompressionStream('deflate-raw')`.

The ZIP parser reads the central directory and does not execute or extract files to the user's filesystem.

## Preview model

The simulation uses the same design targets documented for the future client implementation:

```text
screen:       960 × 544
safe margin:  16 px
sprite:       100 × 100
states:       Idle / Run
movement:     normalized vector movement
orientation:  horizontal mirror based on native_facing
```

Run destinations are kept inside the safe area. A minimum useful destination distance is applied to avoid tiny movements.

## Export result

For an ID such as `vitacat`, the generated archive is:

```text
vitacat.zip
└── vitacat/
    ├── mascot.json
    ├── idle_01_00.png
    ├── idle_01_01.png
    ├── run_01_00.png
    └── run_01_01.png
```

This is intended to be copied to the future client asset location:

```text
Client PSVitaAlive/assets/mascots/vitacat/
```

The current implementation of this web tool does **not** modify or require that client path to exist yet.

## Maintenance rule

Keep this tool aligned with the future mascot manifest contract. If the mascot schema is extended later, add a new `schema_version` path rather than silently changing version 1 semantics.
