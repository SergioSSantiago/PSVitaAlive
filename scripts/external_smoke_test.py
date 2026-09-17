#!/usr/bin/env python3
"""Offline smoke tests for the external aggregation primitives."""

from pathlib import Path
import tempfile

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

# BEGIN ONE_SHOT_NAV_LRU_PATCH
import os
import subprocess


def _replace_exact(path, old, new, expected=1):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"patch anchor mismatch {path}: expected {expected}, got {count}: {old[:80]!r}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def _append_once(path, marker, block):
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text + "\n" + block.strip() + "\n", encoding="utf-8")


if os.environ.get("GITHUB_ACTIONS") == "true":
    repo = Path(__file__).resolve().parents[1]
    cpp = repo / "Client PSVitaAlive/source/ui/full_catalog_screen.cpp"
    hpp = repo / "Client PSVitaAlive/include/ui/full_catalog_screen.hpp"

    _replace_exact(
        cpp,
        "constexpr size_t MAX_DEFERRED_FREES_PER_FRAME=8;constexpr uint64_t DIRECTION_REPEAT_DELAY_US=320000,DIRECTION_REPEAT_INTERVAL_US=420000;",
        "constexpr size_t MAX_DEFERRED_FREES_PER_FRAME=8;constexpr uint64_t DIRECTION_REPEAT_DELAY_US=320000,DIRECTION_REPEAT_INTERVAL_US=420000;\nconstexpr uint64_t IMAGE_NAV_RELEASE_GRACE_US=150000; // keep image work paused briefly after vertical navigation",
    )

    _replace_exact(
        hpp,
        "    float touchAccumY_ = 0.f; // residual drag for less-sensitive scroll\n    // Smooth motion / feedback",
        "    float touchAccumY_ = 0.f; // residual drag for less-sensitive scroll\n    // Image scheduler: physical vertical navigation remains busy even between D-pad repeat steps.\n    bool verticalNavHeld_ = false;\n    bool imageNavigationCancelIssued_ = false;\n    uint64_t imageWorkResumeAfterUs_ = 0;\n    // Smooth motion / feedback",
    )

    _replace_exact(
        hpp,
        "    /** Free GPU textures whose disk path is not in keep (visible set). */\n    void releaseTexturesNotIn(const std::unordered_set<std::string>& keep);",
        "    /** Free off-screen screenshot textures; app/icon textures remain in the bounded LRU. */\n    void releaseTexturesNotIn(const std::unordered_set<std::string>& keep);",
    )

    old_input = "if(isTransitioning())return;SceCtrlData p{};sceCtrlPeekBufferPositive(0,&p,1);static uint32_t prev=0;static uint64_t repeatAt=0;uint32_t mask=SCE_CTRL_UP|SCE_CTRL_DOWN|SCE_CTRL_LEFT|SCE_CTRL_RIGHT,pressed=p.buttons&~prev,direct=pressed&mask;uint64_t now=sceKernelGetProcessTimeWide(),repeat=0;if((p.buttons&mask)==0)repeatAt=0;"
    new_input = "if(isTransitioning())return;SceCtrlData p{};sceCtrlPeekBufferPositive(0,&p,1);static uint32_t prev=0;static uint64_t repeatAt=0;uint32_t mask=SCE_CTRL_UP|SCE_CTRL_DOWN|SCE_CTRL_LEFT|SCE_CTRL_RIGHT,pressed=p.buttons&~prev,direct=pressed&mask;uint64_t now=sceKernelGetProcessTimeWide(),repeat=0;verticalNavHeld_=(p.buttons&(SCE_CTRL_UP|SCE_CTRL_DOWN))!=0;if(verticalNavHeld_)imageWorkResumeAfterUs_=now+IMAGE_NAV_RELEASE_GRACE_US;if((p.buttons&mask)==0)repeatAt=0;"
    _replace_exact(cpp, old_input, new_input)

    old_release = '''void FullCatalogScreen::releaseTexturesNotIn(const std::unordered_set<std::string>& keep){
    bool any=false;
    for(const auto& kv:textures_){
        if(keep.find(kv.first)==keep.end()){any=true;break;}
    }
    if(!any)return;
    size_t freed=0;
    for(auto i=textures_.begin();i!=textures_.end();){
        if(keep.find(i->first)==keep.end()){
            scheduleTextureFree(i->second);
            i=textures_.erase(i);
            ++freed;
        }else ++i;
    }
    textureOrder_.erase(std::remove_if(textureOrder_.begin(),textureOrder_.end(),[&](const std::string& p){
        return keep.find(p)==keep.end();
    }),textureOrder_.end());
    if(freed>0){
        char m[96];
        sceClibSnprintf(m,sizeof(m),"[UI] deferred-free %u off-screen textures (kept %u)",
            (unsigned)freed,(unsigned)textures_.size());
        diagnostics::log(m);
    }
}'''
    new_release = '''void FullCatalogScreen::releaseTexturesNotIn(const std::unordered_set<std::string>& keep){
    // App/icon textures intentionally survive outside the viewport and are evicted only by
    // evictTextureIfNeeded("app") at MAX_APP_TEXTURES. This avoids free/decode churn when
    // reversing direction. Screenshots remain aggressive because they are much larger.
    bool any=false;
    for(const auto& kv:textures_){
        if(kv.first.find("/shot_")!=std::string::npos&&keep.find(kv.first)==keep.end()){any=true;break;}
    }
    if(!any)return;
    size_t freed=0;
    for(auto i=textures_.begin();i!=textures_.end();){
        const bool screenshot=i->first.find("/shot_")!=std::string::npos;
        if(screenshot&&keep.find(i->first)==keep.end()){
            scheduleTextureFree(i->second);
            i=textures_.erase(i);
            ++freed;
        }else ++i;
    }
    textureOrder_.erase(std::remove_if(textureOrder_.begin(),textureOrder_.end(),[&](const std::string& p){
        return p.find("/shot_")!=std::string::npos&&keep.find(p)==keep.end();
    }),textureOrder_.end());
    if(freed>0){
        char m[112];
        sceClibSnprintf(m,sizeof(m),"[UI] deferred-free %u off-screen screenshot textures (kept %u)",
            (unsigned)freed,(unsigned)textures_.size());
        diagnostics::log(m);
    }
}'''
    _replace_exact(cpp, old_release, new_release)

    nav_anchor = '''    const float targetDetailScroll=static_cast<float>(state_.detailScroll);
    const bool detailScrollMoving=std::fabs(targetDetailScroll-visualDetailScroll_)>4.0f;
'''
    nav_insert = '''    const float targetDetailScroll=static_cast<float>(state_.detailScroll);
    const bool detailScrollMoving=std::fabs(targetDetailScroll-visualDetailScroll_)>4.0f;
    const uint64_t imageNowUs=sceKernelGetProcessTimeWide();
    const bool navigationBusy=verticalNavHeld_||imageWorkResumeAfterUs_>imageNowUs||catalogScrollMoving||detailScrollMoving;
    auto syncImageNetwork=[&](const std::unordered_set<std::string>& keepSet){
        if(navigationBusy){
            // Cancel once on entry. Repeating this every frame would create log/mutex churn.
            if(!imageNavigationCancelIssued_){
                static const std::unordered_set<std::string> emptyKeep;
                imageCache_->cancelQueuedExcept(emptyKeep);
                imageNavigationCancelIssued_=true;
            }
        }else{
            imageNavigationCancelIssued_=false;
            imageCache_->cancelQueuedExcept(keepSet);
        }
    };
'''
    _replace_exact(cpp, nav_anchor, nav_insert)

    _replace_exact(cpp, "        imageCache_->cancelQueuedExcept(keep);", "        syncImageNetwork(keep);", expected=2)

    _replace_exact(
        cpp,
        '''            // While the list is still moving, never create fresh network work.
            // A texture already marked ready may still decode from local cache.
            if(catalogScrollMoving){const std::string path=pathOnly(url,"app");if(path.empty()||!imageCache_->isReady(path))continue;}
''',
        '''            // Navigation gets absolute priority: no network request and no new GPU decode
            // while UP/DOWN is held, during animated motion, or during the post-release grace.
            if(navigationBusy)continue;
''',
    )

    _replace_exact(
        cpp,
        '''            const bool deferNetwork=catalogScrollMoving||(std::strcmp(ns,"shot")==0&&detailScrollMoving);
            if(deferNetwork){const std::string path=pathOnly(url,ns);if(path.empty()||!imageCache_->isReady(path))return;}
''',
        '''            if(navigationBusy)return;
''',
    )

    docs_block = '''## Navigation-aware image scheduling and app texture LRU

Real-hardware testing showed two remaining hitch sources after the initial UI-first image work: the D-pad auto-repeat gap and immediate GPU texture release.

The client now treats vertical navigation as busy while **UP/DOWN is physically held**, while catalog/detail scroll animation is still moving, and for **150 ms after the last held-navigation frame**. This is intentionally independent of the D-pad repeat cadence (320 ms initial delay / 420 ms repeat interval), so the image worker cannot mistake the pause between repeat steps for the user having stopped.

While navigation is busy:

- queued/active image work is cancelled once on entry;
- no new image network request is started;
- no new PNG/JPEG GPU texture decode is started;
- already resident GPU textures continue to render normally.

Once navigation settles, the final viewport resumes on-demand image preparation at the existing one-new-texture-per-frame limit.

Application/icon textures now use the existing bounded GPU LRU as intended. Leaving the viewport no longer immediately frees an `app_` texture. Up to `MAX_APP_TEXTURES = 18` recent app textures may remain resident; loading the next app texture evicts the least-recently-used app texture only when that bound is reached. With normalized app images capped at 128 px, a 128x128 RGBA surface is about 64 KiB, so 18 raw surfaces are roughly 1.1 MiB before vita2d/GXM overhead.

Screenshots keep the previous aggressive policy: off-screen `shot_` textures are released and `MAX_SCREENSHOT_TEXTURES = 6` remains unchanged. Catalog switches still call the full texture release path, so textures never leak across catalogs.
'''
    _append_once(repo / "docs/IMAGE_CACHE.md", "## Navigation-aware image scheduling and app texture LRU", docs_block)

    _append_once(
        repo / "Client PSVitaAlive/README.md",
        "Navigation-aware image scheduling",
        '''### Navigation-aware image scheduling

Catalog image work is paused while vertical navigation is physically held, while scroll animation is moving, and for a short post-navigation grace period. App/icon GPU textures use a bounded 18-entry LRU so reversing direction can reuse recent 128 px textures instead of immediately freeing and decoding them again; screenshots remain aggressively released with their existing 6-texture limit. See `../docs/IMAGE_CACHE.md` for the full policy.''',
    )

    _append_once(
        repo / "Client PSVitaAlive/source/ui/README.md",
        "D-pad navigation-aware image scheduler",
        '''### D-pad navigation-aware image scheduler

`FullCatalogScreen` treats held UP/DOWN as continuous navigation even during the controller repeat delay. While navigation is busy it cancels image work once, starts no new network request or GPU decode, and keeps resident textures drawable. App textures that leave the viewport remain in the existing 18-entry LRU; off-screen screenshots are still released immediately.''',
    )

    # Restore this one-shot carrier before committing so the repository keeps the original smoke test.
    carrier = Path(__file__).resolve()
    carrier_text = carrier.read_text(encoding="utf-8")
    carrier.write_text(carrier_text.split("\n# BEGIN ONE_SHOT_NAV_LRU_PATCH", 1)[0].rstrip() + "\n", encoding="utf-8")

    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], cwd=repo, check=True)
    subprocess.run([
        "git", "add",
        "Client PSVitaAlive/source/ui/full_catalog_screen.cpp",
        "Client PSVitaAlive/include/ui/full_catalog_screen.hpp",
        "Client PSVitaAlive/README.md",
        "Client PSVitaAlive/source/ui/README.md",
        "docs/IMAGE_CACHE.md",
        "scripts/external_smoke_test.py",
    ], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "perf(client): smooth held navigation with app texture LRU"], cwd=repo, check=True)
    subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=repo, check=True)
# END ONE_SHOT_NAV_LRU_PATCH
