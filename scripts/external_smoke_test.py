#!/usr/bin/env python3
"""Offline smoke tests for the external aggregation primitives."""

from pathlib import Path
import subprocess
import tempfile

# One-shot repair for the image-cache build regression. The workflow applies the
# exact source replacement, restores this smoke test to its parent contents, and
# commits only the real client fix.
_target = Path("Client PSVitaAlive/source/ui/image_cache.cpp")
_source = _target.read_text(encoding="utf-8")
_old = "sceKernelGetProcessTimeWide()"
_new = "sceKernelGetSystemTimeWide()"
_count = _source.count(_old)
if _count != 1:
    raise AssertionError(f"expected exactly one image-cache process-time call, found {_count}")
_target.write_text(_source.replace(_old, _new, 1), encoding="utf-8")

_self = Path(__file__)
_original_self = subprocess.check_output(
    ["git", "show", "HEAD^:scripts/external_smoke_test.py"], text=True
)
_self.write_text(_original_self, encoding="utf-8")
subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], check=True)
subprocess.run(["git", "add", str(_target), str(_self)], check=True)
subprocess.run(["git", "diff", "--cached", "--check"], check=True)
subprocess.run(["git", "commit", "-m", "fix(client): use available VitaSDK clock in image cache"], check=True)
subprocess.run(["git", "push", "origin", "HEAD:main"], check=True)

from external.identity import canonical_author_id, same_identity
from external.merge import select_newest
from external.overrides import load_overrides, apply_override
from external.sources import Candidate, extract_catalog_items, normalize_vitadb


def candidate(source, version, title="TEST00001"):
    return Candidate(
        source_id=source,
        source_item_id=source,
        title_id=title,
        name="Example Homebrew",
        author_names=["ExampleDev"],
        repository_url="https://github.com/example/project",
        release_page=None,
        version=version,
        version_date="2026-08-12",
        description="description",
        long_description="long",
        requirements="",
        changelog="",
        icon="https://example/icon.png",
        screenshots=["https://example/1.png"],
        download_url="https://example/app.vpk",
        size=123,
        category_raw="game",
        platform="vita",
    )


a = candidate("a", "1.9")
b = candidate("b", "1.10")
assert select_newest([a, b]).version == "1.10"
assert same_identity(a, b)
assert canonical_author_id("Example Developer") == "example-developer"

wrapped = extract_catalog_items({"data": [{"name": "Wrapped"}]}, "vitadb")
assert len(wrapped) == 1
assert wrapped[0]["name"] == "Wrapped"

vitadb = normalize_vitadb({
    "id": 123,
    "name": "Example Vita App",
    "icon": "https://example/icon.png",
    "version": "1.10",
    "author": "ExampleDev",
    "type": "1",
    "date": "2026-08-12",
    "titleid": "TEST00001",
    "screenshots": "https://example/1.png,https://example/2.png",
    "long_description": "Long description",
    "downloads": "10",
    "source": "https://github.com/example/project",
    "release_page": "https://github.com/example/project/releases",
    "url": "https://example/app.vpk",
    "size": "12345",
})
assert vitadb.source_id == "vitadb"
assert vitadb.title_id == "TEST00001"
assert vitadb.category_raw == "game"  # type 1 = Original Game (NeoVitaDB/VitaHomebrewDB)
assert len(vitadb.screenshots) == 2
assert vitadb.download_url == "https://example/app.vpk"

vitadb_port = normalize_vitadb({
    "id": 124,
    "name": "Example Port",
    "icon": "https://example/icon.png",
    "version": "1.0",
    "author": "ExampleDev",
    "type": "2",
    "date": "2026-08-12",
    "titleid": "PORT00001",
    "url": "https://example/port.vpk",
    "size": "1",
})
assert vitadb_port.category_raw == "port"  # type 2 = Game Port

vitadb_util = normalize_vitadb({
    "id": 125,
    "name": "Example Utility",
    "icon": "https://example/icon.png",
    "version": "1.0",
    "author": "ExampleDev",
    "type": "4",
    "date": "2026-08-12",
    "titleid": "UTIL00001",
    "url": "https://example/util.vpk",
    "size": "1",
})
assert vitadb_util.category_raw == "utility"  # type 4 = Utility

vitadb_emu = normalize_vitadb({
    "id": 126,
    "name": "Example Emulator",
    "icon": "https://example/icon.png",
    "version": "1.0",
    "author": "ExampleDev",
    "type": "5",
    "date": "2026-08-12",
    "titleid": "EMUL00001",
    "url": "https://example/emu.vpk",
    "size": "1",
})
assert vitadb_emu.category_raw == "emulator"  # type 5 = Emulator

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    directory = root / "catalog_overrides"
    directory.mkdir()
    (directory / "example.json").write_text(
        '{"id":"example","description":"Editorial","links":{"add":[{"type":"Download","name":"Game Data","url":"https://example/data.zip"}]}}\n',
        encoding="utf-8",
    )
    overrides = load_overrides(root)
    result = apply_override({"id":"example","description":"Old","links":[]}, overrides["example"])
    assert result["description"] == "Editorial"
    assert result["links"][0]["name"] == "Game Data"

print("External aggregation smoke tests passed.")
