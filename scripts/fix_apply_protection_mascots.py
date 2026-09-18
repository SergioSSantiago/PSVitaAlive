#!/usr/bin/env python3
from pathlib import Path

path = Path(__file__).with_name("apply_protection_mascots.py")
text = path.read_text(encoding="utf-8")
old = '''replace_once(ui_cpp, "    for (int i = 0; i < 10; ++i) {\\n        if (opts[i].sectionStart", "    for (int i = 0; i < 11; ++i) {\\n        if (opts[i].sectionStart", "settings measured rows")'''
new = '''replace_once(
    ui_cpp,
    "    int measured = 0;\\n    for (int i = 0; i < 10; ++i) {\\n        if (opts[i].sectionStart",
    "    int measured = 0;\\n    for (int i = 0; i < 11; ++i) {\\n        if (opts[i].sectionStart",
    "settings measured rows",
)'''
count = text.count(old)
if count != 1:
    raise SystemExit(f"expected exactly one patch-script guard to tighten, found {count}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("Mascot integration patch guard tightened")
