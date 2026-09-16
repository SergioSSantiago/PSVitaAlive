from pathlib import Path

path = Path('Client PSVitaAlive/source/main.cpp')
s = path.read_text(encoding='utf-8')

start = s.find('class ImeController {')
end_marker = '\n};\n\nImeController gIme;'
end = s.find(end_marker, start)
if start < 0 or end < 0:
    raise SystemExit('Could not locate ImeController class')
end += len('\n};')

old = s[start:end]
if 'State::Draining' not in old or 'sceSysmoduleLoadModule(SCE_SYSMODULE_IME)' not in old:
    raise SystemExit('Current ImeController does not match expected pre-fix implementation')

new = r'''class ImeController {
public:
    bool open(const std::string& initial, const std::string& title) {
        if (state_ != State::Idle) {
            psvitaalive::diagnostics::log("[UI] IME open blocked: previous session still cooling down");
            return false;
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
        cooldownFrames_ = 0;
        ++sessionId_;

        // Do not explicitly load SCE_SYSMODULE_IME here. The official VitaSDK
        // sample, VitaShell and pkgj use sceImeDialogInit directly. Keeping the
        // lifecycle owned by CommonDialog avoids accumulating/competing module
        // state across many open/close cycles.
        const int r = sceImeDialogInit(&param);
        char b[128];
        sceClibSnprintf(b, sizeof(b), "[UI] IME session=%u init=0x%08X", sessionId_, r);
        psvitaalive::diagnostics::log(b);
        if (r < 0) {
            state_ = State::Idle;
            return false;
        }

        state_ = State::Running;
        return true;
    }

    void poll() {
        if (state_ == State::Idle) return;

        // IMPORTANT: after sceImeDialogTerm(), do not call any sceImeDialog*
        // status/result function again until a new session is initialized.
        // VitaSDK's sample and long-lived apps stop polling the terminated IME.
        // We only keep servicing CommonDialog in the normal render loop and
        // wait a few frames before allowing another sceImeDialogInit().
        if (state_ == State::Cooldown) {
            if (++cooldownFrames_ >= kCooldownFrames) {
                state_ = State::Idle;
                cooldownFrames_ = 0;
                psvitaalive::diagnostics::log("[UI] IME cooldown complete");
            }
            return;
        }

        const SceCommonDialogStatus st = sceImeDialogGetStatus();
        if (st == SCE_COMMON_DIALOG_STATUS_FINISHED) {
            SceImeDialogResult result{};
            const int gr = sceImeDialogGetResult(&result);
            resultAccepted_ = (gr >= 0 && result.button == SCE_IME_DIALOG_BUTTON_ENTER);
            resultText_ = resultAccepted_ ? utf16ToUtf8(inputBuf_) : std::string();
            const int tr = sceImeDialogTerm();
            resultReady_ = true;
            state_ = State::Cooldown;
            cooldownFrames_ = 0;

            char b[160];
            sceClibSnprintf(b, sizeof(b),
                "[UI] IME session=%u finished get=0x%08X term=0x%08X accepted=%d",
                sessionId_, gr, tr, resultAccepted_ ? 1 : 0);
            psvitaalive::diagnostics::log(b);
        } else if (st == SCE_COMMON_DIALOG_STATUS_NONE) {
            // An initialized dialog unexpectedly disappearing is treated as a
            // cancelled session. Do not call Term/GetStatus again; let the
            // CommonDialog renderer settle before another initialization.
            resultAccepted_ = false;
            resultText_.clear();
            resultReady_ = true;
            state_ = State::Cooldown;
            cooldownFrames_ = 0;
            psvitaalive::diagnostics::log("[UI] IME returned NONE while running; entering cooldown");
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
            if (!abortRequested && state_ == State::Running && ++frames > 60 * 180) {
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
        // Only query the IME while this controller still owns a running
        // session. Never query it again after sceImeDialogTerm().
        if (state_ == State::Running) {
            const SceCommonDialogStatus st = sceImeDialogGetStatus();
            if (st == SCE_COMMON_DIALOG_STATUS_RUNNING) {
                const int ar = sceImeDialogAbort();
                char b[96];
                sceClibSnprintf(b, sizeof(b), "[UI] IME shutdown abort=0x%08X", ar);
                psvitaalive::diagnostics::log(b);
            } else if (st == SCE_COMMON_DIALOG_STATUS_FINISHED) {
                sceImeDialogTerm();
            }
        }
        state_ = State::Idle;
        resultReady_ = false;
        resultAccepted_ = false;
        cooldownFrames_ = 0;
    }

private:
    enum class State { Idle, Running, Cooldown };
    static constexpr SceUInt32 kMaxLen = 128;
    // The official sample effectively gives CommonDialog at least one update
    // after Term before reinitializing. Four frames (~64 ms at 60 Hz) add a
    // conservative margin without touching the terminated IME API.
    static constexpr int kCooldownFrames = 4;
    State state_ = State::Idle;
    bool resultReady_ = false;
    bool resultAccepted_ = false;
    unsigned sessionId_ = 0;
    int cooldownFrames_ = 0;
    std::string resultText_;
    SceWChar16 inputBuf_[kMaxLen + 1]{};
    SceWChar16 initialBuf_[kMaxLen + 1]{};
    SceWChar16 titleBuf_[SCE_IME_DIALOG_MAX_TITLE_LENGTH + 1]{};
};'''

s = s[:start] + new + s[end:]
path.write_text(s, encoding='utf-8')

# Static guards: the stress fix must remove the post-Term status-drain model
# and explicit IME sysmodule ownership from this controller.
updated = path.read_text(encoding='utf-8')
controller = updated[updated.find('class ImeController {'):updated.find('\n};\n\nImeController gIme;')]
if 'State::Draining' in controller or 'moduleOwned_' in controller or 'moduleLoadAttempted_' in controller:
    raise SystemExit('Old drain/module state remains in ImeController')
if 'sceSysmoduleLoadModule(SCE_SYSMODULE_IME)' in controller or 'sceSysmoduleUnloadModule(SCE_SYSMODULE_IME)' in controller:
    raise SystemExit('Explicit IME sysmodule lifecycle remains in ImeController')
if 'State::Cooldown' not in controller or 'kCooldownFrames = 4' not in controller:
    raise SystemExit('Cooldown lifecycle was not installed')

print('IME stress fix applied successfully')
