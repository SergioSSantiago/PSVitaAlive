#!/usr/bin/env python3
"""Compatibility wrapper for the one-shot download hardening patch.

The base patch intentionally requires unique anchors. One DownloadManager anchor
(`if (onProgress_)`) exists twice, so for that single labelled replacement we
replace only the first occurrence, which is the normal progress callback. All
other replacements remain strict and must match exactly once.
"""

import apply_download_stack_hardening as patch

_strict_replace_once = patch.replace_once


def replace_once_with_known_exception(text: str, old: str, new: str, label: str) -> str:
    if label == "runtime free-space guard":
        pos = text.find(old)
        if pos < 0:
            raise SystemExit(f"{label}: anchor not found")
        return text[:pos] + new + text[pos + len(old):]
    return _strict_replace_once(text, old, new, label)


patch.replace_once = replace_once_with_known_exception
patch.main()
