#pragma once

#include "network/http_client.hpp"
#include "network/download_manager.hpp"
#include "installer/install_dispatcher.hpp"
#include "installer/app_settings.hpp"
#include "installer/plugin_detector.hpp"

#include <psp2/types.h>

#include <atomic>
#include <string>

namespace psvitaalive {

struct InstallStatus {
    enum class State {
        Idle = 0,
        Downloading,
        Installing,
        Completed,
        Failed,
        Cancelled
    };
    State state = State::Idle;
    uint64_t current = 0;
    uint64_t total = 0;
    uint64_t bytesPerSecond = 0;
    std::string message;
    std::string fileName;
    std::string stage;
    std::string installPath;
    std::string titleId;
    bool liveAreaOk = false;
    uint64_t resultAutoCloseRemainingMs = 0;
    bool needsReboot = false;
};

class InstallController {
public:
    InstallController();
    ~InstallController();

    bool init();
    void shutdown();

    bool requestInstall(
        const std::string& url,
        const std::string& fileName,
        const std::string& zipDestination = std::string(),
        const std::string& zrif = std::string(),
        const std::string& linkType = std::string(),
        const std::string& contentId = std::string(),
        const std::string& displayTitle = std::string(),
        uint64_t expectedBytes = 0,
        const std::string& pluginSection = std::string(),
        const std::string& pluginLine = std::string()
    );
    void cancel();
    void acknowledgeResult();
    InstallStatus status() const;

    bool busy() const;

    const AppSettingsData& settings() const { return settings_; }
    void setSettings(const AppSettingsData& s);

    const PluginStatus& plugins() const { return plugins_; }

    /** Catalog identity for the install about to start (optional; used for receipts). */
    void setPendingCatalogMeta(const std::string& appId, const std::string& version,
                               const std::string& versionDate = std::string(), int revision = 0);

private:
    HttpClient http_;
    DownloadManager downloads_;
    InstallDispatcher dispatcher_;
    AppSettingsData settings_{};
    PluginStatus plugins_{};

    SceUID workerThread_ = -1;
    SceUID keepAwakeThread_ = -1;
    std::atomic<bool> keepAwakeStop_{true};
    bool shellUtilReady_ = false;
    bool shellLocked_ = false;

    bool activeBgdlJob_ = false;
    std::string pendingAppId_;
    std::string pendingCatalogVersion_;
    std::string pendingVersionDate_;
    int pendingReleaseRevision_ = 0;
    std::string activeBgdlUrl_;
    std::string activeBgdlTitle_;
    std::string activeBgdlLinkType_;
    std::string activeJobId_;
    std::string activeZipDestination_;
    std::string activeFileName_;
    std::string activeZrif_;
    std::string activeContentId_;
    std::string activeLinkType_;
    std::string activePluginSection_;
    std::string activePluginLine_;
    std::atomic<bool> needsReboot_{false};

    std::atomic<int> state_{static_cast<int>(InstallStatus::State::Idle)};
    std::atomic<uint64_t> current_{0};
    std::atomic<uint64_t> total_{0};
    std::atomic<uint64_t> speed_{0};
    std::atomic<bool> workerDone_{true};
    std::atomic<bool> liveAreaOk_{false};
    std::atomic<uint64_t> resultShownAtMs_{0};

    char message_[384] = {};
    char fileName_[256] = {};
    char stage_[64] = {};
    char installPath_[256] = {};
    char titleId_[32] = {};

    static int workerEntry(SceSize args, void* argp);
    int workerMain();

    static int keepAwakeEntry(SceSize args, void* argp);
    void startKeepAwakeThread();
    void stopKeepAwakeThread();

    void lockShellDuringJob();
    void unlockShellDuringJob();

    void setMessage(const char* text);
    void setFileName(const char* text);
    void setStage(const char* text);
    void setInstallPath(const char* text);
    void setTitleId(const char* text);
    void setState(InstallStatus::State state, const char* message);
    void maybeAutoAcknowledgeResult();
};

} // namespace psvitaalive
