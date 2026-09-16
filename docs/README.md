# `docs/` — Project documentation

Supplementary documentation for architecture, pipelines and client behaviour.

## How to use this folder

1. Prefer **code and generated artifacts** as source of truth when docs drift.
2. Update the matching README next to the code when behaviour changes.
3. Keep long design/implementation notes here when they do not belong in a module README.
4. For client subsystems that cross more than one module (for example catalog parser + UI + startup), keep one detailed document here and link to it from the affected module READMEs.

## Documentation map

| Location | Topic |
|----------|--------|
| Root `README.md` | Project overview, public JSON API, multi-catalog, recommended Vita setup, download/install locks, commercial PKG routing, client feature summary |
| `docs/IMAGE_CACHE.md` | **Image cache v3**: per-resource identity, H/PV/PSP/PS1 scopes, 256 buckets, URL-change replacement, startup 200 MiB → ~40 MiB trim, loading-bar progress, localization and validation |
| `docs/MULTILANGUAGE.md` | Current UI localization architecture, packaged languages, system/manual selection, English fallback and startup localization ordering |
| `docs/NETWORK_TLS.md` | libcurl / OpenSSL / archive.org failover / optional mbedTLS |
| `docs/PLUGIN_UPDATES.md` | **Planned** remote plugin update system (manifest / versioned Plugin links) — deferred |
| `docs/UPDATE_DETECTION.md` | Installed/update version detection notes |
| `Client PSVitaAlive/README.md` | Native client overview, runtime data and subsystem behaviour |
| `Client PSVitaAlive/source/catalog/README.md` | Multi-catalog cache, zRIF sidecar and image-cache tagging responsibilities |
| `Client PSVitaAlive/source/installer/README.md` | VPK / BGDL PKG, Plugin + tai config, Adrenaline unpack, ZIP integrity, keep-awake + shell locks |
| `Client PSVitaAlive/source/ui/README.md` | Native UI, image cache integration, loading overlays, LOCKED UI, themes, fonts, i18n hooks, essential plugins modal |
| `Client PSVitaAlive/source/update/README.md` | Self-update (PSVAUPDT1) handoff rules |
| `apps/`, `authors/`, `categories/` | Canonical Homebrew data contracts |
| `scripts/` | Generation and validation |
| `sources/` | External feeds |
| `web/` | Website |
| `.github/workflows/` | CI / Pages |

## Image cache documentation rule

The authoritative high-level behaviour is documented in [`IMAGE_CACHE.md`](IMAGE_CACHE.md). When changing image-cache code, keep these surfaces synchronized:

```text
catalog_parser.cpp
        ↓
internal image identity/tag
        ↓
ImageCache v3
        ↓
startup maintenance + FullCatalogScreen progress
```

Do not add cache-only fields to the public catalog JSON schema. The cache metadata remains an in-memory client implementation detail.

## Change classification

When fixing a bug, identify the layer:

1. External acquisition  
2. Normalization / identity / merge  
3. Overrides  
4. Catalog generation / validation  
5. Website  
6. PS Vita client (network, install, UI, image cache, update)

Patch the responsible layer—not a generated catalog—whenever possible.

- [IMAGE_CACHE.md](IMAGE_CACHE.md) — client image cache v3 / disk policy / per-image replacement
- [MULTILANGUAGE.md](MULTILANGUAGE.md) — localization architecture and current packaged languages
- [NETWORK_TLS.md](NETWORK_TLS.md) — libcurl / OpenSSL / archive.org failover / optional mbedTLS
