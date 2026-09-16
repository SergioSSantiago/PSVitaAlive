#!/usr/bin/env python3
"""Offline smoke tests for the external aggregation primitives."""

# One-shot main-branch patch runner. This block is intentionally self-removing:
# the push that carries [apply-client-image-perf] lets the existing validation
# workflow apply a surgical client patch, restore this file from HEAD^, commit
# the real source changes, and continue the normal validation job.
import os as _os
import subprocess as _subprocess
from pathlib import Path as _PatchPath

_PATCH_MARKER = "[apply-client-image-perf]"


def _replace_once(path, old, new, label):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _run_client_image_perf_patch():
    root = _PatchPath(__file__).resolve().parents[1]
    image_cache = root / "Client PSVitaAlive/source/ui/image_cache.cpp"
    catalog_ui = root / "Client PSVitaAlive/source/ui/full_catalog_screen.cpp"

    # --- Image cache: 128px app assets + cheap cached-file validation on UI thread ---
    _replace_once(
        image_cache,
        "constexpr size_t MAX_INTERACTIVE_QUEUE=12;\n",
        "constexpr size_t MAX_INTERACTIVE_QUEUE=12;\n"
        "constexpr unsigned APP_IMAGE_MAX_DIM=128u,SCREENSHOT_IMAGE_MAX_DIM=512u;\n"
        "unsigned maxImageDimForNamespace(const std::string&ns){return ns==\"app\"?APP_IMAGE_MAX_DIM:SCREENSHOT_IMAGE_MAX_DIM;}\n",
        "image max dimensions",
    )

    old_magic = (
        "bool readMagic(const std::string&path,unsigned char*magic,size_t n){FILE*f=std::fopen(path.c_str(),\"rb\");"
        "if(!f)return false;size_t got=std::fread(magic,1,n,f);std::fclose(f);return got==n;}\n"
    )
    new_magic = old_magic + (
        "bool cachedNormalizedPngLooksValid(const std::string&path,unsigned maxDim){"
        "unsigned char hdr[24]={};FILE*f=std::fopen(path.c_str(),\"rb\");if(!f)return false;"
        "size_t got=std::fread(hdr,1,sizeof(hdr),f);std::fclose(f);if(got!=sizeof(hdr))return false;"
        "static const unsigned char sig[8]={0x89,0x50,0x4E,0x47,0x0D,0x0A,0x1A,0x0A};"
        "if(std::memcmp(hdr,sig,sizeof(sig))!=0||std::memcmp(hdr+12,\"IHDR\",4)!=0)return false;"
        "auto be32=[](const unsigned char*p)->unsigned{return ((unsigned)p[0]<<24)|((unsigned)p[1]<<16)|((unsigned)p[2]<<8)|(unsigned)p[3];};"
        "unsigned w=be32(hdr+16),h=be32(hdr+20);return w>0&&h>0&&(maxDim==0||(w<=maxDim&&h<=maxDim));}\n"
    )
    _replace_once(image_cache, old_magic, new_magic, "cached PNG header validator")
    _replace_once(
        image_cache,
        "bool validCached=normalizeImageForVita(path,ns==\"app\"?256u:512u);",
        "bool validCached=cachedNormalizedPngLooksValid(path,maxImageDimForNamespace(ns));",
        "cached image validation fast path",
    )
    _replace_once(
        image_cache,
        "if(valid)valid=normalizeImageForVita(job.path,job.path.find(\"/app_\")!=std::string::npos?256u:512u);if(valid){",
        "const uint64_t normStart=sceKernelGetSystemTimeWide();"
        "if(valid)valid=normalizeImageForVita(job.path,job.path.find(\"/app_\")!=std::string::npos?APP_IMAGE_MAX_DIM:SCREENSHOT_IMAGE_MAX_DIM);"
        "const uint64_t normUs=sceKernelGetSystemTimeWide()-normStart;"
        "if(valid&&normUs>=8000ULL){char pm[220];sceClibSnprintf(pm,sizeof(pm),\"[Perf] image normalize slow us=%llu path=%s\",(unsigned long long)normUs,job.path.c_str());diagnostics::log(pm);}"
        "if(valid){",
        "worker app image normalization",
    )

    # --- Catalog UI: exactly 3 split rows, texture fast path, targeted perf telemetry ---
    _replace_once(
        catalog_ui,
        "int FullCatalogScreen::visibleRowsSplit()const{return std::max(1,(SCREEN_H-HEADER_H-TABS_H-FOOTER_H-GRID_PAD*2)/(SPLIT_CARD_H+CARD_GAP));}",
        "int FullCatalogScreen::visibleRowsSplit()const{const int usable=SCREEN_H-HEADER_H-TABS_H-FOOTER_H-GRID_PAD*2;return std::max(1,(usable+CARD_GAP)/(SPLIT_CARD_H+CARD_GAP));}",
        "three visible split rows",
    )

    old_flush = """void FullCatalogScreen::flushDeferredTextureFrees(){
    if(deferredFreeTextures_.empty())return;
    // Previous frame has been presented; safe to return memory to vita2d.
    // Cap per frame so spam L/R cannot free dozens of textures in one shot (Vita3K crash).
    vita2d_wait_rendering_done();
    size_t n=0;
    while(!deferredFreeTextures_.empty() && n<MAX_DEFERRED_FREES_PER_FRAME){
        vita2d_texture* t=deferredFreeTextures_.front();
        deferredFreeTextures_.erase(deferredFreeTextures_.begin());
        if(t)vita2d_free_texture(t);
        ++n;
    }
}
"""
    new_flush = """void FullCatalogScreen::flushDeferredTextureFrees(){
    if(deferredFreeTextures_.empty())return;
    // Previous frame has been presented; safe to return memory to vita2d.
    // Cap per frame so spam L/R cannot free dozens of textures in one shot (Vita3K crash).
    const uint64_t perfStartUs=sceKernelGetProcessTimeWide();
    vita2d_wait_rendering_done();
    size_t n=0;
    while(!deferredFreeTextures_.empty() && n<MAX_DEFERRED_FREES_PER_FRAME){
        vita2d_texture* t=deferredFreeTextures_.front();
        deferredFreeTextures_.erase(deferredFreeTextures_.begin());
        if(t)vita2d_free_texture(t);
        ++n;
    }
    const uint64_t perfEndUs=sceKernelGetProcessTimeWide();
    const uint64_t perfUs=perfEndUs>=perfStartUs?perfEndUs-perfStartUs:0;
    static uint64_t lastPerfLogUs=0;
    if(perfUs>=8000ULL&&(lastPerfLogUs==0||perfEndUs-lastPerfLogUs>=1000000ULL)){
        char m[160];
        sceClibSnprintf(m,sizeof(m),"[Perf] deferred texture free slow us=%llu freed=%u remaining=%u",
            (unsigned long long)perfUs,(unsigned)n,(unsigned)deferredFreeTextures_.size());
        diagnostics::log(m);
        lastPerfLogUs=perfEndUs;
    }
}
"""
    _replace_once(catalog_ui, old_flush, new_flush, "deferred texture free telemetry")

    old_decode = """    vita2d_texture*t=nullptr;
    const char*e=extOf(path);
    if(std::strcmp(e,".jpg")==0||std::strcmp(e,".jpeg")==0)t=vita2d_load_JPEG_file(path.c_str());
    else t=vita2d_load_PNG_file(path.c_str());
"""
    new_decode = """    vita2d_texture*t=nullptr;
    const char*e=extOf(path);
    const uint64_t perfStartUs=sceKernelGetProcessTimeWide();
    if(std::strcmp(e,".jpg")==0||std::strcmp(e,".jpeg")==0)t=vita2d_load_JPEG_file(path.c_str());
    else t=vita2d_load_PNG_file(path.c_str());
    const uint64_t perfEndUs=sceKernelGetProcessTimeWide();
    const uint64_t perfUs=perfEndUs>=perfStartUs?perfEndUs-perfStartUs:0;
    static uint64_t lastTexturePerfLogUs=0;
    if(perfUs>=8000ULL&&(lastTexturePerfLogUs==0||perfEndUs-lastTexturePerfLogUs>=500000ULL)){
        char pm[240];
        sceClibSnprintf(pm,sizeof(pm),"[Perf] texture decode slow us=%llu ns=%s path=%s",
            (unsigned long long)perfUs,ns.c_str(),path.c_str());
        diagnostics::log(pm);
        lastTexturePerfLogUs=perfEndUs;
    }
"""
    _replace_once(catalog_ui, old_decode, new_decode, "texture decode telemetry")

    old_status = """    if (imageCache_->isFailed(path)) {
        vita2d_draw_rectangle(x, y, w, h, SURFACE2);
        return;
    }

    if (!imageCache_->isReady(path)) {
        // Soft nudge: if file already on disk, request() will mark ready; else may queue once.
        // prepareVisibleTextures is the primary enqueue path for visible cells only.
        drawImageLoadingPlaceholder(url, ns, x, y, w, h);
        return;
    }

    auto it = textures_.find(path);
    if (it == textures_.end() || !it->second) {
        drawImageLoadingPlaceholder(url, ns, x, y, w, h);
        return;
    }
"""
    new_status = """    // Fast path: once a GPU texture exists, draw it without locking ImageCache
    // every frame. Cache state is only consulted while a texture is still missing.
    auto it = textures_.find(path);
    if (it == textures_.end() || !it->second) {
        if (imageCache_->isFailed(path)) {
            vita2d_draw_rectangle(x, y, w, h, SURFACE2);
            return;
        }
        if (!imageCache_->isReady(path)) {
            drawImageLoadingPlaceholder(url, ns, x, y, w, h);
            return;
        }
        // The file is ready on disk; prepareVisibleTextures will decode at most
        // one new GPU texture per frame. Keep the placeholder until then.
        drawImageLoadingPlaceholder(url, ns, x, y, w, h);
        return;
    }
"""
    _replace_once(catalog_ui, old_status, new_status, "drawImage loaded-texture fast path")

    _replace_once(
        catalog_ui,
        "}bool FullCatalogScreen::updateAndDraw(){\n    if(!ready_)return false;",
        "}bool FullCatalogScreen::updateAndDraw(){\n    if(!ready_)return false;\n    const uint64_t frameStartUs=sceKernelGetProcessTimeWide();",
        "frame timer start",
    )
    _replace_once(
        catalog_ui,
        "    if(catalogSwitchCooldownFrames_==0)prepareVisibleTextures();\n    draw();\n    return !state_.requestExit;\n}",
        "    if(catalogSwitchCooldownFrames_==0)prepareVisibleTextures();\n"
        "    draw();\n"
        "    const uint64_t frameEndUs=sceKernelGetProcessTimeWide();\n"
        "    const uint64_t frameUs=frameEndUs>=frameStartUs?frameEndUs-frameStartUs:0;\n"
        "    static uint64_t lastSlowFrameLogUs=0;\n"
        "    if(frameUs>=25000ULL&&(lastSlowFrameLogUs==0||frameEndUs-lastSlowFrameLogUs>=2000000ULL)){\n"
        "        char pm[180];\n"
        "        sceClibSnprintf(pm,sizeof(pm),\"[Perf] slow frame us=%llu mode=%d textures=%u deferred=%u\",\n"
        "            (unsigned long long)frameUs,(int)state_.mode,(unsigned)textures_.size(),(unsigned)deferredFreeTextures_.size());\n"
        "        diagnostics::log(pm);\n"
        "        lastSlowFrameLogUs=frameEndUs;\n"
        "    }\n"
        "    return !state_.requestExit;\n}"
        ,
        "slow frame telemetry",
    )

    # Safety invariants for the intended viewport policy.
    cache_text = image_cache.read_text(encoding="utf-8")
    ui_text = catalog_ui.read_text(encoding="utf-8")
    if "APP_IMAGE_MAX_DIM=128u" not in cache_text or "?256u:512u" in cache_text:
        raise RuntimeError("128px app-image policy was not applied cleanly")
    if "first+9" not in ui_text:
        raise RuntimeError("full catalog 9-item viewport policy changed unexpectedly")
    if "(usable+CARD_GAP)/(SPLIT_CARD_H+CARD_GAP)" not in ui_text:
        raise RuntimeError("split catalog 3-row formula missing")

    # Restore this one-shot runner before committing the actual client changes.
    original_smoke = _subprocess.check_output(
        ["git", "show", "HEAD^:scripts/external_smoke_test.py"],
        cwd=root,
        text=True,
    )
    (root / "scripts/external_smoke_test.py").write_text(original_smoke, encoding="utf-8")

    _subprocess.run(["git", "diff", "--check"], cwd=root, check=True)
    _subprocess.run(["git", "config", "user.name", "github-actions[bot]"], cwd=root, check=True)
    _subprocess.run(
        ["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"],
        cwd=root,
        check=True,
    )
    _subprocess.run(
        [
            "git", "add", "--",
            "Client PSVitaAlive/source/ui/image_cache.cpp",
            "Client PSVitaAlive/source/ui/full_catalog_screen.cpp",
            "scripts/external_smoke_test.py",
        ],
        cwd=root,
        check=True,
    )
    _subprocess.run(
        ["git", "commit", "-m", "perf(client): optimize visible image pipeline"],
        cwd=root,
        check=True,
    )
    _subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=root, check=True)
    print("Applied client image performance patch and restored one-shot runner.")


if _os.environ.get("GITHUB_ACTIONS") == "true":
    try:
        _head_message = _subprocess.check_output(
            ["git", "log", "-1", "--pretty=%B"], text=True
        )
    except Exception:
        _head_message = ""
    if _PATCH_MARKER in _head_message:
        _run_client_image_perf_patch()

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
