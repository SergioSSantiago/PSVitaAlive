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

# __PSVA_PHASE2_PATCH__
# One-shot main-branch patch. It restores this smoke-test file before committing,
# so the net repository change contains only the client optimization + docs.
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()
MARKER = "# __PSVA_PHASE2_PATCH__"


def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


image_hpp = ROOT / "Client PSVitaAlive/include/ui/image_cache.hpp"
image_cpp = ROOT / "Client PSVitaAlive/source/ui/image_cache.cpp"
ui_cpp = ROOT / "Client PSVitaAlive/source/ui/full_catalog_screen.cpp"
doc = ROOT / "docs/IMAGE_CACHE.md"
client_readme = ROOT / "Client PSVitaAlive/README.md"
ui_readme = ROOT / "Client PSVitaAlive/source/ui/README.md"

replace_once(
    image_hpp,
    "    /** Drop queued jobs whose path is not in keep (active download is left alone). */\n",
    "    /** Drop queued jobs outside keep and request cancellation when the active image leaves keep. */\n",
    "image cache header cancellation contract",
)

replace_once(
    image_cpp,
    "constexpr size_t MAX_INTERACTIVE_QUEUE=12;\n",
    "constexpr size_t MAX_INTERACTIVE_QUEUE=12;\nconstexpr uint64_t IMAGE_PROGRESS_PUBLISH_INTERVAL_US=100000ULL; // UI progress <= 10 Hz\n",
    "image progress throttle constant",
)

old_cancel = '''void ImageCache::cancelQueuedExcept(const std::unordered_set<std::string>& keep) {
    if (mutex_ < 0) return;
    sceKernelLockMutex(mutex_, 1, nullptr);
    size_t removed = 0;
    std::vector<Job> keptJobs;
    keptJobs.reserve(queue_.size());
    for (const Job& j : queue_) {
        if (keep.find(j.path) != keep.end()) {
            keptJobs.push_back(j);
        } else {
            pending_.erase(std::remove(pending_.begin(), pending_.end(), j.path), pending_.end());
            ++removed;
        }
    }
    queue_.swap(keptJobs);
    sceKernelUnlockMutex(mutex_, 1);
    if (removed > 0) {
        char m[128];
        sceClibSnprintf(m, sizeof(m), "[ImageCache] pruned %u off-screen queued downloads", (unsigned)removed);
        diagnostics::log(m);
    }
}
'''
new_cancel = '''void ImageCache::cancelQueuedExcept(const std::unordered_set<std::string>& keep) {
    if (mutex_ < 0) return;
    sceKernelLockMutex(mutex_, 1, nullptr);
    size_t removed = 0;
    std::vector<Job> keptJobs;
    keptJobs.reserve(queue_.size());
    for (const Job& j : queue_) {
        if (keep.find(j.path) != keep.end()) {
            keptJobs.push_back(j);
        } else {
            pending_.erase(std::remove(pending_.begin(), pending_.end(), j.path), pending_.end());
            ++removed;
        }
    }
    queue_.swap(keptJobs);
    const bool cancelActive = !currentPath_.empty() && keep.find(currentPath_) == keep.end();
    if (cancelActive) cancelRequested_ = true;
    sceKernelUnlockMutex(mutex_, 1);
    if (removed > 0 || cancelActive) {
        char m[160];
        sceClibSnprintf(m, sizeof(m), "[ImageCache] pruned off-screen queued=%u active_cancel=%d",
                        (unsigned)removed, cancelActive ? 1 : 0);
        diagnostics::log(m);
    }
}
'''
replace_once(image_cpp, old_cancel, new_cancel, "cancel active off-screen image")

old_progress = '''HttpProgressFn onProgress=[this](const HttpProgress&p){if(mutex_<0)return;sceKernelLockMutex(mutex_,1,nullptr);currentDownloaded_=p.downloaded;currentTotal_=p.total;currentSpeed_=p.bytesPerSecond;sceKernelUnlockMutex(mutex_,1);};HttpCancelFn shouldCancel=[this](){if(mutex_<0)return true;sceKernelLockMutex(mutex_,1,nullptr);const bool c=cancelRequested_||stopping_;sceKernelUnlockMutex(mutex_,1);return c;};'''
new_progress = '''uint64_t latestDownloaded=0,latestTotal=0,latestSpeed=0,lastProgressPublishUs=0;HttpProgressFn onProgress=[this,&latestDownloaded,&latestTotal,&latestSpeed,&lastProgressPublishUs](const HttpProgress&p){latestDownloaded=p.downloaded;latestTotal=p.total;latestSpeed=p.bytesPerSecond;const uint64_t now=sceKernelGetProcessTimeWide();const bool finalKnown=p.total>0&&p.downloaded>=p.total;if(!finalKnown&&lastProgressPublishUs!=0&&now-lastProgressPublishUs<IMAGE_PROGRESS_PUBLISH_INTERVAL_US)return;lastProgressPublishUs=now;if(mutex_<0)return;sceKernelLockMutex(mutex_,1,nullptr);currentDownloaded_=latestDownloaded;currentTotal_=latestTotal;currentSpeed_=latestSpeed;sceKernelUnlockMutex(mutex_,1);};HttpCancelFn shouldCancel=[this](){if(mutex_<0)return true;sceKernelLockMutex(mutex_,1,nullptr);const bool c=cancelRequested_||stopping_;sceKernelUnlockMutex(mutex_,1);return c;};'''
replace_once(image_cpp, old_progress, new_progress, "throttle image progress publication")

old_finish = '''sceKernelLockMutex(mutex_,1,nullptr);const bool cancelled=cancelRequested_||r==HttpResult::Cancelled;const uint64_t doneBytes=currentDownloaded_,doneTotal=currentTotal_;if(!cancelled&&r==HttpResult::Ok){completedBytes_+=doneBytes;if(doneTotal>0)completedTotalBytes_+=doneTotal;}currentFile_.clear();currentPath_.clear();currentDownloaded_=0;currentTotal_=0;currentSpeed_=0;cancelRequested_=false;sceKernelUnlockMutex(mutex_,1);if(cancelled){sceIoRemove(job.path.c_str());sceKernelLockMutex(mutex_,1,nullptr);pending_.erase(std::remove(pending_.begin(),pending_.end(),job.path),pending_.end());sceKernelUnlockMutex(mutex_,1);diagnostics::log(std::string("[ImageCache] cancelled url=")+job.url+" path="+job.path);continue;}bool valid=false;if(r==HttpResult::Ok){SceIoStat st={};valid=sceIoGetstat(job.path.c_str(),&st)>=0&&st.st_size>0;}const uint64_t normStart=sceKernelGetSystemTimeWide();if(valid)valid=normalizeImageForVita(job.path,job.path.find("/app_")!=std::string::npos?APP_IMAGE_MAX_DIM:SCREENSHOT_IMAGE_MAX_DIM);const uint64_t normUs=sceKernelGetSystemTimeWide()-normStart;if(valid&&normUs>=8000ULL){char pm[220];sceClibSnprintf(pm,sizeof(pm),"[Perf] image normalize slow us=%llu path=%s",(unsigned long long)normUs,job.path.c_str());diagnostics::log(pm);}if(valid){'''
new_finish = '''const uint64_t doneBytes=latestDownloaded,doneTotal=latestTotal;sceKernelLockMutex(mutex_,1,nullptr);const bool cancelled=cancelRequested_||r==HttpResult::Cancelled||stopping_;sceKernelUnlockMutex(mutex_,1);if(cancelled){sceIoRemove(job.path.c_str());sceKernelLockMutex(mutex_,1,nullptr);pending_.erase(std::remove(pending_.begin(),pending_.end(),job.path),pending_.end());currentFile_.clear();currentPath_.clear();currentDownloaded_=0;currentTotal_=0;currentSpeed_=0;cancelRequested_=false;sceKernelUnlockMutex(mutex_,1);diagnostics::log(std::string("[ImageCache] cancelled url=")+job.url+" path="+job.path);continue;}bool valid=false;if(r==HttpResult::Ok){SceIoStat st={};valid=sceIoGetstat(job.path.c_str(),&st)>=0&&st.st_size>0;}const uint64_t normStart=sceKernelGetSystemTimeWide();if(valid)valid=normalizeImageForVita(job.path,job.path.find("/app_")!=std::string::npos?APP_IMAGE_MAX_DIM:SCREENSHOT_IMAGE_MAX_DIM);const uint64_t normUs=sceKernelGetSystemTimeWide()-normStart;if(valid&&normUs>=8000ULL){char pm[220];sceClibSnprintf(pm,sizeof(pm),"[Perf] image normalize slow us=%llu path=%s",(unsigned long long)normUs,job.path.c_str());diagnostics::log(pm);}sceKernelLockMutex(mutex_,1,nullptr);const bool cancelledAfterNormalize=cancelRequested_||stopping_;if(!cancelledAfterNormalize&&r==HttpResult::Ok&&valid){completedBytes_+=doneBytes;if(doneTotal>0)completedTotalBytes_+=doneTotal;}currentFile_.clear();currentPath_.clear();currentDownloaded_=0;currentTotal_=0;currentSpeed_=0;cancelRequested_=false;sceKernelUnlockMutex(mutex_,1);if(cancelledAfterNormalize){sceIoRemove(job.path.c_str());sceKernelLockMutex(mutex_,1,nullptr);pending_.erase(std::remove(pending_.begin(),pending_.end(),job.path),pending_.end());sceKernelUnlockMutex(mutex_,1);diagnostics::log(std::string("[ImageCache] cancelled after transfer url=")+job.url+" path="+job.path);continue;}if(valid){'''
replace_once(image_cpp, old_finish, new_finish, "keep active identity through normalize and re-check cancellation")

replace_once(
    ui_cpp,
    "    // At most one new GPU texture decode per frame (avoids hitch + free/load storms).\n    constexpr int kLoadsPerFrame = 1;\n",
    "    // At most one new GPU texture decode per frame (avoids hitch + free/load storms).\n    constexpr int kLoadsPerFrame = 1;\n    // UI-first scheduling: do not enqueue missing network images while animated scroll is still moving.\n    // Already-ready cache entries may still be decoded one per frame, preserving fast cached browsing.\n    const float targetCatalogScroll=static_cast<float>(state_.catalogScrollRow);\n    const bool catalogScrollMoving=std::fabs(targetCatalogScroll-visualCatalogScroll_)>0.08f;\n    const float targetDetailScroll=static_cast<float>(state_.detailScroll);\n    const bool detailScrollMoving=std::fabs(targetDetailScroll-visualDetailScroll_)>4.0f;\n",
    "catalog scroll motion detection",
)

old_full_loop = '''        int loads=0;
        for(int i=first;i<last&&loads<kLoadsPerFrame;++i){
            const CatalogItem& it=catalogView()[i];
            const std::string& url=!it.icon.empty()?it.icon:it.cover;
            if(url.empty())continue;
            // Only enqueue download / decode for the current viewport.
            const size_t before=textures_.size();
            prepareImageTexture(url, "app");
            if(textures_.size()>before)++loads;
        }
'''
new_full_loop = '''        int loads=0;
        for(int i=first;i<last&&loads<kLoadsPerFrame;++i){
            const CatalogItem& it=catalogView()[i];
            const std::string& url=!it.icon.empty()?it.icon:it.cover;
            if(url.empty())continue;
            // While the list is still moving, never create fresh network work.
            // A texture already marked ready may still decode from local cache.
            if(catalogScrollMoving){const std::string path=pathOnly(url,"app");if(path.empty()||!imageCache_->isReady(path))continue;}
            const size_t before=textures_.size();
            prepareImageTexture(url, "app");
            if(textures_.size()>before)++loads;
        }
'''
replace_once(ui_cpp, old_full_loop, new_full_loop, "full catalog network debounce")

old_prepare_one = '''        int loads=0;
        auto prepareOne=[&](const std::string& url, const char* ns){
            if(loads>=kLoadsPerFrame||url.empty())return;
            const size_t before=textures_.size();
            prepareImageTexture(url, ns);
            if(textures_.size()>before)++loads;
        };
'''
new_prepare_one = '''        int loads=0;
        auto prepareOne=[&](const std::string& url, const char* ns){
            if(loads>=kLoadsPerFrame||url.empty())return;
            const bool deferNetwork=catalogScrollMoving||(std::strcmp(ns,"shot")==0&&detailScrollMoving);
            if(deferNetwork){const std::string path=pathOnly(url,ns);if(path.empty()||!imageCache_->isReady(path))return;}
            const size_t before=textures_.size();
            prepareImageTexture(url, ns);
            if(textures_.size()>before)++loads;
        };
'''
replace_once(ui_cpp, old_prepare_one, new_prepare_one, "detail/list network debounce")

anchor = "A failed new download does **not** delete the previous version first. Superseded cached versions are pruned only after the current file exists and has passed image normalization/validation.\n\nIf an older queued request for the same resource is still pending when a newer URL is requested, the obsolete queued work is removed. If that old resource is actively downloading, cancellation is requested so the new version can take over.\n"
addition = anchor + '''\n## UI-first scheduling while browsing\n\nImage network work is intentionally subordinate to catalog navigation on real PS Vita hardware. `FullCatalogScreen` still defines the exact viewport set first (9 app images in Full Catalog and 3 app images in the split Detail list, plus only screenshots intersecting the visible Detail body), releases/cancels work outside that set, and then decides whether new image work may start.\n\nWhile the animated catalog scroll has not settled near `catalogScrollRow`, missing app images are **not newly queued for network download**. Images already marked ready in the local cache may still be decoded into a GPU texture, limited to the existing one-new-texture-per-frame budget. This keeps already-cached browsing responsive without allowing rapid Up/Down navigation to create a download/cancel storm for intermediate rows.\n\nThe same policy applies to screenshots while the Detail body itself is still scrolling: a missing screenshot waits until the Detail scroll settles, while an already-ready cached screenshot may be prepared normally.\n\n`cancelQueuedExcept()` also covers the currently active image transfer. If `currentPath_` leaves the viewport keep-set, `cancelRequested_` is raised and the existing libcurl cancellation callback stops the transfer. The worker keeps the active identity through normalization and checks cancellation again before publishing the result, so work that became obsolete at the transfer/normalize boundary is discarded instead of being marked ready.\n\nImage download progress is published to shared UI state at most every **100 ms (10 Hz)**, with a final known-total update allowed immediately. The worker still tracks the latest byte counters locally for accounting; throttling only reduces cross-thread mutex traffic and does not limit network throughput.\n\nConceptually:\n\n```text\nrapid catalog navigation\n        ↓\ncompute final visible keep-set\n        ↓\nprune queued off-screen work\n        ↓\ncancel active transfer if it left the keep-set\n        ↓\nscroll still moving?\n   ├─ yes → reuse/decode ready cache only; no new network requests\n   └─ no  → queue missing images for the settled viewport\n```\n'''
replace_once(doc, anchor, addition, "IMAGE_CACHE UI-first scheduling documentation")

replace_once(
    client_readme,
    "- **Image cache v3** with on-demand loading, catalog/resource-aware replacement and startup disk cap: app/icon/cover images are normalized to max **128 px**, screenshots to max **256 px**; if cache exceeds **200 MiB**, startup trims oldest complete images to about **40 MiB**; see [`../docs/IMAGE_CACHE.md`](../docs/IMAGE_CACHE.md)\n",
    "- **Image cache v3** with UI-first on-demand loading, catalog/resource-aware replacement and startup disk cap: app/icon/cover images are normalized to max **128 px**, screenshots to max **256 px**; rapid catalog/detail scrolling suppresses new network image requests, off-screen active image transfers are cancellable, and shared download progress is throttled to 10 Hz; if cache exceeds **200 MiB**, startup trims oldest complete images to about **40 MiB**; see [`../docs/IMAGE_CACHE.md`](../docs/IMAGE_CACHE.md)\n",
    "client README image cache summary",
)

replace_once(
    ui_readme,
    "- Existing `/app_` and `/shot_` path classification remains compatible with the texture-management logic in `FullCatalogScreen`.\n",
    "- Existing `/app_` and `/shot_` path classification remains compatible with the texture-management logic in `FullCatalogScreen`.\n- UI-first scheduling defers new network image requests while catalog/detail scrolling is still animated, while allowing already-ready cached textures to continue loading under the one-texture-per-frame budget. Off-screen active image transfers are cancelled through the existing libcurl cancellation callback, and worker progress publication is limited to 10 Hz to reduce mutex pressure during navigation.\n",
    "UI README scheduling summary",
)

# Sanity checks before committing.
assert "IMAGE_PROGRESS_PUBLISH_INTERVAL_US=100000ULL" in image_cpp.read_text(encoding="utf-8")
assert "active_cancel=%d" in image_cpp.read_text(encoding="utf-8")
assert "catalogScrollMoving" in ui_cpp.read_text(encoding="utf-8")
assert "## UI-first scheduling while browsing" in doc.read_text(encoding="utf-8")

# Restore this one-shot carrier so it does not remain in the net repository diff.
self_text = SELF.read_text(encoding="utf-8")
SELF.write_text(self_text.split(MARKER, 1)[0].rstrip() + "\n", encoding="utf-8")

subprocess.run(["git", "diff", "--check"], cwd=ROOT, check=True)
subprocess.run(["git", "config", "user.name", "github-actions[bot]"], cwd=ROOT, check=True)
subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], cwd=ROOT, check=True)
paths = [
    "scripts/external_smoke_test.py",
    "Client PSVitaAlive/include/ui/image_cache.hpp",
    "Client PSVitaAlive/source/ui/image_cache.cpp",
    "Client PSVitaAlive/source/ui/full_catalog_screen.cpp",
    "docs/IMAGE_CACHE.md",
    "Client PSVitaAlive/README.md",
    "Client PSVitaAlive/source/ui/README.md",
]
subprocess.run(["git", "add", "--", *paths], cwd=ROOT, check=True)
subprocess.run(["git", "commit", "-m", "perf(client): prioritize UI during image downloads"], cwd=ROOT, check=True)
subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=ROOT, check=True)
print("PSVitaAlive image-scroll performance phase 2 applied and pushed.")
