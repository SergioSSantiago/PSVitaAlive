# Mascot Generator — Sprite Sheet Splitter

## Purpose

This feature extends the web-only PSVitaAlive Mascot Generator so users do not need pre-separated PNG frames.

A user can load a PNG Sprite Sheet, optionally remove a solid-color background with a one-tap color sample, detect the individual sprites in the browser, review the cuts, choose which sprites to keep, and send those generated frames directly into an existing Idle or Run animation.

The implementation is fully client-side. The original Sprite Sheet, the cleaned copy, extracted sprites and generated ZIP files remain in the browser and are not uploaded to any server.

## Authoring pipeline

The Sprite Sheet workflow is intentionally divided into two independent stages:

```text
Original Sprite Sheet
        ↓
Optional solid-background cleanup
        ↓
Transparent working PNG
        ↓
Connected-component Sprite Sheet Splitter
        ↓
Individual PNG frames
        ↓
Existing Mascot Generator animation editor
```

The cleanup stage does not modify the original file and does not change `mascot.json`. It creates a temporary transparent PNG and passes that PNG to the existing splitter through the same file-input path the splitter already understands.

This separation keeps the connected-component detector, frame extraction, Idle/Run editor, validation and final mascot ZIP pipeline unchanged.

## Source process reproduced in the browser

The connected-component splitter follows the same process as the Python `sprite_splitter.py` reference used during the original PSVitaAlive mascot work:

1. Load the working Sprite Sheet as RGBA.
2. Treat every pixel with alpha greater than zero as foreground.
3. Detect 4-way connected components.
4. Measure each component:
   - opaque pixel count;
   - width;
   - height;
   - horizontal center;
   - vertical center.
5. Filter components by pixel count and dimensions.
6. Sort remaining components from top to bottom.
7. Group them into rows using a configurable vertical-center threshold.
8. Sort every row from left to right.
9. Crop every accepted component.
10. Scale it uniformly into a square transparent output canvas using nearest-neighbour rendering.
11. Center the scaled sprite inside the square.
12. Name frames sequentially as `prefix_001.png`, `prefix_002.png`, etc.

The web implementation does not require Pillow, NumPy or SciPy. Canvas and typed arrays provide the equivalent browser-side pipeline.

## Solid-background removal

### Why it exists

Connected-component detection requires transparent separation between sprites. Many Sprite Sheets instead use a flat color such as white, black, green, blue or magenta as the background.

The optional **Remove solid background** stage converts those sheets into the transparent working PNG expected by the splitter.

### One-tap sampling

The user does not need to draw a rectangle.

After enabling background removal, a preview of the original Sprite Sheet appears. The user taps or clicks **once** on a clean part of the solid background.

The browser automatically samples a `5 × 5` pixel neighborhood centered around that point:

```text
radius: 2 pixels
sample: 5 × 5 maximum
```

Near image borders the sample is clipped safely to the available pixels.

Fully transparent pixels are ignored while averaging the sample. The resulting RGB average becomes the reference background color.

A green crosshair marks the sampled point and the UI shows the selected RGB value.

### Color tolerance

Exact RGB matching is often too strict because Sprite Sheets can contain anti-aliasing, subtle export differences or compression-like color variation even when the background looks visually flat.

The cleanup stage therefore uses an RGB Euclidean distance:

```text
distance² = (r-r0)² + (g-g0)² + (b-b0)²
```

A pixel is considered background-compatible when:

```text
distance² <= tolerance²
```

Default tolerance:

```text
24
```

The UI accepts values from `0` to `255`.

Recommended workflow:

1. Start with the default tolerance.
2. Increase it only if visible background halos remain.
3. Reduce it if colors belonging to the sprite begin disappearing.

Changing tolerance automatically rebuilds the cleaned PNG and sends it back through normal sprite detection.

### Edge-connected safety mode

By default, **Remove matching background connected to image edges only** is enabled.

This is the safer mode. A pixel must:

1. match the sampled color within tolerance; and
2. belong to a 4-way connected region reachable from one of the outer image edges.

A flood-fill starts from the complete image perimeter and removes only matching pixels it can reach.

This protects similarly colored details inside the character in many common cases.

Example:

```text
blue sheet background
blue detail inside character
```

If the internal blue detail is isolated from the outer background by non-matching sprite pixels, it remains intact.

### Removing all matching pixels

Some sheets contain background-colored holes fully enclosed by a sprite, for example the empty space between arms or inside a ring-shaped pose.

Those pixels are not connected to an outer image edge, so safety mode intentionally leaves them untouched.

For this case the user can disable edge-connected mode. The cleanup stage then turns **all** pixels matching the sampled color/tolerance transparent.

This is more aggressive and can also remove legitimate sprite details that share the background color, so visual inspection is recommended.

### Original image preservation

Background removal is non-destructive:

- the uploaded source File remains stored as the original;
- processing happens on a temporary Canvas copy;
- disabling background removal immediately sends the untouched original back to the splitter;
- **Reset background sample** discards the processed copy and restores the original;
- tapping another background location creates a new sample from the original, never from an already-modified image.

The original Sprite Sheet is never rewritten or downloaded over.

### Processed preview

The background cleanup preview switches from **original preview** to **processed preview** after a valid sample is applied.

The checkerboard behind the Canvas makes transparent areas visible.

The sample crosshair remains visible so the user knows which point produced the selected color.

The existing splitter preview below then shows the transparent working sheet together with detected component boxes.

## Default detection parameters

The component-detection defaults intentionally match the supplied Python tool:

```text
output size:       64 × 64
minimum pixels:    100
maximum pixels:    10000
minimum dimension: 20 px
maximum dimension: 120 px
row threshold:     30 px
```

The size checks preserve the Python behavior: a component must be strictly larger than the minimums and strictly smaller than the maximums.

All values can be adjusted from the **Advanced detection filters** section.

## Output size and PSVitaAlive compatibility

The default output is `64 × 64`, which works well with the current mascot system.

The web UI limits generated square frames to a maximum of `100 × 100`, matching the logical mascot area used by PSVitaAlive.

Scaling uses nearest-neighbour rendering so pixel-art sprites remain crisp.

Example:

```text
source crop: 42 × 56
output:      64 × 64 transparent canvas
sprite:      48 × 64 centered inside the canvas
```

The aspect ratio is never stretched.

## User workflow

### Sprite Sheet already transparent

1. Open the Mascot Generator.
2. Complete Identity and Behaviour as usual.
3. In **Sprite Sheet Splitter**, choose **Load Sprite Sheet**.
4. Leave **Remove solid background** disabled.
5. The browser detects and extracts sprites normally.
6. Review the detection and continue with selection/animation assignment.

### Sprite Sheet with a solid background

1. Load the Sprite Sheet.
2. Enable **Remove solid background**.
3. Tap or click once on a clean area of the background preview.
4. The tool samples a 5 × 5 neighborhood and shows the RGB color.
5. The background is removed locally using tolerance `24` by default.
6. The transparent result is automatically sent to the existing sprite detector.
7. Inspect the processed preview and detected boxes.
8. If needed:
   - tap a different background point;
   - change tolerance;
   - disable/enable edge-connected mode;
   - reset the sample.
9. Review the individual extracted sprites.
10. Click individual sprites to include/exclude them, or use **Select all** / **Select none**.
11. If component detection itself is wrong, adjust the advanced filters and press **Re-detect**.
12. Choose target state and target animation.
13. Press **Add selected to animation**.
14. Configure animation timing and preview the mascot normally.
15. Export the final mascot ZIP using the existing generator.

## Direct integration with the animation editor

The splitter intentionally remains separate from the mascot project data until the user chooses **Add selected to animation**.

This has several advantages:

- the original Sprite Sheet is never included in the mascot package;
- the temporary cleaned Sprite Sheet is never included either;
- rejected components consume no mascot texture memory;
- the user can send different selections to different Idle/Run animations;
- the existing mascot validation and export pipeline remains authoritative;
- no duplicate animation/export implementation is introduced.

Generated PNG files are passed into the same frame input already used by the mascot editor, so all existing rules still apply:

- unique filenames;
- PNG validation;
- frame ordering;
- Vita preview;
- final mascot ZIP generation.

## Selection and visual verification

After detection:

- accepted components are drawn as boxes over the transparent working Sprite Sheet;
- selected components use the PSVitaAlive green accent;
- every detected sprite receives its sequential index;
- extracted frames show:
  - filename;
  - detected row;
  - original crop dimensions;
  - opaque pixel count.

This lets users manually remove logos, effects or false positives before creating an animation.

## Separate sprite ZIP

The splitter can also export the selected generated PNGs as a standalone ZIP:

```text
prefix_sprites.zip
├── prefix_001.png
├── prefix_002.png
├── prefix_003.png
└── ...
```

The ZIP uses the STORE method. PNG files are already compressed, so additional DEFLATE compression is unnecessary for this helper export.

This standalone ZIP is optional. The normal workflow is to send frames directly to an Idle/Run animation and then download the final ready mascot ZIP.

## Memory and performance

Component detection is performed only when:

- a Sprite Sheet is loaded;
- background cleanup sends a new transparent working PNG;
- **Re-detect** is pressed;
- a detection/output parameter is changed.

Background cleanup is performed only when:

- a background point is sampled;
- tolerance changes;
- edge-connected mode changes;
- background removal is re-enabled with an existing sample.

Neither operation runs every animation frame and neither has any relationship with the PS Vita runtime.

For background cleanup the browser temporarily allocates:

- the decoded original Sprite Sheet;
- a full RGBA Canvas/ImageData working copy;
- a `Uint8Array` visited map in edge-connected mode;
- an `Int32Array` flood-fill queue in edge-connected mode.

After cleanup, the resulting PNG goes through the normal splitter pipeline.

Very large Sprite Sheets can consume significant browser memory because Canvas must decode and process the complete RGBA image. The feature is intended for normal game Sprite Sheets rather than massive atlases.

## Error cases

### Opaque background becomes one giant component

Enable **Remove solid background** and tap the background once. The cleaned transparent copy will automatically replace the opaque working image used by detection.

### Background halo remains

Increase **Color tolerance** gradually.

Do not immediately use very high values because colors close to the background can belong to the sprite.

### Part of the sprite disappears

Possible causes:

- tolerance is too high;
- the sprite itself uses a color close to the sampled background;
- aggressive all-matching-pixels mode is enabled.

Reduce tolerance and keep edge-connected mode enabled when possible.

### Background remains inside a closed hole

This is expected with edge-connected safety mode if that background region cannot reach the outer image perimeter.

Disable **Remove matching background connected to image edges only** to remove every matching pixel.

### Wrong color sampled

Tap another clean background area. Every tap samples from the untouched original image.

Use **Reset background sample** to return to the original sheet and clear the current color.

### No sprites detected

Possible causes:

- solid background removal was not enabled for an opaque sheet;
- minimum pixel count is too high;
- maximum pixel count is too low;
- minimum dimensions are too high;
- maximum dimensions are too low;
- sprites are composed of multiple disconnected pieces.

Adjust the cleanup or detection filters and run detection again.

### Too many tiny sprites

Increase:

```text
Minimum opaque pixels
Minimum component dimension
```

### Large logos are detected

Reduce:

```text
Maximum opaque pixels
Maximum component dimension
```

### Rows are mixed

Adjust **Row threshold**. The reference script recommends values around `20–50` for typical sheets.

### One visual frame becomes several components

Connected-component detection only understands pixels that physically touch through up/down/left/right adjacency. If a visual frame contains detached effects or accessories, they may be identified separately. The selection UI lets the user discard unwanted pieces, but combining disconnected parts automatically is outside this version's scope.

## Scope boundaries

This feature changes only the GitHub Pages mascot generator.

It does **not** modify:

```text
Client PSVitaAlive/
apps/
authors/
categories/
catalog.json
authors.json
categories.json
GitHub catalog generation
```

It also does not change `mascot.json` schema version 1.

The Sprite Sheet and cleaned working image are authoring inputs only. PSVitaAlive on PS Vita continues to consume the same individual PNG frames generated by the existing mascot package format.

## Files

```text
web/tools/mascot-generator/index.html
web/tools/mascot-generator/sprite-sheet-splitter.css
web/tools/mascot-generator/sprite-sheet-splitter.js
web/tools/mascot-generator/sprite-sheet-background-removal.css
web/tools/mascot-generator/sprite-sheet-background-removal.js
web/tools/mascot-generator/SPRITE_SHEET_SPLITTER.md
```

The existing `sprite-sheet-splitter.js` remains responsible for connected-component detection/extraction, and `mascot-generator.js` remains the owner of mascot project state, animation editing, preview, validation and final package generation.
