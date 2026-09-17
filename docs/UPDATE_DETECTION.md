# Reliable Homebrew Update Detection

## Fixed behavior
- APP_VER mismatch alone never shows Update available (default sfo_policy=fallback).
- New state: InstalledUnknown ("Installed · version unknown").
- Receipts after successful install: ux0:data/psvitaalive/installed/<TITLE_ID>.json
- Decision matrix: receipt > fingerprint > SFO (trusted only).

## Build
Use this tree's Client PSVitaAlive sources (especially full_catalog_screen.cpp) for the UI integration.

## Catalog card presentation

Update detection and card presentation remain separate concerns. `queryLocalInstall()` / `decideInstallState()` continue to determine the state; the catalog renderer only presents that result.

- `Installed` → one localized `BADGE_INSTALLED` badge at the top-right.
- `InstalledUnknown` → the same installed badge on the card; detailed metadata keeps the version-unknown explanation.
- `UpdateAvailable` → one localized `BADGE_UPDATE` badge at the top-right with a subtle orange breathing glow.
- `NotInstalled` / `Unknown` → no card badge.

The previous second badge over the lower-left icon corner and the hardcoded `ON` / `UPD` abbreviations were removed. Card title width now reserves the badge area, and long localized text uses clipping/marquee rather than overlapping app information.
