# Protection-screen mascots

## Status

Implemented by the PS Vita client for the existing OLED / long-operation protection screen.

The mascot subsystem is presentation-only. It does **not** change download, extraction, installation, cancellation, power-lock, keep-awake or catalog logic.

## Sources

The client combines two dynamic roots:

```text
app0:mascots/
ux0:data/psvitaalive/mascots/
```

- `app0:mascots/` contains mascots packaged inside the PSVitaAlive VPK.
- `ux0:data/psvitaalive/mascots/` contains user-installed mascots and is created automatically when needed.

Each direct child folder is one mascot:

```text
<root>/<id>/
├── mascot.json
├── idle_01_00.png
├── idle_01_01.png
├── run_01_00.png
└── ...
```

The folder name is the stable mascot ID. The visible name comes from `mascot.json`.

## Settings

The saved key is:

```json
"mascot_selection": "random"
```

Supported values:

```text
random
  Pick one valid mascot whenever the protection screen enters.

off
  Keep the existing protection screen without a mascot.

internal:<id>
  Use a specific VPK mascot.

user:<id>
  Use a specific mascot from ux0:data/psvitaalive/mascots/.
```

`random` is the default for new installations and for existing configurations that do not yet contain `mascot_selection`.

Internal and user IDs are source-qualified internally, so a user mascot may have the same folder ID as an internal mascot without silently replacing it.

Settings rescans both roots when the Settings screen is opened. This lets a user copy a new mascot to `ux0:` and then open Settings to make it appear in the selector without rebuilding PSVitaAlive.

## Random behavior

`Random` selects across all valid internal and user mascots each time the protection screen actually becomes active.

When more than one valid mascot exists, the runtime tries not to repeat the immediately previous Random mascot. This is a preference rather than a hard requirement; invalid/corrupt packages can be skipped during loading.

Dismissing the protection screen and allowing it to enter again starts a fresh mascot session and therefore performs a fresh Random choice.

## Manifest schema v1

The web Mascot Generator exports the supported format:

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

`native_facing` accepts `left` or `right` and describes the original horizontal direction of the supplied art. The runtime mirrors the current frame horizontally when movement requires the opposite direction.

## Logical size versus PNG size

The manifest values:

```json
"width": 100,
"height": 100
```

are the **logical protection-screen box**, not a requirement that every PNG be physically 100 × 100.

Examples:

```text
64 × 64   -> displayed as 100 × 100
64 × 48   -> displayed as 100 × 75, centered vertically
256 × 128 -> displayed as 100 × 50, centered vertically
```

The client always preserves the PNG aspect ratio and fits it inside the logical 100 × 100 box. Movement and screen-edge checks use the logical box, so artwork stays inside the safe area even when the visible pixels occupy less than the full box.

## Runtime states

The first implementation has two states:

```text
Idle
Run
```

### Idle

- Chooses one Idle animation.
- Keeps the logical position fixed.
- Loops its PNG frames using `frame_ms`.
- Duration is random between `idle_min_ms` and `idle_max_ms`.
- When several Idle animations exist, the runtime prefers not to immediately repeat the previous one.
- When Idle finishes, the next state is selected again.

### Run

- Chooses one Run animation.
- Chooses a destination inside the 16 px safe margin.
- Uses normalized vector movement, so diagonal movement is not faster than horizontal movement.
- `run_speed` is pixels per second and movement uses elapsed time rather than pixels per frame.
- Horizontal movement controls facing direction.
- Run ends when the destination is reached or `run_max_ms` expires.
- A new state is then selected.

## Protection-screen lifecycle

The existing protection screen still controls when the feature exists:

```text
long active operation
        ↓
60-second protection delay
        ↓
protection screen enters
        ↓
MascotManager starts one session
        ↓
Idle / Run updates every UI frame
        ↓
operation phase ends, user dismisses, failure/cancel/completion
        ↓
MascotManager stops and frees its textures
```

Mascot PNG loading and texture freeing are serviced from the main UI thread, outside an active vita2d drawing scene. Download/install worker callbacks only update their existing progress state and never perform mascot GPU work.

The render order is:

```text
pure black protection background
mascot
progress / phase / ETA text
```

The progress information therefore remains readable if a mascot travels behind it.

## Memory policy

The discovery list keeps only lightweight metadata.

The client does **not** load the PNG textures for every available mascot. Only the mascot selected for the current protection session is loaded. Those textures are released when the session ends.

This intentionally avoids using the catalog `ImageCache`, so mascot assets cannot evict catalog icons or screenshots.

## Validation and defensive limits

Invalid packages are skipped instead of crashing the protection screen.

Schema v1 currently enforces:

- `schema_version == 1`.
- Visible name present and bounded.
- `native_facing` is `left` or `right`.
- Logical `width == 100` and `height == 100`.
- At least one Idle and one Run animation.
- Maximum 16 animations per state.
- Maximum 32 frames per animation.
- Maximum 64 referenced frames in one mascot.
- PNG frame names only; no `/`, `\\`, `:`, `..` or path traversal.
- All referenced PNG files must exist.
- `frame_ms`: 16–10000 ms.
- Positive `run_speed`, capped at 1000 px/s.
- Valid positive Idle range, capped at 120 seconds.
- Positive `run_max_ms`, capped at 60 seconds.
- Manifest file capped at 64 KiB.

If a configured explicit mascot disappears or becomes invalid, the runtime tries other valid mascots rather than failing the protection screen. If none can load, the original mascot-free protection screen continues normally.

## Installing a user mascot

1. Create/export the mascot with the PSVitaAlive web Mascot Generator.
2. Extract the generated ZIP.
3. Copy the complete `<id>` folder to:

```text
ux0:data/psvitaalive/mascots/<id>/
```

Example:

```text
ux0:data/psvitaalive/mascots/vitacat/mascot.json
ux0:data/psvitaalive/mascots/vitacat/idle_01_00.png
ux0:data/psvitaalive/mascots/vitacat/run_01_00.png
```

Do not copy only the PNG files; `mascot.json` is required.

After copying, open PSVitaAlive Settings. The selector rescans the folder and should show the mascot by the display name stored in its manifest.

## Built-in mascots

A built-in package uses exactly the same files under:

```text
Client PSVitaAlive/assets/mascots/<id>/
```

CMake packages that directory into `app0:mascots/`. Adding another valid built-in mascot therefore requires assets only, not a new hard-coded C++ entry.

## Logs

Useful entries begin with:

```text
[Mascot]
```

Examples include discovery count, rejected manifests, failed PNG loads, selected key and session start/stop.

## Test checklist

Test on Vita3K and, importantly, real PS Vita hardware:

- Existing config without `mascot_selection` defaults to Random.
- Random works with one mascot and multiple mascots.
- Random can select both internal and user packages.
- Specific internal and user selections persist after restart.
- Off restores the existing protection screen exactly.
- 64 × 64 and non-square sprites preserve aspect ratio.
- Left/right facing and horizontal mirror are correct.
- Idle loops and timing are correct.
- Run can move left/right and diagonally.
- No sprite logical box crosses the 16 px safe margin.
- Dismissing the protector consumes the input exactly as before.
- Download, extract, install, Install All, failure, cancellation and completion behavior remain unchanged.
- Repeated protection entries do not produce continuing texture/RAM growth.
- Corrupt/missing user packages are skipped safely.
- Removing the currently configured user mascot falls back safely on the next protection entry.
