# Mascot Generator — Smart Sprite Sheet Splitter

## Purpose

The Sprite Sheet Splitter is an optional authoring helper inside the PSVitaAlive Mascot Generator. It lets a user start from a complete Sprite Sheet instead of manually preparing every PNG frame.

The normal user should not need to understand connected components, pixel-count thresholds, row thresholds or bounding-box dimensions. The default workflow is intentionally simple:

```text
Load Sprite Sheet
      ↓
if needed: Remove solid background
      ↓
Tap background once
      ↓
Automatic Smart detection
      ↓
Review/select frames
      ↓
Idle / Run animation
      ↓
normal mascot preview + ZIP export
```

Everything is processed locally in the browser. No image is uploaded to PSVitaAlive or another server.

## User workflow

### Transparent Sprite Sheet

1. Press **Load Sprite Sheet**.
2. Leave **Detection mode** on **Automatic — recommended**.
3. Smart detection runs automatically.
4. Review the detected frames.
5. Select the frames wanted for the current animation.
6. Choose Idle or Run and the target animation.
7. Press **Add selected to animation**.

### Solid-color background

1. Press **Load Sprite Sheet**.
2. Enable **Remove solid background**.
3. Tap/click **once** on a clean part of the background.
4. The page samples a 5 × 5 neighborhood around the touched point.
5. It chooses a safe RGB tolerance automatically.
6. It creates a temporary transparent working copy.
7. Smart detection runs again automatically.
8. Review/select the resulting frames.

No dragging or rectangle selection is required.

## Simplified detection modes

The main UI exposes four modes.

### Automatic — recommended

This is the default and should work for most game Sprite Sheets.

It estimates useful values from the current sheet itself:

- typical frame width;
- typical frame height;
- typical opaque-pixel count;
- safe detached-piece merge distance;
- minimum useful frame size;
- maximum useful frame size;
- row grouping distance.

Users normally should not open Expert settings.

### Sensitive

Use this when Automatic skips several small frames or detached effects/accessories.

Sensitive mode:

- accepts smaller components;
- allows a slightly larger detached-piece merge distance;
- tolerates a wider range of frame sizes.

### Strict

Use this when Automatic finds too many decorations, particles or noise.

Strict mode:

- rejects more tiny components;
- uses a smaller merge distance;
- accepts a narrower range of frame sizes.

### Expert

Expert mode restores manual control over the technical parameters:

- minimum opaque pixels;
- maximum opaque pixels;
- minimum component dimension;
- maximum component dimension;
- row threshold;
- detached-piece merge distance.

These values are deliberately hidden under **Expert detection settings (usually not needed)**.

## Smart detection algorithm

The default detector no longer assumes that one 4-way connected component must always equal one visual sprite.

The pipeline is:

1. Decode the transparent working PNG.
2. Treat pixels with `alpha > 0` as foreground.
3. Find raw foreground components using **8-direction connectivity**:

```text
↖ ↑ ↗
← X →
↙ ↓ ↘
```

4. Measure each raw component.
5. Estimate typical Sprite Sheet dimensions and pixel counts.
6. Merge nearby disconnected pieces when the merge remains inside a safe frame-sized bounding box.
7. Apply mode-specific automatic filtering.
8. Group accepted frames into rows using their vertical centers.
9. Sort each row left-to-right.
10. Extract the frame to a transparent square canvas using nearest-neighbour scaling.

This is more tolerant of pixel-art sprites whose pieces become disconnected after background cleanup or which naturally contain detached parts.

## Solid-background cleanup

Background removal remains a preprocessing step. The original uploaded file is always kept untouched in browser memory.

```text
original Sprite Sheet
        │
        ├── kept untouched
        │
        ↓
local Canvas working copy
        ↓
background cleanup
        ↓
transparent temporary PNG
        ↓
Smart Sprite Sheet detector
```

### One-tap sample

A tap/click samples a 5 × 5 neighborhood and averages its opaque RGB values.

The cleanup tolerance is chosen automatically from that sample, with a conservative default floor. The manual tolerance control still exists under **Background cleanup settings (usually not needed)**.

### Edge-connected cleanup

The safe default removes matching background pixels connected to the image edges. This helps avoid deleting a similar color that exists only inside the character.

### Dark-outline protection

Black and very dark backgrounds are common in old pixel-art sheets, while the sprite itself often uses black outlines too.

For a very dark sampled background, the cleanup stage performs one conservative outline-recovery pass after background removal. Removed dark pixels directly surrounded by surviving foreground may be restored before Smart detection.

The goal is not to reconstruct arbitrary artwork. It only protects likely one-pixel dark edges so characters do not become unnecessarily fragmented.

## Detecting an opaque background

If Smart detection sees one foreground component covering most of the sheet, it assumes the source probably still has an opaque background.

Instead of returning a confusing result, the UI tells the user to:

```text
Enable Remove solid background
→ tap the background once
```

## Add missed sprite

Automatic detection can never perfectly understand every historical Sprite Sheet. The fallback is designed for normal users rather than requiring numeric tuning.

1. Press **Add missed sprite**.
2. Tap/click the missing visual frame in the detected-sheet preview.
3. The splitter finds the nearest raw foreground component.
4. Nearby foreground pieces are grouped using a more permissive local distance.
5. If that area already belongs to a detected frame, that frame is simply selected.
6. Otherwise a new frame is generated and inserted back into spatial order.

The user can cancel the mode with the same button.

## Preview colors

In the detected Sprite Sheet preview:

- green: normally detected/selected frame;
- yellow: unusual frame worth reviewing;
- blue: frame recovered with **Add missed sprite**;
- gray: unselected frame.

The numbered boxes use the same final ordering as the extracted PNG list.

## Automatic ordering

Frames are ordered:

1. top-to-bottom by detected row;
2. left-to-right inside each row.

This preserves the common layout used by game Sprite Sheets while still allowing individual frames to be deselected before adding them to an animation.

The extracted-frame grid no longer uses the previous short internal viewport limit, so users do not mistake hidden rows for missing detections.

## Output frames

The default output canvas remains `64 × 64` and can be changed up to `100 × 100`.

Each detected crop is scaled uniformly:

```text
scale = min(outputSize / cropWidth, outputSize / cropHeight)
```

The result is centered in a transparent square and rendered with image smoothing disabled, preserving crisp pixel art.

The aspect ratio is never stretched.

## Relationship with mascot.json

The Sprite Sheet is only an authoring input.

Smart detection does **not** change `mascot.json` schema version 1. Final packages still contain ordinary individual PNG frames:

```text
<mascot-id>/
├── mascot.json
├── sprite_001.png
├── sprite_002.png
└── ...
```

The PS Vita client does not need Sprite Sheet support and does not know how the original frames were produced.

## Direct animation integration

Pressing **Add selected to animation** passes generated PNG files into the existing Mascot Generator frame input. Therefore the existing generator remains authoritative for:

- PNG validation;
- unique frame names;
- frame ordering;
- animation timing;
- 100 × 100 logical mascot-area rules;
- Vita preview;
- final mascot ZIP export.

## Standalone sprites ZIP

**Download selected sprites ZIP** remains available for users who only want the extracted PNG files.

```text
prefix_sprites.zip
├── prefix_001.png
├── prefix_002.png
└── ...
```

## Reference test case

The Smart detector was designed and checked against a dense historical Mario pixel-art sheet during this revision. That sheet includes:

- an opaque black background;
- near-black color variations;
- black character outlines;
- many rows of frames;
- small and large poses;
- hammers, capes and other detached-looking accessories;
- narrow/tall frames;
- irregular frame dimensions.

The reference sheet is used to validate the algorithm shape, not to hardcode Mario-specific values. Automatic mode derives thresholds from each loaded sheet.

## Performance and memory

Detection runs only when:

- a Sprite Sheet is loaded;
- background cleanup produces a new transparent working image;
- **Smart detect** is pressed;
- Detection mode changes;
- output size changes;
- Expert values change while Expert mode is active.

The algorithm is not part of the PS Vita runtime.

Temporary browser memory can contain:

- the decoded source Sprite Sheet;
- the transparent working copy;
- an RGBA analysis buffer;
- visited/queue typed arrays;
- extracted PNG bytes and object URLs.

Object URLs are revoked when the sheet is replaced or cleared.

## Troubleshooting

### It says Solid background detected

Enable **Remove solid background** and tap the background once.

### Automatic misses a few frames

First use **Add missed sprite** and tap each missing frame.

If many frames are missing, switch Detection mode to **Sensitive**.

### Automatic detects decorations or noise

Deselect those frames manually or switch Detection mode to **Strict**.

### Background cleanup still leaves a halo

Open **Background cleanup settings (usually not needed)** and increase Color tolerance slightly.

### Background cleanup removes too much

Reduce Color tolerance. Keep edge-connected cleanup enabled unless the sheet specifically requires global color removal.

### A very unusual sheet still fails

Use **Expert** mode only after Automatic/Sensitive/Strict and Add missed sprite have been tried.

## Scope boundaries

This feature remains web-only. It does not modify:

```text
Client PSVitaAlive/
apps/
authors/
categories/
catalog.json
authors.json
categories.json
mascot.json schema version 1
```

Files involved:

```text
web/tools/mascot-generator/sprite-sheet-splitter.js
web/tools/mascot-generator/sprite-sheet-background-removal.js
web/tools/mascot-generator/SPRITE_SHEET_SPLITTER.md
web/tools/mascot-generator/README.md
```
