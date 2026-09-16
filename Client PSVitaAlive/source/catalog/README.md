# `source/catalog/` — Catalog manager

Loads public JSON catalogs from the PS Vita Alive Store repository (or configured URLs).

## Responsibilities

- Download / validate cache (ETag / validators when available)
- Parse application records for Homebrew and commercial catalogs
- Keep **validated catalogs in RAM** after first successful load (fast tab switch)
- Download the separate **Vita zRIF index** when loading Vita Games
- Expose ready state to UI and startup flow
- Coordinate with startup update check ordering when enabled
- Attach **internal image-cache identity metadata** to parsed icon/cover/screenshot URLs for the native client

## Files

| File | Role |
|------|------|
| `catalog_manager.cpp` | Orchestration, disk + RAM cache, zRIF index download |
| `catalog_parser.cpp` | JSON → in-memory records / links; zRIF stays outside the JSON RAM model; also tags parsed image URLs with internal cache identity metadata |

## Catalogs

| Type | Remote file | Image-cache prefix |
|------|-------------|-------------------|
| Homebrew | `catalog.json` | `H` |
| Vita Games | `catalog_psvita_games.json` | `PV` |
| PSP | `catalog_psp_games.json` | `PSP` |
| PS1 | `catalog_ps1_games.json` | `PS1` |

## Image-cache identity handoff

The parser participates in the image cache without changing the public catalog format.

For every parsed media resource it computes a stable identity from:

```text
catalog prefix + (title_id when available, otherwise id) + image role
```

Roles are resource-specific (`icon`, `cover`, `shot0`, `shot1`, ...). The identity is hashed with 64-bit FNV-1a.

The parser then adds an **in-memory-only** tag to the image URL:

```text
#psva_cache=<catalog>:<resource-key>
```

or `&psva_cache=...` if the URL already has a fragment.

Example:

```text
https://example.org/icon-v2.png#psva_cache=H:7F31A820D4C9E112
```

Important rules:

- this tag is never written back to `apps/*.json` or generated catalogs;
- it is not a schema field and must not become one;
- `ImageCache` strips the tag before libcurl sees the URL;
- the stable resource key stays the same when only the image URL changes;
- the URL hash changes, allowing the cache to distinguish current vs superseded versions of the same resource.

This is what allows a changed image to be replaced individually without scanning/cleaning an entire catalog.

See [`../../../docs/IMAGE_CACHE.md`](../../../docs/IMAGE_CACHE.md) for the complete v3 cache design, disk layout, replacement rules and startup size limit.

### Why the identity belongs in parser output

The parser already knows all three pieces needed to build a stable resource identity:

1. which catalog is being parsed;
2. which app/game owns the image;
3. which image role/slot is being assigned.

Passing that identity as internal URL metadata avoids adding cache-specific parameters throughout `FullCatalogScreen` and other UI call sites.

The UI still consumes ordinary string fields; only `ImageCache` interprets the private `psva_cache` fragment.

## zRIF sidecar (Vita Games)

Used by **BGDL PKG installs** on real hardware (verified). Index is keyed by **content_id** (not URL).

License strings are **not** stored inside `catalog_psvita_games.json` (avoids OOM when all four catalogs stay in memory).

| Item | Location |
|------|----------|
| Remote | `catalog_psvita_games.zrifidx` (repo root) |
| Device cache | `ux0:data/psvitaalive/cache/catalog/catalog_psvita_games.zrifidx` |
| Line format | `content_id<TAB>zrif` |

`CatalogManager` downloads the index when the Vita Games catalog is loaded (if missing/too small).  
`LicenseHelper` resolves a zRIF at **install time** only: exact `content_id` match first, then Title ID fallback. See `source/installer/README.md`.

## Memory notes

- Multi-catalog **RAM cache** is intentional for UX after startup.
- Heavy fields (long descriptions / changelogs) may be trimmed at parse time.
- UI browse path should avoid duplicating the full list while search is empty (`catalogView()`).
- Image-cache tagging adds only a small fragment to media URL strings; it does not load image binaries into catalog RAM.
- The image cache itself is disk-backed and downloaded on demand.

## Compatibility

Optional JSON fields may be missing. Parser must use safe defaults and keep loading.

Media URLs may be HTTP(S); failures must not block catalog readiness.

Image-cache metadata is deliberately internal so older/newer public catalog data remains compatible. The official data architecture remains unchanged:

```text
apps/ + authors/ + categories/
        ↓
GitHub Actions
        ↓
catalog.json + authors.json + categories.json
        ↓
Web + Client
```

## License lookup (install time)

The catalog JSON does **not** embed zRIF strings. The client downloads `catalog_psvita_games.zrifidx` when Vita Games is loaded.

| Step | Key |
|------|-----|
| 1 (preferred) | Link field `content_id` → exact line in `.zrifidx` |
| 2 (fallback) | Title ID from URL/path (e.g. `PCSB00040`) → first key containing `-TITLEID_` |
| 3 | No match → PKG install fails with a clear license error (no raw `.pkg` promote) |

Each region / DLC / update should expose its own `content_id` on the link so the correct license is used.
