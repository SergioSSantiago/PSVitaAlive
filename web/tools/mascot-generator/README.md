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
- Split complete Sprite Sheets into individual PNG frames directly in the browser.
- Accept Sprite Sheets that are already transparent or have a solid-color background.
- Remove a solid background with one tap/click on a clean background area.
- Automatically choose a background-color tolerance from the 5 × 5 sample.
- Protect likely dark pixel-art outlines when cleaning a black/very-dark background.
- Use Smart Sprite Detection by default instead of requiring manual technical thresholds.
- Detect foreground using 8-direction connectivity and safely group nearby detached pieces.
- Offer simple Automatic, Sensitive and Strict detection modes.
- Keep numeric threshold controls under Expert settings for exceptional sheets.
- Recover a missed frame with **Add missed sprite** and a single tap on the preview.
- Send selected extracted sprites directly to any Idle or Run animation.
- Download selected extracted sprites as a standalone ZIP when desired.
- Create multiple Idle and Run animations.
- Reorder frames with buttons or drag and drop.
- Configure frame timing, Idle range, Run timeout and movement speed.
- Validate required fields, PNG assets, duplicate frame names and missing assets.
- Keep PNGs at or below 100 × 100 unchanged.
- Automatically normalize oversized PNGs down to fit within 100 × 100 while preserving aspect ratio.
- Preview the mascot inside a 960 × 544 PS Vita simulation.
- Simulate automatic Idle/Run transitions, diagonal movement and horizontal sprite mirroring.
- Force Idle or Run in the preview for testing.
- Show optional safe-area, sprite-bound and run-target overlays.
- Export `mascot.json` alone.
- Export a ready ZIP containing `<id>/mascot.json` and `<id>/*.png`.

## Privacy / hosting

The tool is fully client-side and works on GitHub Pages. Imported files are read locally by the browser and are not uploaded anywhere.

Sprite Sheet cleanup and detection are also local. The original source remains untouched; temporary working images and extracted frames only exist in browser memory.

No server, database or API is required.

## Sprite Sheet workflow

For most users the optional authoring flow is intentionally short:

```text
Sprite Sheet PNG
      ↓
optional: Remove solid background
      ↓
one tap on background
      ↓
Automatic Smart detection
      ↓
select frames
      ↓
Idle / Run animation
      ↓
normal mascot preview + validation + ZIP export
```

For transparent sheets, background cleanup is skipped.

For solid-background sheets:

1. Load the Sprite Sheet.
2. Enable **Remove solid background**.
3. Tap/click once on a clean background area.
4. The browser samples a 5 × 5 neighborhood and chooses a safe tolerance automatically.
5. A transparent working PNG is generated locally.
6. Smart detection runs automatically.
7. Review/select frames and send them to an animation.

Users normally leave Detection mode on **Automatic — recommended**. If needed:

- **Sensitive** finds smaller/detached frames;
- **Strict** ignores more noise;
- **Add missed sprite** lets the user tap one skipped frame directly;
- **Expert** exposes the technical thresholds.

Detailed behavior is documented in:

```text
SPRITE_SHEET_SPLITTER.md
```

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
- `width: 100` and `height: 100` describe the logical mascot display area, not a mandatory source-PNG resolution.
- Frames at or below `100 × 100` are kept byte-for-byte unchanged (for example `64 × 64`).
- Frames larger than the logical area are automatically normalized down so neither dimension exceeds 100 px, preserving aspect ratio.
- During preview, every frame is fitted inside the logical `100 × 100` area and scaled as large as possible without stretching; for example, a `64 × 64` frame renders as `100 × 100`, while a `64 × 48` frame renders as `100 × 75` and is centered.
- `native_facing` is `left` or `right`.
- At least one Idle animation and one Run animation are required.
- Every animation requires a positive `frame_ms` and at least one frame.
- `run_speed`, `idle_min_ms`, `idle_max_ms` and `run_max_ms` must be positive.
- `idle_max_ms` must be greater than or equal to `idle_min_ms`.
- Frame file names must be unique inside the mascot folder.

Sprite Sheet authoring does **not** extend or modify this schema. Final mascot packages still contain individual PNG frames.

## ZIP implementation

The mascot exporter writes standard ZIP archives using the `STORE` method (no compression). PNG images are already compressed, so extra DEFLATE compression would provide little value and would add an external dependency.

The mascot importer supports:

- ZIP `STORE` entries directly.
- ZIP `DEFLATE` entries when the browser provides `DecompressionStream('deflate-raw')`.

The ZIP parser reads the central directory and does not execute or extract files to the user's filesystem.

The Sprite Sheet helper can also generate a standalone ZIP containing only selected extracted PNG frames.

## Preview model

The mascot simulation uses the same design targets as the PS Vita client:

```text
screen:       960 × 544
safe margin:  16 px
mascot area:  100 × 100
source PNG:   flexible; ≤100 kept, >100 normalized down
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

Built-in mascots can be placed in:

```text
Client PSVitaAlive/assets/mascots/vitacat/
```

User-installed mascots can use the same folder format under:

```text
ux0:data/psvitaalive/mascots/vitacat/
```

The web generator itself only creates the package; it does not write to either PS Vita location.

## Maintenance rule

Keep this tool aligned with the mascot manifest contract. If the mascot schema is extended later, add a new `schema_version` path rather than silently changing version 1 semantics.
