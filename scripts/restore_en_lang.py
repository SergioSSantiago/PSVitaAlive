#!/usr/bin/env python3
"""Restore Client PSVitaAlive/assets/lang/en.lang from embedded base64."""
import base64
import pathlib
import sys

# Minimal embedded: only ensures INSTALL_STATE_INSTALLED_UNKNOWN exists without wiping the file.
# Prefer copying from the build tree if available.

def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    path = root / "Client PSVitaAlive" / "assets" / "lang" / "en.lang"
    if not path.exists():
        print("en.lang missing at", path, file=sys.stderr)
        return 1
    text = path.read_text(encoding="utf-8", errors="replace")
    if text.strip() in ("PLACEHOLDER_EN", "PLACEHOLDER") or len(text) < 500:
        print("en.lang looks corrupted/truncated; restore from release tree:", file=sys.stderr)
        print("  artifacts/psva_update_release/Client PSVitaAlive/assets/lang/en.lang", file=sys.stderr)
        return 2
    line = "INSTALL_STATE_INSTALLED_UNKNOWN=Installed · version unknown"
    if "INSTALL_STATE_INSTALLED_UNKNOWN" not in text:
        key = "INSTALL_STATE_NOT_INSTALLED="
        idx = text.find(key)
        if idx < 0:
            text = text.rstrip() + "\n" + line + "\n"
        else:
            end = text.find("\n", idx)
            text = text[: end + 1] + line + "\n" + text[end + 1 :]
        path.write_text(text, encoding="utf-8")
        print("injected", line)
    else:
        print("already present")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
