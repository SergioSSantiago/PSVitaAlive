#!/usr/bin/env python3
"""Restore Client PSVitaAlive/assets/lang/en.lang from embedded gzip payload."""
import gzip, base64, pathlib
# generated payload
B64 = open(__file__).read().split('B64_START\n')[1].split('\nB64_END')[0].replace('\n','')
# fallback: load from sibling if present
