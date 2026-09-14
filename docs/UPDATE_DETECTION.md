# Reliable Homebrew Update Detection (PSVitaAlive)

## Problem
Comparing catalog `version` to installed `APP_VER` produces false **Update available** badges when developers never bump `APP_VER` (often stuck at `00.00`).

## Design (hybrid evidence)
Priority:
1. **PSVitaAlive receipt** (valid only if on-disk fingerprint still matches)
2. **Catalog fingerprints** (`update_detection` signatures / known_releases)
3. **SFO** only under explicit policy

### States
| State | Meaning |
|-------|---------|
| NotInstalled | No `ux0:app/TITLEID` |
| Installed | Positive evidence of current catalog release |
| UpdateAvailable | Positive evidence of a known *older* release |
| InstalledUnknown | Installed, but release identity not proven |

**Absolute rules**
- Hash mismatch ≠ UpdateAvailable
- SFO mismatch ≠ UpdateAvailable (unless `sfo_policy=trusted`)
- Nightlies / forks / unknown builds → InstalledUnknown (never auto-downgrade)

### Default SFO policy = `fallback`
Even without `update_detection` metadata, APP_VER alone never forces UpdateAvailable.

### Receipts
Path: `ux0:data/psvitaalive/installed/<TITLE_ID>.json`  
Written only after successful install (atomic tmp+rename).  
Invalidated when verification fingerprint no longer matches disk.

### Modules
- `include/update/install_state.hpp`
- `include/update/update_decision.hpp` + `source/update/update_decision.cpp`
- `include/update/installed_release_tracker.hpp` + `source/update/installed_release_tracker.cpp`
- Host tests: `tests/test_update_decision.cpp`

### Optional catalog field (future population)
```json
"update_detection": {
  "revision": 4,
  "sfo_policy": "fallback",
  "signatures": [{ "path": "eboot.bin", "algorithm": "sha256", "digest": "..." }],
  "known_releases": []
}
```
Optional; apps without it remain valid.

### UI integration note
`Client PSVitaAlive/source/ui/full_catalog_screen.cpp` on GitHub remains a size stub (`RESTORE_IN_PROGRESS`).
The production UI source used for builds lives in the project worktree and was updated so that:
- `queryLocalInstall` no longer maps APP_VER mismatch → UpdateAvailable
- mismatch / placeholder → `InstalledUnknown`
- badges/detail show the unknown state

Full fingerprint hashing workers + parser/`update_detection` propagation + install-success receipt hooks are the next layer once the UI tree is fully restored on GitHub.

### Tests
```bash
g++ -std=c++17 -I"Client PSVitaAlive/include" \
  tests/test_update_decision.cpp \
  "Client PSVitaAlive/source/update/update_decision.cpp" \
  -o /tmp/test_ud && /tmp/test_ud
```
All pure-decision cases (A–K style) pass on host.
