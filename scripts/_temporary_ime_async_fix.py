from pathlib import Path

main_path = Path('Client PSVitaAlive/source/main.cpp')
hdr_path = Path('Client PSVitaAlive/include/ui/full_catalog_screen.hpp')
cpp_path = Path('Client PSVitaAlive/source/ui/full_catalog_screen.cpp')

main = main_path.read_text(encoding='utf-8')
hdr = hdr_path.read_text(encoding='utf-8')
cpp = cpp_path.read_text(encoding='utf-8')

# FullCatalogScreen API: make search request asynchronous.
old = '    using SearchRequestFn = std::function<std::string(const std::string&)>;'
new = '    using SearchRequestFn = std::function<void(const std::string&)>;'
if hdr.count(old) != 1:
    raise SystemExit(f'Expected one SearchRequestFn typedef, found {hdr.count(old)}')
hdr = hdr.replace(old, new, 1)

marker = '    void setSearchCallback(SearchRequestFn callback);\n'
insert = (
    marker +
    '    /** Apply text returned asynchronously by the system IME. */\n'
    '    void completeSearch(const std::string& query);\n'
    '    /** Block underlying catalog input while a system dialog owns controls/touch. */\n'
    '    void setExternalInputBlocked(bool blocked) { externalInputBlocked_ = blocked; }\n'
)
if hdr.count(marker) != 1:
    raise SystemExit(f'Expected one setSearchCallback declaration, found {hdr.count(marker)}')
hdr = hdr.replace(marker, insert, 1)

marker = '    std::string searchQuery_;\n'
insert = marker + '    bool externalInputBlocked_ = false;\n'
if hdr.count(marker) != 1:
    raise SystemExit(f'Expected one searchQuery_ member, found {hdr.count(marker)}')
hdr = hdr.replace(marker, insert, 1)

# FullCatalogScreen rendering: service CommonDialog on every frame.
compact = 'vita2d_end_drawing();vita2d_swap_buffers();'
spaced = 'vita2d_end_drawing();\n    vita2d_swap_buffers();'
compact_n = cpp.count(compact)
spaced_n = cpp.count(spaced)
if compact_n + spaced_n < 4:
    raise SystemExit(f'Expected >=4 frame endings, found compact={compact_n} spaced={spaced_n}')
cpp = cpp.replace(compact, 'finishFrameWithCommonDialog();')
cpp = cpp.replace(spaced, 'finishFrameWithCommonDialog();')

ns = 'namespace psvitaalive::ui { namespace {\n'
helper = '''namespace psvitaalive::ui { namespace {

// Service Sony CommonDialog between end_drawing and swap on every UI frame.
// Repeated IME sessions on real hardware depend on this lifecycle continuing
// even after sceImeDialogTerm() while the dialog state drains back to NONE.
inline void finishFrameWithCommonDialog() {
    vita2d_end_drawing();
    vita2d_common_dialog_update();
    vita2d_swap_buffers();
}
'''
if cpp.count(ns) != 1:
    raise SystemExit(f'Expected one UI anonymous namespace marker, found {cpp.count(ns)}')
cpp = cpp.replace(ns, helper, 1)

old_call = 'if (searchRequest_) applySearch(searchRequest_(searchQuery_));'
call_n = cpp.count(old_call)
if call_n != 2:
    raise SystemExit(f'Expected two synchronous search calls, found {call_n}')
cpp = cpp.replace(old_call, 'if (searchRequest_) searchRequest_(searchQuery_);')

set_items = 'void FullCatalogScreen::setCatalogItems(std::vector<CatalogItem>items){'
completion = '''void FullCatalogScreen::completeSearch(const std::string& query){
    applySearch(query);
}

void FullCatalogScreen::setCatalogItems(std::vector<CatalogItem>items){'''
if cpp.count(set_items) != 1:
    raise SystemExit(f'Expected one setCatalogItems definition, found {cpp.count(set_items)}')
cpp = cpp.replace(set_items, completion, 1)

hi = 'void FullCatalogScreen::handleInput(){\n'
if cpp.count(hi) != 1:
    raise SystemExit(f'Expected one handleInput, found {cpp.count(hi)}')
cpp = cpp.replace(hi, hi + '    if (externalInputBlocked_) return;\n', 1)

ht = 'void FullCatalogScreen::handleTouch(){\n'
if cpp.count(ht) != 1:
    raise SystemExit(f'Expected one handleTouch, found {cpp.count(ht)}')
cpp = cpp.replace(ht, ht + '    if (externalInputBlocked_) return;\n', 1)

# main.cpp: persistent, repeat-safe IME controller.
start = main.find('bool asciiToWide(')
end = main.find('\nbool peekFrontTouch', start)
if start < 0 or end < 0:
    raise SystemExit('Could not locate old IME helper block in main.cpp')

ime_block = r'''size_t utf8ToUtf16(const std::string& src, SceWChar16* dst, size_t cap) {
    if (!dst || cap == 0) return 0;
    size_t i = 0, out = 0;
    while (i < src.size() && out + 1 < cap) {
        const unsigned char c = static_cast<unsigned char>(src[i]);
        uint32_t cp = 0xFFFD;
        size_t step = 1;
        if (c < 0x80) {
            cp = c;
        } else if ((c & 0xE0) == 0xC0 && i + 1 < src.size()) {
            const unsigned char c1 = static_cast<unsigned char>(src[i + 1]);
            if ((c1 & 0xC0) == 0x80) {
                cp = ((c & 0x1F) << 6) | (c1 & 0x3F);
                if (cp >= 0x80) step = 2; else cp = 0xFFFD;
            }
        } else if ((c & 0xF0) == 0xE0 && i + 2 < src.size()) {
            const unsigned char c1 = static_cast<unsigned char>(src[i + 1]);
            const unsigned char c2 = static_cast<unsigned char>(src[i + 2]);
            if ((c1 & 0xC0) == 0x80 && (c2 & 0xC0) == 0x80) {
                cp = ((c & 0x0F) << 12) | ((c1 & 0x3F) << 6) | (c2 & 0x3F);
                if (cp >= 0x800 && !(cp >= 0xD800 && cp <= 0xDFFF)) step = 3; else cp = 0xFFFD;
            }
        } else if ((c & 0xF8) == 0xF0 && i + 3 < src.size()) {
            const unsigned char c1 = static_cast<unsigned char>(src[i + 1]);
            const unsigned char c2 = static_cast<unsigned char>(src[i + 2]);
            const unsigned char c3 = static_cast<unsigned char>(src[i + 3]);
            if ((c1 & 0xC0) == 0x80 && (c2 & 0xC0) == 0x80 && (c3 & 0xC0) == 0x80) {
                cp = ((c & 0x07) << 18) | ((c1 & 0x3F) << 12) | ((c2 & 0x3F) << 6) | (c3 & 0x3F);
                if (cp >= 0x10000 && cp <= 0x10FFFF) step = 4; else cp = 0xFFFD;
            }
        }
        if (cp <= 0xFFFF) {
            dst[out++] = static_cast<SceWChar16>(cp);
        } else {
            if (out + 2 >= cap) break;
            cp -= 0x10000;
            dst[out++] = static_cast<SceWChar16>(0xD800 | (cp >> 10));
            dst[out++] = static_cast<SceWChar16>(0xDC00 | (cp & 0x3FF));
        }
        i += step;
    }
    dst[out] = 0;
    return out;
}

std::string utf16ToUtf8(const SceWChar16* src) {
    std::string out;
    if (!src) return out;
    for (size_t i = 0; src[i] != 0 && i < 2048; ++i) {
        uint32_t cp = src[i];
        if (cp >= 0xD800 && cp <= 0xDBFF && src[i + 1] >= 0xDC00 && src[i + 1] <= 0xDFFF) {
            cp = 0x10000 + ((cp - 0xD800) << 10) + (src[++i] - 0xDC00);
        } else if (cp >= 0xD800 && cp <= 0xDFFF) {
            cp = 0xFFFD;
        }
        if (cp < 0x80) {
            out.push_back(static_cast<char>(cp));
        } else if (cp < 0x800) {
            out.push_back(static_cast<char>(0xC0 | (cp >> 6)));
            out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
        } else if (cp < 0x10000) {
            out.push_back(static_cast<char>(0xE0 | (cp >> 12)));
            out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
            out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
        } else {
            out.push_back(static_cast<char>(0xF0 | (cp >> 18)));
            out.push_back(static_cast<char>(0x80 | ((cp >> 12) & 0x3F)));
            out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
            out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
        }
    }
    return out;
}

class ImeController {
public:
    bool open(const std::string& initial, const std::string& title) {
        if (state_ != State::Idle) {
            psvitaalive::diagnostics::log("[UI] IME open blocked: previous session still draining");
            return false;
        }
        if (!moduleLoadAttempted_) {
            const int r = sceSysmoduleLoadModule(SCE_SYSMODULE_IME);
            moduleLoadAttempted_ = true;
            moduleOwned_ = (r >= 0);
            char b[96];
            sceClibSnprintf(b, sizeof(b), "[UI] SCE_SYSMODULE_IME load=0x%08X owned=%d", r, moduleOwned_ ? 1 : 0);
            psvitaalive::diagnostics::log(b);
        }

        sceClibMemset(inputBuf_, 0, sizeof(inputBuf_));
        sceClibMemset(initialBuf_, 0, sizeof(initialBuf_));
        sceClibMemset(titleBuf_, 0, sizeof(titleBuf_));
        utf8ToUtf16(initial, initialBuf_, kMaxLen + 1);
        utf8ToUtf16(initial, inputBuf_, kMaxLen + 1);
        utf8ToUtf16(title.empty() ? std::string("Search") : title, titleBuf_, SCE_IME_DIALOG_MAX_TITLE_LENGTH + 1);

        SceImeDialogParam param;
        sceImeDialogParamInit(&param);
        param.supportedLanguages = 0x0001FFFF;
        param.languagesForced = SCE_TRUE;
        param.type = SCE_IME_TYPE_DEFAULT;
        param.option = SCE_IME_OPTION_NO_AUTO_CAPITALIZATION;
        param.dialogMode = SCE_IME_DIALOG_DIALOG_MODE_WITH_CANCEL;
        param.textBoxMode = SCE_IME_DIALOG_TEXTBOX_MODE_WITH_CLEAR;
        param.title = titleBuf_;
        param.maxTextLength = kMaxLen;
        param.initialText = initialBuf_;
        param.inputTextBuffer = inputBuf_;
        param.enterLabel = SCE_IME_ENTER_LABEL_SEARCH;

        resultReady_ = false;
        resultAccepted_ = false;
        resultText_.clear();
        noneFrames_ = 0;
        ++sessionId_;

        const int r = sceImeDialogInit(&param);
        char b[128];
        sceClibSnprintf(b, sizeof(b), "[UI] IME session=%u init=0x%08X", sessionId_, r);
        psvitaalive::diagnostics::log(b);
        if (r < 0) {
            const SceCommonDialogStatus st = sceImeDialogGetStatus();
            sceClibSnprintf(b, sizeof(b), "[UI] IME init failed status=%d", static_cast<int>(st));
            psvitaalive::diagnostics::log(b);
            state_ = (st == SCE_COMMON_DIALOG_STATUS_NONE) ? State::Idle : State::Draining;
            return false;
        }
        state_ = State::Running;
        return true;
    }

    void poll() {
        if (state_ == State::Idle) return;
        const SceCommonDialogStatus st = sceImeDialogGetStatus();
        if (state_ == State::Running) {
            if (st == SCE_COMMON_DIALOG_STATUS_FINISHED) {
                SceImeDialogResult result{};
                const int gr = sceImeDialogGetResult(&result);
                resultAccepted_ = (gr >= 0 && result.button == SCE_IME_DIALOG_BUTTON_ENTER);
                resultText_ = resultAccepted_ ? utf16ToUtf8(inputBuf_) : std::string();
                const int tr = sceImeDialogTerm();
                resultReady_ = true;
                state_ = State::Draining;
                noneFrames_ = 0;
                char b[160];
                sceClibSnprintf(b, sizeof(b),
                    "[UI] IME session=%u finished get=0x%08X term=0x%08X accepted=%d",
                    sessionId_, gr, tr, resultAccepted_ ? 1 : 0);
                psvitaalive::diagnostics::log(b);
            } else if (st == SCE_COMMON_DIALOG_STATUS_NONE) {
                resultAccepted_ = false;
                resultText_.clear();
                resultReady_ = true;
                state_ = State::Draining;
                noneFrames_ = 1;
                psvitaalive::diagnostics::log("[UI] IME returned NONE while running; cancelling session");
            }
            return;
        }
        if (st == SCE_COMMON_DIALOG_STATUS_NONE) {
            if (++noneFrames_ >= kSettleFrames) {
                state_ = State::Idle;
                noneFrames_ = 0;
                psvitaalive::diagnostics::log("[UI] IME drain complete");
            }
        } else {
            noneFrames_ = 0;
        }
    }

    bool takeFinished(std::string& text, bool& accepted) {
        if (!resultReady_) return false;
        text = resultText_;
        accepted = resultAccepted_;
        resultReady_ = false;
        return true;
    }

    bool busy() const { return state_ != State::Idle; }

    bool runBlocking(const std::string& initial, const std::string& title, std::string& out) {
        if (!open(initial, title)) return false;
        int frames = 0;
        bool abortRequested = false;
        while (busy()) {
            vita2d_start_drawing();
            vita2d_clear_screen();
            vita2d_draw_rectangle(0, 0, 960, 544, RGBA8(0, 0, 0, 180));
            vita2d_end_drawing();
            vita2d_common_dialog_update();
            vita2d_swap_buffers();
            poll();
            if (!abortRequested && ++frames > 60 * 180) {
                const int ar = sceImeDialogAbort();
                char b[96];
                sceClibSnprintf(b, sizeof(b), "[UI] IME blocking timeout abort=0x%08X", ar);
                psvitaalive::diagnostics::log(b);
                abortRequested = true;
            }
            sceKernelDelayThread(16 * 1000);
        }
        std::string text;
        bool accepted = false;
        if (!takeFinished(text, accepted)) return false;
        if (accepted) out = text;
        return accepted;
    }

    void shutdown() {
        if (state_ != State::Idle) {
            const SceCommonDialogStatus st = sceImeDialogGetStatus();
            if (st == SCE_COMMON_DIALOG_STATUS_RUNNING) sceImeDialogAbort();
            if (st != SCE_COMMON_DIALOG_STATUS_NONE) sceImeDialogTerm();
        }
        state_ = State::Idle;
        resultReady_ = false;
        if (moduleOwned_) {
            const int r = sceSysmoduleUnloadModule(SCE_SYSMODULE_IME);
            char b[96];
            sceClibSnprintf(b, sizeof(b), "[UI] SCE_SYSMODULE_IME unload=0x%08X", r);
            psvitaalive::diagnostics::log(b);
        }
        moduleOwned_ = false;
    }

private:
    enum class State { Idle, Running, Draining };
    static constexpr SceUInt32 kMaxLen = 128;
    static constexpr int kSettleFrames = 3;
    State state_ = State::Idle;
    bool moduleLoadAttempted_ = false;
    bool moduleOwned_ = false;
    bool resultReady_ = false;
    bool resultAccepted_ = false;
    unsigned sessionId_ = 0;
    int noneFrames_ = 0;
    std::string resultText_;
    SceWChar16 inputBuf_[kMaxLen + 1]{};
    SceWChar16 initialBuf_[kMaxLen + 1]{};
    SceWChar16 titleBuf_[SCE_IME_DIALOG_MAX_TITLE_LENGTH + 1]{};
};

ImeController gIme;

bool promptText(const std::string& initial, const std::string& title, std::string& out) {
    return gIme.runBlocking(initial, title, out);
}
'''

main = main[:start] + ime_block + main[end:]

old_search = '    screen.setSearchCallback([&](const std::string&current){std::string result=current;if(promptText(current,"Search catalog",result))return result;return current;});'
new_search = '''    screen.setSearchCallback([&](const std::string& current){
        if (!gIme.open(current, "Search catalog")) {
            psvitaalive::diagnostics::log("[UI] search IME request rejected");
            screen.showToast("Keyboard unavailable", 1800);
        }
    });'''
if main.count(old_search) != 1:
    raise SystemExit(f'Expected one old search callback, found {main.count(old_search)}')
main = main.replace(old_search, new_search, 1)

old_loop = 'while(screen.updateAndDraw()){\n'
new_loop = '''while(true){
        screen.setExternalInputBlocked(gIme.busy());
        if(!screen.updateAndDraw()) break;

        // CommonDialog was serviced during the frame. Poll IME only afterwards
        // so FINISHED -> GetResult -> Term follows the VitaSDK ordering.
        gIme.poll();
        std::string imeText;
        bool imeAccepted = false;
        if(gIme.takeFinished(imeText, imeAccepted) && imeAccepted){
            screen.completeSearch(imeText);
        }
'''
if main.count(old_loop) != 1:
    raise SystemExit(f'Expected one main UI loop, found {main.count(old_loop)}')
main = main.replace(old_loop, new_loop, 1)

old_cleanup = '    screen.setInstallProgress(false,0,0,0,"","","",0,false,"","");screen.shutdown();installer.shutdown();catalogs.shutdown();images.shutdown();psvitaalive::diagnostics::log("PSVitaAlive session END");psvitaalive::diagnostics::shutdown();sceKernelExitProcess(0);return 0;'
new_cleanup = '    screen.setInstallProgress(false,0,0,0,"","","",0,false,"","");gIme.shutdown();screen.shutdown();installer.shutdown();catalogs.shutdown();images.shutdown();sceAppUtilShutdown();psvitaalive::diagnostics::log("PSVitaAlive session END");psvitaalive::diagnostics::shutdown();sceKernelExitProcess(0);return 0;'
if main.count(old_cleanup) != 1:
    raise SystemExit(f'Expected one normal cleanup line, found {main.count(old_cleanup)}')
main = main.replace(old_cleanup, new_cleanup, 1)

required = [
    'class ImeController',
    'ImeController gIme;',
    'gIme.open(current, "Search catalog")',
    'screen.setExternalInputBlocked(gIme.busy());',
    'gIme.poll();',
    'screen.completeSearch(imeText);',
    'return gIme.runBlocking(initial, title, out);',
]
for token in required:
    if token not in main:
        raise SystemExit(f'Missing expected main token: {token}')
if 'applySearch(searchRequest_(searchQuery_))' in cpp:
    raise SystemExit('Synchronous search callback still present')
if 'std::function<std::string(const std::string&)>' in hdr:
    raise SystemExit('Old SearchRequestFn signature still present')

main_path.write_text(main, encoding='utf-8')
hdr_path.write_text(hdr, encoding='utf-8')
cpp_path.write_text(cpp, encoding='utf-8')

print('Async IME patch applied')
print(f'CommonDialog frame endings replaced: {compact_n + spaced_n}')
