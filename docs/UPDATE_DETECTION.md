# Reliable Homebrew Update Detection

## Fixed behavior
- APP_VER mismatch alone never shows Update available (default sfo_policy=fallback).
- New state: InstalledUnknown ("Installed · version unknown").
- Receipts after successful install: ux0:data/psvitaalive/installed/<TITLE_ID>.json
- Decision matrix: receipt > fingerprint > SFO (trusted only).

## Build
Use this tree's Client PSVitaAlive sources (especially full_catalog_screen.cpp) for the UI integration.
