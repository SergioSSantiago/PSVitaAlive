#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(rel, old, new, label):
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 match in {rel}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def append_once(rel, marker, block):
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text + block, encoding="utf-8")


# ---------------------------------------------------------------------------
# AppSettings persistence: Random is backward-compatible default.
# ---------------------------------------------------------------------------
settings_cpp = "Client PSVitaAlive/source/installer/app_settings.cpp"
replace_once(
    settings_cpp,
    '''bool containsBool(const std::string& json, const char* key, bool& out) {
    const std::string pattern = std::string("\\\"") + key + "\\\"";
    size_t p = json.find(pattern); if (p == std::string::npos) return false;
    p = json.find(':', p); if (p == std::string::npos) return false;
    while (p < json.size() && (json[p] == ':' || json[p] == ' ' || json[p] == '\\t')) ++p;
    if (json.compare(p, 4, "true") == 0) { out = true; return true; }
    if (json.compare(p, 5, "false") == 0) { out = false; return true; }
    return false;
}

} // namespace
''',
    '''bool containsBool(const std::string& json, const char* key, bool& out) {
    const std::string pattern = std::string("\\\"") + key + "\\\"";
    size_t p = json.find(pattern); if (p == std::string::npos) return false;
    p = json.find(':', p); if (p == std::string::npos) return false;
    while (p < json.size() && (json[p] == ':' || json[p] == ' ' || json[p] == '\\t')) ++p;
    if (json.compare(p, 4, "true") == 0) { out = true; return true; }
    if (json.compare(p, 5, "false") == 0) { out = false; return true; }
    return false;
}

bool validMascotSelection(const std::string& value) {
    if (value == "random" || value == "off") return true;
    const char* prefix = nullptr;
    if (value.rfind("internal:", 0) == 0) prefix = "internal:";
    else if (value.rfind("user:", 0) == 0) prefix = "user:";
    else return false;
    const size_t start = std::strlen(prefix);
    if (value.size() <= start || value.size() > 96) return false;
    for (size_t i = start; i < value.size(); ++i) {
        const char c = value[i];
        const bool ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                        (c >= '0' && c <= '9') || c == '-' || c == '_';
        if (!ok) return false;
    }
    return true;
}

} // namespace
''',
    "settings mascot validator",
)
replace_once(settings_cpp, "char buf[1280];", "char buf[2048];", "settings read buffer")
replace_once(
    settings_cpp,
    '''    if (containsKey(json, "ui_font_file", v)) data.uiFontFile = v;
    {
''',
    '''    if (containsKey(json, "ui_font_file", v)) data.uiFontFile = v;
    if (containsKey(json, "mascot_selection", v) && validMascotSelection(v)) data.mascotSelection = v;
    {
''',
    "settings mascot load",
)
replace_once(settings_cpp, "char json[1792];", "char json[2304];", "settings write buffer")
replace_once(
    settings_cpp,
    '''        "{\\n  \\\"install_method\\\": \\\"%s\\\",\\n  \\\"psp_target\\\": \\\"%s\\\",\\n  \\\"psp_media_format\\\": \\\"%s\\\",\\n  \\\"color_theme\\\": \\\"%s\\\",\\n  \\\"warn_missing_plugins\\\": %s,\\n  \\\"prompt_image_warmup\\\": %s,\\n  \\\"theme_setup_done\\\": %s,\\n  \\\"psp_setup_done\\\": %s,\\n  \\\"startup_plugin_detection\\\": %s,\\n  \\\"startup_update_check\\\": %s,\\n  \\\"language_mode\\\": \\\"%s\\\",\\n  \\\"language\\\": \\\"%s\\\",\\n  \\\"ui_font_style\\\": \\\"%s\\\",\\n  \\\"ui_font_file\\\": \\\"%s\\\",\\n  \\\"ui_font_scale\\\": %d\\n}\\n",
''',
    '''        "{\\n  \\\"install_method\\\": \\\"%s\\\",\\n  \\\"psp_target\\\": \\\"%s\\\",\\n  \\\"psp_media_format\\\": \\\"%s\\\",\\n  \\\"color_theme\\\": \\\"%s\\\",\\n  \\\"warn_missing_plugins\\\": %s,\\n  \\\"prompt_image_warmup\\\": %s,\\n  \\\"theme_setup_done\\\": %s,\\n  \\\"psp_setup_done\\\": %s,\\n  \\\"startup_plugin_detection\\\": %s,\\n  \\\"startup_update_check\\\": %s,\\n  \\\"language_mode\\\": \\\"%s\\\",\\n  \\\"language\\\": \\\"%s\\\",\\n  \\\"ui_font_style\\\": \\\"%s\\\",\\n  \\\"ui_font_file\\\": \\\"%s\\\",\\n  \\\"ui_font_scale\\\": %d,\\n  \\\"mascot_selection\\\": \\\"%s\\\"\\n}\\n",
''',
    "settings mascot save format",
)
replace_once(
    settings_cpp,
    '''        toString(data.uiFontStyle), data.uiFontFile.c_str(), data.uiFontScalePct);
''',
    '''        toString(data.uiFontStyle), data.uiFontFile.c_str(), data.uiFontScalePct,
        validMascotSelection(data.mascotSelection) ? data.mascotSelection.c_str() : "random");
''',
    "settings mascot save arg",
)
replace_once(
    settings_cpp,
    '''    sceClibPrintf("[AppSettings] loaded theme=%s language=%s psp_setup_done=%d\\n", toString(data.colorTheme), data.language.c_str(), data.pspSetupDone ? 1 : 0);
''',
    '''    sceClibPrintf("[AppSettings] loaded theme=%s language=%s psp_setup_done=%d mascot=%s\\n",
                  toString(data.colorTheme), data.language.c_str(), data.pspSetupDone ? 1 : 0, data.mascotSelection.c_str());
''',
    "settings mascot load log",
)

# ---------------------------------------------------------------------------
# Mascot manager small safety refinements.
# ---------------------------------------------------------------------------
manager_cpp = "Client PSVitaAlive/source/ui/mascot_manager.cpp"
replace_once(manager_cpp, "#include <cstring>\n#include <string>", "#include <cstring>\n#include <cstddef>\n#include <string>", "manager cstddef")
replace_once(
    manager_cpp,
    '''    // The module may already be loaded by the catalog parser. Loading again is harmless on
    // supported VitaSDK runtimes; parsing below remains the authoritative success check.
    (void)sceSysmoduleLoadModule(SCE_SYSMODULE_JSON);
''',
    '''    // Request the JSON sysmodule once for this process. The catalog parser may already have
    // loaded it; the parse result below remains the authoritative validity check either way.
    static bool jsonModuleRequested = false;
    if (!jsonModuleRequested) {
        jsonModuleRequested = true;
        (void)sceSysmoduleLoadModule(SCE_SYSMODULE_JSON);
    }
''',
    "manager JSON module once",
)
replace_once(
    manager_cpp,
    '''    if (impl_->catalog.empty()) scan();
    if (impl_->catalog.empty()) {
''',
    '''    // A protection entry is infrequent. Rescan here so mascots copied to ux0 while
    // PSVitaAlive is already running can participate in the very next Random session.
    scan();
    if (impl_->catalog.empty()) {
''',
    "manager rescan per session",
)

# ---------------------------------------------------------------------------
# FullCatalogScreen: hook manager only into protector + settings.
# ---------------------------------------------------------------------------
ui_cpp = "Client PSVitaAlive/source/ui/full_catalog_screen.cpp"
replace_once(
    ui_cpp,
    '#include "ui/full_catalog_screen.hpp"\n#include "ui/news_markdown.hpp"',
    '#include "ui/full_catalog_screen.hpp"\n#include "ui/mascot_manager.hpp"\n#include "ui/news_markdown.hpp"',
    "UI manager include",
)
replace_once(
    ui_cpp,
    '''uint32_t gProtectionRngState = 0;

uint64_t protectionNowMs() {
''',
    '''uint32_t gProtectionRngState = 0;
::psvitaalive::ui::MascotManager gProtectionMascotManager;
std::string gProtectionMascotSelection = "random";
bool gProtectionMascotStartPending = false;
bool gProtectionMascotStopPending = false;

uint64_t protectionNowMs() {
''',
    "protection mascot globals",
)
replace_once(
    ui_cpp,
    '''    if (next == ProtectionPhase::None) {
        if (gProtectionActive) diagnostics::log("[UI] OLED protection left: job phase ended");
        gProtectionPhase = ProtectionPhase::None;
        gProtectionActive = false;
        gProtectionPhaseStartMs = 0;
        gProtectionLastMoveMs = 0;
        return;
    }

    if (next != gProtectionPhase || gProtectionPhaseStartMs == 0) {
        gProtectionPhase = next;
        gProtectionActive = false;
        gProtectionPhaseStartMs = now;
        gProtectionLastMoveMs = 0;
        protectionChoosePosition(false);
        diagnostics::log("[UI] OLED protection phase timer started");
    }
''',
    '''    if (next == ProtectionPhase::None) {
        if (gProtectionActive) diagnostics::log("[UI] OLED protection left: job phase ended");
        gProtectionPhase = ProtectionPhase::None;
        gProtectionActive = false;
        gProtectionPhaseStartMs = 0;
        gProtectionLastMoveMs = 0;
        gProtectionMascotStartPending = false;
        gProtectionMascotStopPending = true;
        return;
    }

    if (next != gProtectionPhase || gProtectionPhaseStartMs == 0) {
        gProtectionPhase = next;
        gProtectionActive = false;
        gProtectionPhaseStartMs = now;
        gProtectionLastMoveMs = 0;
        gProtectionMascotStartPending = false;
        gProtectionMascotStopPending = true;
        protectionChoosePosition(false);
        diagnostics::log("[UI] OLED protection phase timer started");
    }
''',
    "protection phase lifecycle",
)
replace_once(
    ui_cpp,
    '''            gProtectionActive = true;
            protectionChoosePosition(false);
            gProtectionLastMoveMs = now;
            diagnostics::log("[UI] OLED protection entered");
''',
    '''            gProtectionActive = true;
            protectionChoosePosition(false);
            gProtectionLastMoveMs = now;
            gProtectionMascotStartPending = true;
            diagnostics::log("[UI] OLED protection entered");
''',
    "protection start pending",
)
replace_once(
    ui_cpp,
    '''void protectionDismiss() {
    if (!gProtectionActive) return;
    gProtectionActive = false;
    gProtectionPhaseStartMs = protectionNowMs();
    gProtectionLastMoveMs = 0;
    diagnostics::log("[UI] OLED protection dismissed by user; grace timer restarted");
}
''',
    '''void protectionDismiss() {
    if (!gProtectionActive) return;
    gProtectionActive = false;
    gProtectionPhaseStartMs = protectionNowMs();
    gProtectionLastMoveMs = 0;
    gProtectionMascotStartPending = false;
    gProtectionMascotStopPending = true;
    diagnostics::log("[UI] OLED protection dismissed by user; grace timer restarted");
}

void protectionServiceMascot() {
    const uint64_t now = protectionNowMs();
    if (gProtectionMascotStopPending) {
        gProtectionMascotManager.stop();
        gProtectionMascotStopPending = false;
    }
    if (gProtectionMascotStartPending) {
        if (gProtectionActive) gProtectionMascotManager.start(gProtectionMascotSelection, now);
        gProtectionMascotStartPending = false;
    }
    if (gProtectionActive && gProtectionMascotManager.active())
        gProtectionMascotManager.update(now);
}
''',
    "protection service manager",
)
replace_once(
    ui_cpp,
    '''void FullCatalogScreen::shutdown(){
    releaseTextures();
''',
    '''void FullCatalogScreen::shutdown(){
    gProtectionMascotStartPending = false;
    gProtectionMascotStopPending = false;
    gProtectionMascotManager.stop();
    releaseTextures();
''',
    "shutdown mascot cleanup",
)
replace_once(
    ui_cpp,
    '''void FullCatalogScreen::setAppSettings(const ::psvitaalive::AppSettingsData& settings) {
    settingsEdit_ = settings;
    applyColorTheme(settingsEdit_.colorTheme, false);
''',
    '''void FullCatalogScreen::setAppSettings(const ::psvitaalive::AppSettingsData& settings) {
    settingsEdit_ = settings;
    if (settingsEdit_.mascotSelection.empty()) settingsEdit_.mascotSelection = "random";
    gProtectionMascotSelection = settingsEdit_.mascotSelection;
    applyColorTheme(settingsEdit_.colorTheme, false);
''',
    "settings inject mascot",
)
replace_once(
    ui_cpp,
    '''    pluginsStatus_ = ::psvitaalive::PluginDetector::scan();
    settingsKubridgeOk_ = essentialPluginFullyInstalled(
''',
    '''    gProtectionMascotManager.scan();
    pluginsStatus_ = ::psvitaalive::PluginDetector::scan();
    settingsKubridgeOk_ = essentialPluginFullyInstalled(
''',
    "settings mascot scan",
)
replace_once(
    ui_cpp,
    '''    if (save) {
        if (settingsSave_) settingsSave_(settingsEdit_);
        showToast(::psvitaalive::L(::psvitaalive::TextId::SettingsSaved), 1600);
        diagnostics::log("[UI] settings saved");
    }
''',
    '''    if (save) {
        if (settingsEdit_.mascotSelection.empty()) settingsEdit_.mascotSelection = "random";
        if (settingsEdit_.mascotSelection != "random" && settingsEdit_.mascotSelection != "off" &&
            !gProtectionMascotManager.find(settingsEdit_.mascotSelection)) {
            diagnostics::log("[Mascot] saved selection disappeared; fallback=random");
            settingsEdit_.mascotSelection = "random";
        }
        gProtectionMascotSelection = settingsEdit_.mascotSelection;
        if (settingsSave_) settingsSave_(settingsEdit_);
        showToast(::psvitaalive::L(::psvitaalive::TextId::SettingsSaved), 1600);
        diagnostics::log("[UI] settings saved");
    }
''',
    "settings mascot save normalization",
)
replace_once(
    ui_cpp,
    '''    } else if (row == 6) {
        (void)delta;
        openThemePicker(); // same palette window as first-run setup
    } else if (row == 7) {
        settingsEdit_.warnMissingPlugins = !settingsEdit_.warnMissingPlugins;
    } else if (row == 8) {
        settingsEdit_.promptImageWarmup = !settingsEdit_.promptImageWarmup;
    } else if (row == 9) {
        triggerSelfUpdateAction();
    }
''',
    '''    } else if (row == 6) {
        (void)delta;
        openThemePicker(); // same palette window as first-run setup
    } else if (row == 7) {
        settingsEdit_.mascotSelection = gProtectionMascotManager.cycleSelection(
            settingsEdit_.mascotSelection.empty() ? "random" : settingsEdit_.mascotSelection, delta);
    } else if (row == 8) {
        settingsEdit_.warnMissingPlugins = !settingsEdit_.warnMissingPlugins;
    } else if (row == 9) {
        settingsEdit_.promptImageWarmup = !settingsEdit_.promptImageWarmup;
    } else if (row == 10) {
        triggerSelfUpdateAction();
    }
''',
    "settings mascot cycle row",
)
replace_once(ui_cpp, "    constexpr int kRows = 10;\n    if (nav & SCE_CTRL_UP)", "    constexpr int kRows = 11;\n    if (nav & SCE_CTRL_UP)", "settings keyboard row count")

# Settings touch metadata / row count.
replace_once(
    ui_cpp,
    '''        // Must match opts[10] section breaks in drawSettings
        Meta meta[10] = {
            {true, "INSTALL"}, {false, ""}, {false, ""},
            {true, "INTERFACE"}, {false, ""}, {false, ""}, {false, ""}, {false, ""},
            {true, "CATALOG"}, {true, "UPDATES"}
        };
        int rowY[10];
        int y = contentTop - static_cast<int>(settingsScrollY_);
        for (int i = 0; i < 10; ++i) {
''',
    '''        // Must match opts[11] section breaks in drawSettings
        Meta meta[11] = {
            {true, "INSTALL"}, {false, ""}, {false, ""},
            {true, "INTERFACE"}, {false, ""}, {false, ""}, {false, ""}, {false, ""}, {false, ""},
            {true, "CATALOG"}, {true, "UPDATES"}
        };
        int rowY[11];
        int y = contentTop - static_cast<int>(settingsScrollY_);
        for (int i = 0; i < 11; ++i) {
''',
    "settings touch metadata",
)
replace_once(ui_cpp, "        const int measured = 9 * (52 + 8) + 4 * 22;", "        const int measured = 11 * (52 + 8) + 4 * 22;", "settings touch measured")
replace_once(ui_cpp, "                    constexpr int kRows = 10;\n                    touchAccumY_", "                    constexpr int kRows = 11;\n                    touchAccumY_", "settings touch row count")
replace_once(ui_cpp, "            for (int i = 0; i < 10; ++i) {\n                if (hit(x, yy, listX, rowY[i], listW, rowH))", "            for (int i = 0; i < 11; ++i) {\n                if (hit(x, yy, listX, rowY[i], listW, rowH))", "settings touch tap rows")

# Settings draw helpers and option list.
replace_once(
    ui_cpp,
    '''    auto yesNo = [&](bool v) -> std::string {
        return v ? ::psvitaalive::L(TID::Yes) : ::psvitaalive::L(TID::No);
    };

    struct Opt {
''',
    '''    auto yesNo = [&](bool v) -> std::string {
        return v ? ::psvitaalive::L(TID::Yes) : ::psvitaalive::L(TID::No);
    };
    auto mascotLabel = [&]() -> std::string {
        const std::string selection = settingsEdit_.mascotSelection.empty() ? "random" : settingsEdit_.mascotSelection;
        if (selection == "random") return ::psvitaalive::L("MASCOT_RANDOM");
        if (selection == "off") return ::psvitaalive::L("MASCOT_OFF");
        const ::psvitaalive::ui::MascotInfo* info = gProtectionMascotManager.find(selection);
        return info ? info->name : ::psvitaalive::L("MASCOT_RANDOM");
    };

    struct Opt {
''',
    "settings mascot label helper",
)
replace_once(
    ui_cpp,
    '''    Opt opts[10] = {
        {::psvitaalive::L(TID::SectionInstall), ::psvitaalive::L(TID::InstallMethod), methodLabel(), ::psvitaalive::L(TID::HintInstallMethod), true},
        {"", ::psvitaalive::L(TID::PspPs1Target), pspLabel(), ::psvitaalive::L(TID::HintPspTarget), false},
        {"", ::psvitaalive::L(TID::PspMediaAdrenaline), mediaFormatLabel(), ::psvitaalive::L(TID::HintPspMedia), false},
        {::psvitaalive::L(TID::SectionInterface), ::psvitaalive::L(TID::Language), languageLabel(), ::psvitaalive::L(TID::HintLanguage), true},
        {"", ::psvitaalive::L(TID::UiFont), fontLabel(), ::psvitaalive::L(TID::HintUiFont), false},
        {"", ::psvitaalive::L(TID::UiFontSize), (std::to_string(settingsEdit_.uiFontScalePct) + "%"), ::psvitaalive::L(TID::HintUiFontSize), false},
        {"", ::psvitaalive::L(TID::ColorTheme), themeLabel() + "  >", ::psvitaalive::L(TID::HintColorTheme), false},
        {"", ::psvitaalive::L(TID::WarnMissingPlugins), yesNo(settingsEdit_.warnMissingPlugins), ::psvitaalive::L(TID::HintWarnPlugins), false},
        {::psvitaalive::L(TID::SectionCatalog), ::psvitaalive::L(TID::PromptImageDownload), yesNo(settingsEdit_.promptImageWarmup), ::psvitaalive::L(TID::HintImageWarmup), true},
        {::psvitaalive::L(TID::SectionUpdates), ::psvitaalive::L(TID::CheckForUpdates), updateLabel(), ::psvitaalive::L(TID::HintSelfUpdate), true},
    };
''',
    '''    Opt opts[11] = {
        {::psvitaalive::L(TID::SectionInstall), ::psvitaalive::L(TID::InstallMethod), methodLabel(), ::psvitaalive::L(TID::HintInstallMethod), true},
        {"", ::psvitaalive::L(TID::PspPs1Target), pspLabel(), ::psvitaalive::L(TID::HintPspTarget), false},
        {"", ::psvitaalive::L(TID::PspMediaAdrenaline), mediaFormatLabel(), ::psvitaalive::L(TID::HintPspMedia), false},
        {::psvitaalive::L(TID::SectionInterface), ::psvitaalive::L(TID::Language), languageLabel(), ::psvitaalive::L(TID::HintLanguage), true},
        {"", ::psvitaalive::L(TID::UiFont), fontLabel(), ::psvitaalive::L(TID::HintUiFont), false},
        {"", ::psvitaalive::L(TID::UiFontSize), (std::to_string(settingsEdit_.uiFontScalePct) + "%"), ::psvitaalive::L(TID::HintUiFontSize), false},
        {"", ::psvitaalive::L(TID::ColorTheme), themeLabel() + "  >", ::psvitaalive::L(TID::HintColorTheme), false},
        {"", ::psvitaalive::L("MASCOT"), mascotLabel(), ::psvitaalive::L("HINT_MASCOT"), false},
        {"", ::psvitaalive::L(TID::WarnMissingPlugins), yesNo(settingsEdit_.warnMissingPlugins), ::psvitaalive::L(TID::HintWarnPlugins), false},
        {::psvitaalive::L(TID::SectionCatalog), ::psvitaalive::L(TID::PromptImageDownload), yesNo(settingsEdit_.promptImageWarmup), ::psvitaalive::L(TID::HintImageWarmup), true},
        {::psvitaalive::L(TID::SectionUpdates), ::psvitaalive::L(TID::CheckForUpdates), updateLabel(), ::psvitaalive::L(TID::HintSelfUpdate), true},
    };
''',
    "settings mascot option row",
)
replace_once(ui_cpp, "    for (int i = 0; i < 10; ++i) {\n        if (opts[i].sectionStart", "    for (int i = 0; i < 11; ++i) {\n        if (opts[i].sectionStart", "settings measured rows")
replace_once(ui_cpp, "        for (int i = 0; i <= settingsFocus_ && i < 10; ++i) {", "        for (int i = 0; i <= settingsFocus_ && i < 11; ++i) {", "settings focus rows")
replace_once(ui_cpp, "    int rowY[10] = {};\n    int y = contentTop", "    int rowY[11] = {};\n    int y = contentTop", "settings row array")
replace_once(ui_cpp, "    for (int i = 0; i < 10; ++i) {\n        if (opts[i].sectionStart", "    for (int i = 0; i < 11; ++i) {\n        if (opts[i].sectionStart", "settings draw rows")
replace_once(
    ui_cpp,
    '''        case 7:
            body1 = ::psvitaalive::L(TID::InfoWarnPlugins1);
            body2 = ::psvitaalive::L(TID::InfoWarnPlugins2);
            body3 = ::psvitaalive::L(TID::InfoWarnPlugins3);
            break;
        case 8:
            body1 = ::psvitaalive::L(TID::InfoImageWarmup1);
            body2 = ::psvitaalive::L(TID::InfoImageWarmup2);
            body3 = ::psvitaalive::L(TID::InfoImageWarmup3);
            break;
        case 9:
            body1 = ::psvitaalive::L(TID::InfoSelfUpdate1);
            body2 = ::psvitaalive::L(TID::InfoSelfUpdate2);
            body3 = ::psvitaalive::L(TID::InfoSelfUpdate3);
            break;
''',
    '''        case 7:
            body1 = ::psvitaalive::L("INFO_MASCOT_1");
            body2 = ::psvitaalive::L("INFO_MASCOT_2");
            body3 = ::psvitaalive::L("INFO_MASCOT_3");
            break;
        case 8:
            body1 = ::psvitaalive::L(TID::InfoWarnPlugins1);
            body2 = ::psvitaalive::L(TID::InfoWarnPlugins2);
            body3 = ::psvitaalive::L(TID::InfoWarnPlugins3);
            break;
        case 9:
            body1 = ::psvitaalive::L(TID::InfoImageWarmup1);
            body2 = ::psvitaalive::L(TID::InfoImageWarmup2);
            body3 = ::psvitaalive::L(TID::InfoImageWarmup3);
            break;
        case 10:
            body1 = ::psvitaalive::L(TID::InfoSelfUpdate1);
            body2 = ::psvitaalive::L(TID::InfoSelfUpdate2);
            body3 = ::psvitaalive::L(TID::InfoSelfUpdate3);
            break;
''',
    "settings mascot info panel",
)
replace_once(ui_cpp, "            if (settingsFocus_ == 9) {\n                char ver[96];", "            if (settingsFocus_ == 10) {\n                char ver[96];", "settings update info index")

# Move protection tick to normal update path and render mascot between black background and text.
replace_once(
    ui_cpp,
    '''    pollSelfUpdateProgress();
    updateAnimations();
''',
    '''    pollSelfUpdateProgress();
    protectionTick();
    protectionServiceMascot();
    updateAnimations();
''',
    "protection tick main UI path",
)
replace_once(
    ui_cpp,
    '''// Burn-in protection is intentionally restricted to active transfer/extract/install
// phases. The normal progress/result UI returns immediately on phase changes/end.
protectionTick();
if (installProgressActive_ && installOutcome_ == 0 && gProtectionActive) {
''',
    '''// Burn-in protection is intentionally restricted to active transfer/extract/install
// phases. The normal progress/result UI returns immediately on phase changes/end.
if (installProgressActive_ && installOutcome_ == 0 && gProtectionActive) {
''',
    "remove draw-time protection tick",
)
replace_once(
    ui_cpp,
    '''    const unsigned protectionBlack = RGBA8(0, 0, 0, 255);
    vita2d_draw_rectangle(0, 0, SCREEN_W, SCREEN_H, protectionBlack);

    using TID = ::psvitaalive::TextId;
''',
    '''    const unsigned protectionBlack = RGBA8(0, 0, 0, 255);
    vita2d_draw_rectangle(0, 0, SCREEN_W, SCREEN_H, protectionBlack);
    // Mascot is below progress text so the transfer state always stays readable.
    gProtectionMascotManager.render();

    using TID = ::psvitaalive::TextId;
''',
    "protection mascot render",
)

# ---------------------------------------------------------------------------
# CMake: compile manager and package internal mascot asset root.
# ---------------------------------------------------------------------------
cmake = "Client PSVitaAlive/CMakeLists.txt"
replace_once(cmake, "  source/ui/ui_font.cpp\n  source/ui/full_catalog_screen.cpp", "  source/ui/ui_font.cpp\n  source/ui/mascot_manager.cpp\n  source/ui/full_catalog_screen.cpp", "CMake manager source")
replace_once(cmake, '    -a "../assets/font=font"\n    -a "updater_eboot.bin=updater/eboot.bin"', '    -a "../assets/font=font"\n    -a "../assets/mascots=mascots"\n    -a "updater_eboot.bin=updater/eboot.bin"', "CMake mascot VPK asset")
replace_once(cmake, '    "${CMAKE_SOURCE_DIR}/assets/font"\n  COMMENT', '    "${CMAKE_SOURCE_DIR}/assets/font"\n    "${CMAKE_SOURCE_DIR}/assets/mascots"\n  COMMENT', "CMake mascot dependency")

# ---------------------------------------------------------------------------
# Dynamic localization keys: English fallback + Spanish native strings.
# ---------------------------------------------------------------------------
append_once(
    "Client PSVitaAlive/assets/lang/en.lang",
    "\nMASCOT=",
    '''\n# Protection mascot settings\nMASCOT=Mascot\nMASCOT_RANDOM=Random\nMASCOT_OFF=Off\nHINT_MASCOT=Random, Off, built-in or user mascot\nINFO_MASCOT_1=Random chooses a mascot each time the protection screen opens.\nINFO_MASCOT_2=Built-in and user mascots are combined in one list.\nINFO_MASCOT_3=User mascots: ux0:data/psvitaalive/mascots/\n''',
)
append_once(
    "Client PSVitaAlive/assets/lang/es.lang",
    "\nMASCOT=",
    '''\n# Ajustes de mascota del protector\nMASCOT=Mascota\nMASCOT_RANDOM=Aleatoria\nMASCOT_OFF=Desactivada\nHINT_MASCOT=Aleatoria, desactivada, interna o del usuario\nINFO_MASCOT_1=Aleatoria elige una mascota cada vez que se abre el protector.\nINFO_MASCOT_2=Las mascotas internas y del usuario aparecen en una sola lista.\nINFO_MASCOT_3=Mascotas del usuario: ux0:data/psvitaalive/mascots/\n''',
)

# ---------------------------------------------------------------------------
# Existing OLED protection documentation: append integration contract.
# ---------------------------------------------------------------------------
append_once(
    "Client PSVitaAlive/docs/OLED_PROTECTION_MODE.md",
    "## Mascotas del protector",
    '''\n\n## Mascotas del protector\n\nEl modo de protección admite ahora mascotas animadas mediante `MascotManager`. Esta integración es exclusivamente visual y no modifica libcurl, el instalador, extractores, colas, bloqueos del botón PS ni `sceKernelPowerTick`.\n\nFuentes combinadas:\n\n```text\napp0:mascots/\nux0:data/psvitaalive/mascots/\n```\n\nEl valor predeterminado de Settings es `Random`: cada entrada real al protector selecciona una mascota válida de cualquiera de las dos fuentes. El usuario también puede elegir `Off` o una mascota concreta.\n\nLas texturas se cargan únicamente para la sesión activa del protector y se liberan al salir. La carga/liberación se atiende en el hilo principal de UI antes del dibujo, nunca desde workers de red/instalación.\n\nEl área lógica de movimiento continúa siendo 100 × 100 con margen seguro de 16 px. Los PNG físicos pueden tener otras dimensiones y se ajustan dentro de esa caja conservando la relación de aspecto.\n\nLa especificación completa, instalación de mascotas de usuario, límites y pruebas está en [`MASCOTS.md`](MASCOTS.md).\n''',
)

print("Protection mascot integration patch applied successfully")
