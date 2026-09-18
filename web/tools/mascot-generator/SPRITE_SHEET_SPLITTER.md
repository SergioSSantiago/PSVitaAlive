# Mascot Generator — Sprite Sheet Splitter

## Purpose

This feature extends the web-only PSVitaAlive Mascot Generator so users do not need pre-separated PNG frames.

A user can load a transparent PNG Sprite Sheet, detect the individual sprites in the browser, review the cuts, choose which sprites to keep, and send those generated frames directly into an existing Idle or Run animation.

The implementation is fully client-side and does not upload the Sprite Sheet or generated sprites to any server.

## Source process reproduced in the browser

The browser implementation follows the same process as the Python `sprite_splitter.py` reference used during the original PSVitaAlive mascot work:

1. Load the Sprite Sheet as RGBA.
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

## Default detection parameters

The defaults intentionally match the supplied Python tool:

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

## Transparency requirement

Automatic component detection assumes a transparent Sprite Sheet.

The foreground mask is:

```text
alpha > 0
```

If the source image has an opaque background, that background becomes one large connected component and automatic extraction will not work correctly. The source should be converted to transparent PNG first.

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

1. Open the Mascot Generator.
2. Complete Identity and Behaviour as usual.
3. In **Sprite Sheet Splitter**, choose **Load Sprite Sheet**.
4. The browser automatically detects and extracts sprites using the default filters.
5. Review the green detection boxes over the original sheet.
6. Review the individual extracted sprites below the sheet.
7. Click individual sprites to include/exclude them, or use **Select all** / **Select none**.
8. If detection is wrong, adjust the advanced filters and press **Re-detect**.
9. Choose:
   - target state: Idle or Run;
   - target animation.
10. Press **Add selected to animation**.
11. The generated PNG files are passed directly into the existing mascot animation editor.
12. Continue configuring animation timing and preview the mascot normally.
13. Export the final mascot ZIP using the existing generator.

## Direct integration with the animation editor

The splitter intentionally remains separate from the mascot project data until the user chooses **Add selected to animation**.

This has several advantages:

- the original Sprite Sheet is never included in the mascot package;
- rejected components consume no mascot texture memory;
- the user can send different selections to different Idle/Run animations;
- the existing mascot validation and export pipeline remains authoritative;
- no duplicate animation/export implementation is introduced.

The integration passes generated PNG files into the same frame input already used by the mascot editor, so all existing rules still apply:

- unique filenames;
- PNG validation;
- frame ordering;
- Vita preview;
- final mascot ZIP generation.

## Selection and visual verification

After detection:

- accepted components are drawn as boxes over the original Sprite Sheet;
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

Detection is performed only when:

- a Sprite Sheet is loaded;
- **Re-detect** is pressed;
- a detection/output parameter is changed.

It is not performed every animation frame and has no relationship with the PS Vita runtime.

The browser temporarily keeps:

- the original decoded Sprite Sheet;
- one alpha/visited analysis buffer while detecting;
- PNG bytes and object URLs for accepted extracted sprites.

Generated object URLs are revoked when the Sprite Sheet is replaced or cleared.

Very large Sprite Sheets can consume significant browser memory because Canvas must decode the complete RGBA image. This tool is intended for normal game Sprite Sheets rather than massive image atlases.

## Error cases

### No sprites detected

Possible causes:

- Sprite Sheet has an opaque background;
- minimum pixel count is too high;
- maximum pixel count is too low;
- minimum dimensions are too high;
- maximum dimensions are too low;
- sprites are composed of multiple disconnected pieces.

Adjust the filters and run detection again.

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

The Sprite Sheet is an authoring input only; PSVitaAlive on PS Vita continues to consume the same individual PNG frames generated by the existing mascot package format.

## Files

```text
web/tools/mascot-generator/index.html
web/tools/mascot-generator/sprite-sheet-splitter.css
web/tools/mascot-generator/sprite-sheet-splitter.js
web/tools/mascot-generator/SPRITE_SHEET_SPLITTER.md
```

The existing `mascot-generator.js` remains the owner of mascot project state, animation editing, preview, validation and final package generation.
