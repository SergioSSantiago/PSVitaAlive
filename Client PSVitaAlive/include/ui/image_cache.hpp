#pragma once

#include <psp2/kernel/threadmgr.h>

#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace psvitaalive {
namespace ui {

class ImageCache {
public:
    ImageCache();
    ~ImageCache();

    bool init();
    void shutdown();

    std::string request(const std::string& url, const std::string& namespaceName);
    /** Resolve local cache path without queueing a download. */
    std::string pathFor(const std::string& url, const std::string& namespaceName) const;
    /** Drop queued jobs whose path is not in keep (active download is left alone). */
    void cancelQueuedExcept(const std::unordered_set<std::string>& keep);

    // Queue a remote image for background download without requiring it to be
    // visible on screen. Used at startup to warm the complete catalog cache.
    void preload(const std::vector<std::string>& urls, const std::string& namespaceName);

    bool isReady(const std::string& localPath) const;
    bool isFailed(const std::string& localPath) const;
    bool isPending(const std::string& localPath) const;
    bool isCached(const std::string& url, const std::string& namespaceName) const;

    struct ProgressSnapshot {
        bool active = false;
        uint64_t downloaded = 0;
        uint64_t total = 0;
        uint64_t speed = 0;
        uint64_t completedBytes = 0;
        uint64_t knownTotalBytes = 0;
        std::string fileName;
        std::string localPath;
    };

    ProgressSnapshot progress() const;
    void resetProgress();

    // Cancel queued and active image work. The active partial file is removed
    // by the worker after libcurl acknowledges the cancellation.
    void cancelAll();
    void cancelQueuedRequests();

    /** Pause background image downloads so install/VPK bandwidth is not shared. */
    void setNetworkPaused(bool paused);
    bool networkPaused() const { return networkPaused_; }

private:
    struct Job {
        std::string url;
        std::string path;
        int attempt = 0;
    };

    SceUID mutex_ = -1;
    SceUID workerThread_ = -1;
    volatile bool stopping_ = false;
    volatile bool cancelRequested_ = false;
    volatile bool networkPaused_ = false;
    std::vector<Job> queue_;
    std::vector<std::string> pending_;
    std::vector<std::string> ready_;
    std::vector<std::string> failed_;
    std::unordered_map<std::string, uint64_t> retryAfter_;

    // Per-catalog image manifest state. The parser writes a tiny revisioned
    // manifest for H/PV/PSP/PS1; ImageCache uses it to garbage-collect stale
    // files without loading other catalogs into RAM.
    std::unordered_map<std::string, uint64_t> manifestRevision_;
    std::unordered_map<std::string, uint64_t> manifestCheckAfter_;

    std::string currentFile_;
    std::string currentPath_;
    uint64_t currentDownloaded_ = 0;
    uint64_t currentTotal_ = 0;
    uint64_t currentSpeed_ = 0;
    uint64_t completedBytes_ = 0;
    uint64_t completedTotalBytes_ = 0;
    bool bulkPreload_ = false;

    static int workerEntry(SceSize args, void* argp);
    int workerMain();

    std::string makePath(const std::string& url, const std::string& namespaceName) const;
    bool contains(const std::vector<std::string>& values, const std::string& value) const;
    bool ensureDirectory(const std::string& path) const;
    void pruneCatalogIfNeeded(const std::string& catalogPrefix);
    void markReady(const std::string& path);
    void markFailed(const std::string& path);
};

} // namespace ui
} // namespace psvitaalive
