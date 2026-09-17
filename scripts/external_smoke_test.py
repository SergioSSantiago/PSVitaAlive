#!/usr/bin/env python3
from pathlib import Path
import subprocess

repo = Path(__file__).resolve().parents[1]

def replace_once(path, old, new):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"anchor mismatch {path}: expected 1 got {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

hpp = repo / "Client PSVitaAlive/include/ui/full_catalog_screen.hpp"
cpp = repo / "Client PSVitaAlive/source/ui/full_catalog_screen.cpp"
client_readme = repo / "Client PSVitaAlive/README.md"
ui_readme = repo / "Client PSVitaAlive/source/ui/README.md"
image_doc = repo / "docs/IMAGE_CACHE.md"

replace_once(
    hpp,
    "    ::psvitaalive::PluginStatus pluginsStatus_{};\n    SettingsSaveFn settingsSave_;\n",
    "    ::psvitaalive::PluginStatus pluginsStatus_{};\n"
    "    // Snapshot expensive filesystem-backed plugin checks once when Settings opens.\n"
    "    bool settingsKubridgeOk_ = false;\n"
    "    bool settingsRepatchOk_ = false;\n"
    "    bool settingsFdFixOk_ = false;\n"
    "    bool settingsLibshacccgOk_ = false;\n"
    "    SettingsSaveFn settingsSave_;\n"
)

old_open = '''void FullCatalogScreen::openSettings() {
    if (installProgressActive_ || catalogLoading_ || selfUpdateBusy_.load()) {
        showToast(::psvitaalive::L(::psvitaalive::TextId::LockedFinishJob), 2800);
        return;
    }
    if (state_.mode == UiMode::SETTINGS) return;
    settingsReturnMode_ = (state_.mode == UiMode::SPLIT_DETAIL) ? UiMode::SPLIT_DETAIL : UiMode::FULL_CATALOG;
    settingsFocus_ = 0;
    settingsInfoScrollY_ = 0.f;
    settingsInfoScrollY_ = 0.f;
    settingsEnter_ = 0.f;
    settingsFocusY_ = 0.f;
    settingsScrollY_ = 0.f;
    state_.mode = UiMode::SETTINGS;
    diagnostics::log("[UI] settings opened");
}
'''
new_open = '''void FullCatalogScreen::openSettings() {
    if (installProgressActive_ || catalogLoading_ || selfUpdateBusy_.load()) {
        showToast(::psvitaalive::L(::psvitaalive::TextId::LockedFinishJob), 2800);
        return;
    }
    if (state_.mode == UiMode::SETTINGS) return;

    // Settings must be render-only after entry: cancel catalog image work and perform
    // filesystem-backed plugin detection exactly once instead of from drawSettings().
    if (imageCache_) {
        static const std::unordered_set<std::string> emptyImageKeep;
        imageCache_->cancelQueuedExcept(emptyImageKeep);
    }
    pluginsStatus_ = ::psvitaalive::PluginDetector::scan();
    settingsKubridgeOk_ = essentialPluginFullyInstalled(
        "*KERNEL", "ur0:tai/kubridge.skprx", {"ur0:tai/kubridge.skprx"});
    settingsRepatchOk_ = pluginsStatus_.repatch;
    settingsFdFixOk_ = pluginsStatus_.fdFix || settingsRepatchOk_;
    settingsLibshacccgOk_ = essentialFilePresent({
        "ur0:/data/libshacccg.suprx", "ur0:data/libshacccg.suprx", "ux0:data/libshacccg.suprx"});

    settingsReturnMode_ = (state_.mode == UiMode::SPLIT_DETAIL) ? UiMode::SPLIT_DETAIL : UiMode::FULL_CATALOG;
    settingsFocus_ = 0;
    settingsInfoScrollY_ = 0.f;
    settingsEnter_ = 0.f;
    settingsFocusY_ = 0.f;
    settingsScrollY_ = 0.f;
    state_.mode = UiMode::SETTINGS;
    diagnostics::log("[UI] settings opened (plugin status snapshot ready)");
}
'''
replace_once(cpp, old_open, new_open)

old_plugins = '''            pushPlug("NoNpDrm", pluginsStatus_.nonpdrm);
            pushPlug("NoPspEmuDrm", pluginsStatus_.nopspemudrmKern);
            {
                const bool kub = essentialPluginFullyInstalled(
                    "*KERNEL", "ur0:tai/kubridge.skprx",
                    {"ur0:tai/kubridge.skprx"});
                const bool fdfFile = essentialPluginFullyInstalled(
                    "*KERNEL", "ur0:tai/fd_fix.skprx",
                    {"ur0:tai/fd_fix.skprx"});
                const bool rep = essentialPluginFullyInstalled(
                    "*KERNEL", "ur0:tai/repatch.skprx",
                    {"ur0:tai/repatch.skprx", "ur0:tai/repatch_ex.skprx"});
                const bool fdf = fdfFile || rep || pluginsStatus_.fdFix;
                const bool sha =
                    essentialFilePresent({"ur0:/data/libshacccg.suprx", "ur0:data/libshacccg.suprx",
                                                "ux0:data/libshacccg.suprx"});
                pushPlug("kubridge", kub);
                pushPlug("RePatch", rep);
                pushPlug("fd_fix", fdf);
                pushPlug("libshacccg", sha);
            }
'''
new_plugins = '''            pushPlug("NoNpDrm", pluginsStatus_.nonpdrm);
            pushPlug("NoPspEmuDrm", pluginsStatus_.nopspemudrmKern);
            // Pure RAM reads: disk/config probing is snapshotted once in openSettings().
            pushPlug("kubridge", settingsKubridgeOk_);
            pushPlug("RePatch", settingsRepatchOk_);
            pushPlug("fd_fix", settingsFdFixOk_);
            pushPlug("libshacccg", settingsLibshacccgOk_);
'''
replace_once(cpp, old_plugins, new_plugins)

replace_once(
    cpp,
    "    if(catalogSwitchCooldownFrames_==0)prepareVisibleTextures();\n",
    "    // Settings is intentionally image-worker quiet; existing GPU textures remain resident.\n"
    "    if(state_.mode!=UiMode::SETTINGS&&catalogSwitchCooldownFrames_==0)prepareVisibleTextures();\n"
)

replace_once(
    client_readme,
    "- Plugin detection (AutoPlugin2-style parser; prefer **ur0:tai** over ux0); Settings **INFO → SYSTEM** shows NoNpDrm, NoPspEmuDrm, kubridge, fd_fix, libshacccg\n",
    "- Plugin detection (AutoPlugin2-style parser; prefer **ur0:tai** over ux0); Settings **INFO → SYSTEM** shows NoNpDrm, NoPspEmuDrm, kubridge, fd_fix, libshacccg. Filesystem-backed plugin checks are snapshotted once when Settings opens, so the render loop does not repeatedly read `ur0:tai/config.txt` or probe plugin files.\n"
)

settings_section = '''## Settings performance\n\nSettings is deliberately **render-only after entry**. Opening Settings cancels queued/active catalog image work, snapshots plugin status once, and then renders the SYSTEM status block from RAM. `drawSettings()` must not call filesystem-backed plugin probes such as `essentialPluginFullyInstalled()` or `TaiConfigEditor::configContainsLine()` because those operations open/read `ur0:tai/config.txt` and can collapse frame rate on real hardware.\n\n`updateAndDraw()` also skips `prepareVisibleTextures()` while `UiMode::SETTINGS` is active. Existing app textures remain resident in the bounded LRU and image preparation resumes automatically after Settings closes.\n\n'''
replace_once(ui_readme, "## Settings INFO\n\nINFO panel documents each focused option (install method, PSP target/media, language, font, theme, plugins, images, updates). SYSTEM block lists plugin detection status with larger type.\n\n", "## Settings INFO\n\nINFO panel documents each focused option (install method, PSP target/media, language, font, theme, plugins, images, updates). SYSTEM block lists plugin detection status with larger type.\n\n" + settings_section)

image_settings = '''## Settings image-work suspension\n\nSettings is treated as a UI-only surface. When it opens, `FullCatalogScreen` cancels queued/active catalog image work once and `updateAndDraw()` stops calling `prepareVisibleTextures()` until Settings closes. Already-created app textures stay resident in the existing bounded LRU, so returning to the catalog does not force unnecessary decode/reload churn.\n\nThis also keeps Settings isolated from image-network and GPU-decode contention while the user changes options. No catalog schema or disk-cache format changes are involved.\n\n'''
replace_once(image_doc, "## Image normalization dimensions\n", image_settings + "## Image normalization dimensions\n")

subprocess.run(["git", "config", "user.name", "github-actions[bot]"], cwd=repo, check=True)
subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], cwd=repo, check=True)
subprocess.run(["git", "checkout", "HEAD^", "--", "scripts/external_smoke_test.py"], cwd=repo, check=True)
paths = [
    "Client PSVitaAlive/include/ui/full_catalog_screen.hpp",
    "Client PSVitaAlive/source/ui/full_catalog_screen.cpp",
    "Client PSVitaAlive/README.md",
    "Client PSVitaAlive/source/ui/README.md",
    "docs/IMAGE_CACHE.md",
    "scripts/external_smoke_test.py",
]
subprocess.run(["git", "add", "--", *paths], cwd=repo, check=True)
subprocess.run(["git", "diff", "--cached", "--check"], cwd=repo, check=True)
subprocess.run(["git", "commit", "-m", "perf(client): keep settings render loop filesystem-free"], cwd=repo, check=True)
subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=repo, check=True)
print("Settings performance patch applied and pushed.")
