#include "ui/mascot_manager.hpp"

#include "diagnostic_logger.hpp"

#include <vita2d.h>
#include <psp2/gxm.h>
#include <psp2/io/dirent.h>
#include <psp2/io/fcntl.h>
#include <psp2/io/stat.h>
#include <psp2/json.h>
#include <psp2/kernel/clib.h>
#include <psp2/kernel/processmgr.h>
#include <psp2/sysmodule.h>

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <string>
#include <utility>
#include <vector>

namespace psvitaalive::ui {
namespace {

constexpr const char* kInternalRoot = "app0:mascots";
constexpr const char* kUserRoot = "ux0:data/psvitaalive/mascots";
constexpr float kScreenW = 960.0f;
constexpr float kScreenH = 544.0f;
constexpr float kSafeMargin = 16.0f;
constexpr float kLogicalW = 100.0f;
constexpr float kLogicalH = 100.0f;
constexpr float kMinRunDistance = 100.0f;
constexpr size_t kMaxAnimationsPerState = 16;
constexpr size_t kMaxFramesPerAnimation = 32;
constexpr size_t kMaxFramesTotal = 64;
constexpr uint32_t kMinFrameMs = 16;
constexpr uint32_t kMaxFrameMs = 10000;
constexpr uint32_t kMaxIdleMs = 120000;
constexpr uint32_t kMaxRunMs = 60000;
constexpr float kMaxRunSpeed = 1000.0f;

class VitaJsonAllocator final : public sce::Json::MemAllocator {
public:
    void* allocateMemory(SceSize size, void* userData) override {
        (void)userData;
        return std::malloc(size);
    }
    void freeMemory(void* ptr, void* userData) override {
        (void)userData;
        std::free(ptr);
    }
};

struct AnimationDef {
    std::string name;
    uint32_t frameMs = 100;
    std::vector<std::string> frameFiles;
};

struct ManifestDef {
    std::string name;
    bool nativeFacesRight = true;
    float runSpeed = 150.0f;
    uint32_t idleMinMs = 2000;
    uint32_t idleMaxMs = 5000;
    uint32_t runMaxMs = 4000;
    std::vector<AnimationDef> idle;
    std::vector<AnimationDef> run;
};

struct LoadedAnimation {
    std::string name;
    uint32_t frameMs = 100;
    std::vector<vita2d_texture*> frames;
};

std::string lowerAscii(std::string value) {
    for (char& c : value)
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return value;
}

std::string pathJoin(const std::string& base, const std::string& leaf) {
    if (base.empty()) return leaf;
    if (!base.empty() && base.back() == '/') return base + leaf;
    return base + "/" + leaf;
}

bool fileExists(const std::string& path) {
    SceIoStat st{};
    return sceIoGetstat(path.c_str(), &st) >= 0;
}

bool safeFrameName(const std::string& value) {
    if (value.empty() || value.size() > 120) return false;
    if (value == "." || value == "..") return false;
    if (value.find('/') != std::string::npos || value.find('\\') != std::string::npos ||
        value.find(':') != std::string::npos || value.find("..") != std::string::npos)
        return false;
    const std::string low = lowerAscii(value);
    return low.size() > 4 && low.compare(low.size() - 4, 4, ".png") == 0;
}

std::string jsonString(const sce::Json::Value& object, const char* key) {
    const sce::Json::Value& value = object[key];
    if (!value) return {};
    return value.getString().c_str();
}

uint32_t jsonUInt(const sce::Json::Value& object, const char* key, uint32_t fallback) {
    const sce::Json::Value& value = object[key];
    if (!value) return fallback;
    return static_cast<uint32_t>(value.getUInteger());
}

bool parseAnimations(const sce::Json::Value& animationsRoot,
                     const char* key,
                     const std::string& basePath,
                     std::vector<AnimationDef>& out,
                     size_t& totalFrames) {
    const sce::Json::Value& listValue = animationsRoot[key];
    if (!listValue) return false;
    const sce::Json::Array& list = listValue.getArray();
    if (list.empty() || list.size() > kMaxAnimationsPerState) return false;

    out.clear();
    out.reserve(list.size());
    for (SceSize i = 0; i < list.size(); ++i) {
        const sce::Json::Value& item = listValue[i];
        AnimationDef animation;
        animation.name = jsonString(item, "name");
        animation.frameMs = jsonUInt(item, "frame_ms", 0);
        if (animation.name.empty() || animation.frameMs < kMinFrameMs || animation.frameMs > kMaxFrameMs)
            return false;

        const sce::Json::Value& framesValue = item["frames"];
        if (!framesValue) return false;
        const sce::Json::Array& frames = framesValue.getArray();
        if (frames.empty() || frames.size() > kMaxFramesPerAnimation) return false;
        if (totalFrames + frames.size() > kMaxFramesTotal) return false;

        animation.frameFiles.reserve(frames.size());
        for (SceSize f = 0; f < frames.size(); ++f) {
            const sce::Json::Value& frameValue = framesValue[f];
            if (!frameValue) return false;
            const std::string frame = frameValue.getString().c_str();
            if (!safeFrameName(frame) || !fileExists(pathJoin(basePath, frame))) return false;
            animation.frameFiles.push_back(frame);
        }
        totalFrames += frames.size();
        out.push_back(std::move(animation));
    }
    return true;
}

bool parseManifest(const std::string& basePath, ManifestDef& out, std::string& error) {
    const std::string manifestPath = pathJoin(basePath, "mascot.json");
    SceIoStat st{};
    if (sceIoGetstat(manifestPath.c_str(), &st) < 0) {
        error = "missing mascot.json";
        return false;
    }
    if (st.st_size <= 0 || st.st_size > 64 * 1024) {
        error = "manifest size invalid";
        return false;
    }

    // The module may already be loaded by the catalog parser. Loading again is harmless on
    // supported VitaSDK runtimes; parsing below remains the authoritative success check.
    (void)sceSysmoduleLoadModule(SCE_SYSMODULE_JSON);

    VitaJsonAllocator allocator;
    sce::Json::InitParameter params;
    params.allocator = &allocator;
    params.userData = nullptr;
    params.bufSize = 16 * 1024;

    sce::Json::Initializer initializer;
    const int initResult = initializer.initialize(&params);
    if (initResult < 0) {
        char buf[64];
        sceClibSnprintf(buf, sizeof(buf), "json init 0x%08X", initResult);
        error = buf;
        return false;
    }

    sce::Json::Value root;
    const int parseResult = sce::Json::Parser::parse(root, manifestPath.c_str());
    if (parseResult < 0) {
        char buf[64];
        sceClibSnprintf(buf, sizeof(buf), "json parse 0x%08X", parseResult);
        error = buf;
        initializer.terminate();
        return false;
    }

    bool ok = true;
    const uint32_t schema = jsonUInt(root, "schema_version", 0);
    if (schema != 1) {
        error = "unsupported schema_version";
        ok = false;
    }

    ManifestDef parsed;
    if (ok) {
        parsed.name = jsonString(root, "name");
        const std::string facing = lowerAscii(jsonString(root, "native_facing"));
        const uint32_t logicalW = jsonUInt(root, "width", 100);
        const uint32_t logicalH = jsonUInt(root, "height", 100);
        if (parsed.name.empty() || parsed.name.size() > 96 ||
            (facing != "left" && facing != "right") || logicalW != 100 || logicalH != 100) {
            error = "invalid identity/logical size";
            ok = false;
        } else {
            parsed.nativeFacesRight = facing == "right";
        }
    }

    if (ok) {
        const sce::Json::Value& behavior = root["behavior"];
        if (!behavior) {
            error = "missing behavior";
            ok = false;
        } else {
            const uint32_t speed = jsonUInt(behavior, "run_speed", 0);
            parsed.idleMinMs = jsonUInt(behavior, "idle_min_ms", 0);
            parsed.idleMaxMs = jsonUInt(behavior, "idle_max_ms", 0);
            parsed.runMaxMs = jsonUInt(behavior, "run_max_ms", 0);
            parsed.runSpeed = static_cast<float>(speed);
            if (speed == 0 || parsed.runSpeed > kMaxRunSpeed || parsed.idleMinMs == 0 ||
                parsed.idleMinMs > kMaxIdleMs || parsed.idleMaxMs < parsed.idleMinMs ||
                parsed.idleMaxMs > kMaxIdleMs || parsed.runMaxMs == 0 || parsed.runMaxMs > kMaxRunMs) {
                error = "invalid behavior values";
                ok = false;
            }
        }
    }

    if (ok) {
        const sce::Json::Value& animations = root["animations"];
        if (!animations) {
            error = "missing animations";
            ok = false;
        } else {
            size_t totalFrames = 0;
            if (!parseAnimations(animations, "idle", basePath, parsed.idle, totalFrames) ||
                !parseAnimations(animations, "run", basePath, parsed.run, totalFrames)) {
                error = "invalid animation/frame list";
                ok = false;
            }
        }
    }

    initializer.terminate();
    if (ok) out = std::move(parsed);
    return ok;
}

uint32_t seedFromClock() {
    const uint64_t t = sceKernelGetProcessTimeWide();
    uint32_t seed = static_cast<uint32_t>(t ^ (t >> 32) ^ 0x7F4A7C15u);
    return seed ? seed : 0xA341316Cu;
}

void freeAnimations(std::vector<LoadedAnimation>& animations) {
    for (auto& animation : animations) {
        for (vita2d_texture* texture : animation.frames) {
            if (texture) vita2d_free_texture(texture);
        }
        animation.frames.clear();
    }
    animations.clear();
}

} // namespace

struct MascotManager::Impl {
    enum class State { Idle = 0, Run };

    std::vector<MascotInfo> catalog;
    std::vector<LoadedAnimation> idle;
    std::vector<LoadedAnimation> run;
    std::string activeKey;
    std::string lastRandomKey;
    bool nativeFacesRight = true;
    bool facingRight = true;
    bool active = false;
    float runSpeed = 150.0f;
    uint32_t idleMinMs = 2000;
    uint32_t idleMaxMs = 5000;
    uint32_t runMaxMs = 4000;
    State state = State::Idle;
    float x = kSafeMargin;
    float y = kSafeMargin;
    float targetX = kSafeMargin;
    float targetY = kSafeMargin;
    size_t animationIndex = 0;
    size_t previousIdleAnimation = static_cast<size_t>(-1);
    size_t previousRunAnimation = static_cast<size_t>(-1);
    size_t frameIndex = 0;
    uint64_t stateStartMs = 0;
    uint64_t stateDurationMs = 0;
    uint64_t frameStartMs = 0;
    uint64_t lastUpdateMs = 0;
    uint32_t rng = 0;

    uint32_t random() {
        if (rng == 0) rng = seedFromClock();
        uint32_t v = rng;
        v ^= v << 13;
        v ^= v >> 17;
        v ^= v << 5;
        rng = v ? v : 0xA341316Cu;
        return rng;
    }

    float randomFloat(float minValue, float maxValue) {
        if (maxValue <= minValue) return minValue;
        const float unit = static_cast<float>(random() & 0x00FFFFFFu) / static_cast<float>(0x01000000u);
        return minValue + (maxValue - minValue) * unit;
    }

    size_t randomIndex(size_t count) {
        return count ? static_cast<size_t>(random() % static_cast<uint32_t>(count)) : 0;
    }

    void clearLoaded() {
        if (!idle.empty() || !run.empty()) vita2d_wait_rendering_done();
        freeAnimations(idle);
        freeAnimations(run);
        active = false;
        activeKey.clear();
    }

    bool loadAnimations(const std::string& basePath,
                        const std::vector<AnimationDef>& defs,
                        std::vector<LoadedAnimation>& out) {
        out.clear();
        out.reserve(defs.size());
        for (const auto& def : defs) {
            LoadedAnimation loaded;
            loaded.name = def.name;
            loaded.frameMs = def.frameMs;
            loaded.frames.reserve(def.frameFiles.size());
            for (const auto& file : def.frameFiles) {
                const std::string path = pathJoin(basePath, file);
                vita2d_texture* texture = vita2d_load_PNG_file(path.c_str());
                if (!texture) {
                    diagnostics::log(std::string("[Mascot] PNG load failed: ") + path);
                    for (vita2d_texture* existing : loaded.frames) if (existing) vita2d_free_texture(existing);
                    loaded.frames.clear();
                    freeAnimations(out);
                    return false;
                }
                vita2d_texture_set_filters(texture, SCE_GXM_TEXTURE_FILTER_POINT, SCE_GXM_TEXTURE_FILTER_POINT);
                loaded.frames.push_back(texture);
            }
            out.push_back(std::move(loaded));
        }
        return !out.empty();
    }

    bool load(const MascotInfo& info) {
        ManifestDef manifest;
        std::string error;
        if (!parseManifest(info.basePath, manifest, error)) {
            diagnostics::log(std::string("[Mascot] rejected ") + info.key + ": " + error);
            return false;
        }

        std::vector<LoadedAnimation> nextIdle;
        std::vector<LoadedAnimation> nextRun;
        if (!loadAnimations(info.basePath, manifest.idle, nextIdle) ||
            !loadAnimations(info.basePath, manifest.run, nextRun)) {
            freeAnimations(nextIdle);
            freeAnimations(nextRun);
            return false;
        }

        clearLoaded();
        idle = std::move(nextIdle);
        run = std::move(nextRun);
        nativeFacesRight = manifest.nativeFacesRight;
        facingRight = manifest.nativeFacesRight;
        runSpeed = manifest.runSpeed;
        idleMinMs = manifest.idleMinMs;
        idleMaxMs = manifest.idleMaxMs;
        runMaxMs = manifest.runMaxMs;
        activeKey = info.key;
        active = true;
        return true;
    }

    void choosePosition() {
        const float maxX = kScreenW - kSafeMargin - kLogicalW;
        const float maxY = kScreenH - kSafeMargin - kLogicalH;
        x = randomFloat(kSafeMargin, maxX);
        y = randomFloat(kSafeMargin, maxY);
    }

    size_t chooseAnimation(const std::vector<LoadedAnimation>& list, size_t previous) {
        if (list.empty()) return 0;
        if (list.size() == 1) return 0;
        size_t idx = randomIndex(list.size());
        for (int attempt = 0; attempt < 6 && idx == previous; ++attempt)
            idx = randomIndex(list.size());
        return idx;
    }

    void chooseTarget() {
        const float maxX = kScreenW - kSafeMargin - kLogicalW;
        const float maxY = kScreenH - kSafeMargin - kLogicalH;
        float bestX = x;
        float bestY = y;
        for (int attempt = 0; attempt < 12; ++attempt) {
            bestX = randomFloat(kSafeMargin, maxX);
            bestY = randomFloat(kSafeMargin, maxY);
            if (std::hypot(bestX - x, bestY - y) >= kMinRunDistance) break;
        }
        targetX = bestX;
        targetY = bestY;
        const float dx = targetX - x;
        if (std::fabs(dx) > 0.5f) facingRight = dx > 0.0f;
    }

    void beginState(State next, uint64_t nowMs) {
        state = next;
        stateStartMs = nowMs;
        frameStartMs = nowMs;
        frameIndex = 0;
        if (state == State::Idle) {
            animationIndex = chooseAnimation(idle, previousIdleAnimation);
            previousIdleAnimation = animationIndex;
            stateDurationMs = static_cast<uint64_t>(randomFloat(static_cast<float>(idleMinMs), static_cast<float>(idleMaxMs)));
        } else {
            animationIndex = chooseAnimation(run, previousRunAnimation);
            previousRunAnimation = animationIndex;
            stateDurationMs = runMaxMs;
            chooseTarget();
        }
    }

    void beginRandomState(uint64_t nowMs) {
        beginState((random() & 1u) ? State::Run : State::Idle, nowMs);
    }

    LoadedAnimation* currentAnimation() {
        std::vector<LoadedAnimation>& list = state == State::Idle ? idle : run;
        if (list.empty()) return nullptr;
        if (animationIndex >= list.size()) animationIndex = 0;
        return &list[animationIndex];
    }

    const LoadedAnimation* currentAnimation() const {
        const std::vector<LoadedAnimation>& list = state == State::Idle ? idle : run;
        if (list.empty()) return nullptr;
        const size_t idx = animationIndex < list.size() ? animationIndex : 0;
        return &list[idx];
    }
};

MascotManager::MascotManager() : impl_(new Impl()) {}

MascotManager::~MascotManager() {
    if (impl_) {
        impl_->clearLoaded();
        delete impl_;
        impl_ = nullptr;
    }
}

void MascotManager::scan() {
    if (!impl_) return;
    // Settings/protector never calls scan while rendering a mascot, but be defensive.
    if (impl_->active) impl_->clearLoaded();
    impl_->catalog.clear();

    (void)sceIoMkdir("ux0:data/psvitaalive", 0777);
    (void)sceIoMkdir(kUserRoot, 0777);

    auto scanRoot = [&](const char* root, MascotSource source, const char* prefix) {
        SceUID dir = sceIoDopen(root);
        if (dir < 0) return;
        SceIoDirent entry{};
        while (sceIoDread(dir, &entry) > 0) {
            const std::string id = entry.d_name;
            std::memset(&entry, 0, sizeof(entry));
            if (id.empty() || id == "." || id == ".." || id.size() > 80) continue;
            if (id.find('/') != std::string::npos || id.find('\\') != std::string::npos || id.find(':') != std::string::npos) continue;
            const std::string basePath = pathJoin(root, id);
            if (!fileExists(pathJoin(basePath, "mascot.json"))) continue;

            ManifestDef manifest;
            std::string error;
            if (!parseManifest(basePath, manifest, error)) {
                diagnostics::log(std::string("[Mascot] scan skip ") + basePath + ": " + error);
                continue;
            }
            MascotInfo info;
            info.key = std::string(prefix) + ":" + id;
            info.id = id;
            info.name = manifest.name;
            info.basePath = basePath;
            info.source = source;
            impl_->catalog.push_back(std::move(info));
        }
        sceIoDclose(dir);
    };

    scanRoot(kInternalRoot, MascotSource::Internal, "internal");
    scanRoot(kUserRoot, MascotSource::User, "user");

    std::sort(impl_->catalog.begin(), impl_->catalog.end(), [](const MascotInfo& a, const MascotInfo& b) {
        const std::string an = lowerAscii(a.name);
        const std::string bn = lowerAscii(b.name);
        if (an != bn) return an < bn;
        if (a.source != b.source) return a.source == MascotSource::Internal;
        return lowerAscii(a.id) < lowerAscii(b.id);
    });

    diagnostics::log(std::string("[Mascot] scan complete count=") + std::to_string(impl_->catalog.size()));
}

const std::vector<MascotInfo>& MascotManager::mascots() const {
    static const std::vector<MascotInfo> empty;
    return impl_ ? impl_->catalog : empty;
}

const MascotInfo* MascotManager::find(const std::string& key) const {
    if (!impl_) return nullptr;
    for (const auto& info : impl_->catalog)
        if (info.key == key) return &info;
    return nullptr;
}

std::string MascotManager::cycleSelection(const std::string& current, int delta) const {
    if (!impl_ || delta == 0) return current.empty() ? "random" : current;
    std::vector<std::string> keys;
    keys.reserve(2 + impl_->catalog.size());
    keys.emplace_back("random");
    keys.emplace_back("off");
    for (const auto& info : impl_->catalog) keys.push_back(info.key);

    int index = 0;
    for (size_t i = 0; i < keys.size(); ++i) {
        if (keys[i] == current) {
            index = static_cast<int>(i);
            break;
        }
    }
    const int count = static_cast<int>(keys.size());
    index = (index + (delta > 0 ? 1 : -1)) % count;
    if (index < 0) index += count;
    return keys[static_cast<size_t>(index)];
}

bool MascotManager::start(const std::string& selection, uint64_t nowMs) {
    if (!impl_) return false;
    impl_->clearLoaded();
    if (selection == "off") {
        diagnostics::log("[Mascot] protector mascot disabled by settings");
        return false;
    }
    if (impl_->catalog.empty()) scan();
    if (impl_->catalog.empty()) {
        diagnostics::log("[Mascot] no valid mascots available; protector continues without mascot");
        return false;
    }

    std::vector<size_t> order;
    order.reserve(impl_->catalog.size());
    const MascotInfo* explicitInfo = nullptr;
    if (!selection.empty() && selection != "random") explicitInfo = find(selection);
    if (explicitInfo) {
        order.push_back(static_cast<size_t>(explicitInfo - impl_->catalog.data()));
    }

    // Random, missing explicit selection, or fallback after an invalid PNG: try every candidate.
    std::vector<size_t> randomPool;
    randomPool.reserve(impl_->catalog.size());
    for (size_t i = 0; i < impl_->catalog.size(); ++i) {
        if (!order.empty() && i == order.front()) continue;
        randomPool.push_back(i);
    }
    while (!randomPool.empty()) {
        size_t pick = impl_->randomIndex(randomPool.size());
        // Avoid the immediately previous Random mascot where possible.
        if ((selection == "random" || !explicitInfo) && randomPool.size() > 1 &&
            impl_->catalog[randomPool[pick]].key == impl_->lastRandomKey) {
            pick = (pick + 1) % randomPool.size();
        }
        order.push_back(randomPool[pick]);
        randomPool.erase(randomPool.begin() + static_cast<std::ptrdiff_t>(pick));
    }

    if ((selection == "random" || !explicitInfo) && order.size() > 1 &&
        impl_->catalog[order.front()].key == impl_->lastRandomKey) {
        std::swap(order[0], order[1]);
    }

    for (size_t index : order) {
        const MascotInfo& info = impl_->catalog[index];
        if (!impl_->load(info)) continue;
        impl_->choosePosition();
        impl_->lastUpdateMs = nowMs;
        impl_->beginRandomState(nowMs);
        if (selection == "random" || !explicitInfo) impl_->lastRandomKey = info.key;
        diagnostics::log(std::string("[Mascot] protector started key=") + info.key + " name=" + info.name);
        return true;
    }

    diagnostics::log("[Mascot] all candidate mascots failed to load; protector continues without mascot");
    return false;
}

void MascotManager::stop() {
    if (!impl_) return;
    const bool wasActive = impl_->active;
    const std::string oldKey = impl_->activeKey;
    impl_->clearLoaded();
    if (wasActive) diagnostics::log(std::string("[Mascot] protector stopped key=") + oldKey);
}

void MascotManager::update(uint64_t nowMs) {
    if (!impl_ || !impl_->active) return;
    if (impl_->lastUpdateMs == 0 || nowMs < impl_->lastUpdateMs) impl_->lastUpdateMs = nowMs;
    const uint64_t deltaMsRaw = nowMs - impl_->lastUpdateMs;
    impl_->lastUpdateMs = nowMs;
    const float dt = static_cast<float>(std::min<uint64_t>(deltaMsRaw, 100)) / 1000.0f;

    LoadedAnimation* animation = impl_->currentAnimation();
    if (animation && !animation->frames.empty()) {
        const uint64_t frameMs = std::max<uint32_t>(1, animation->frameMs);
        if (nowMs >= impl_->frameStartMs && nowMs - impl_->frameStartMs >= frameMs) {
            const uint64_t steps = std::max<uint64_t>(1, (nowMs - impl_->frameStartMs) / frameMs);
            impl_->frameIndex = (impl_->frameIndex + static_cast<size_t>(steps)) % animation->frames.size();
            impl_->frameStartMs += steps * frameMs;
        }
    }

    if (impl_->state == Impl::State::Idle) {
        if (nowMs >= impl_->stateStartMs && nowMs - impl_->stateStartMs >= impl_->stateDurationMs)
            impl_->beginRandomState(nowMs);
        return;
    }

    const float dx = impl_->targetX - impl_->x;
    const float dy = impl_->targetY - impl_->y;
    const float distance = std::hypot(dx, dy);
    if (std::fabs(dx) > 0.5f) impl_->facingRight = dx > 0.0f;
    const float step = std::max(0.0f, impl_->runSpeed) * dt;
    bool done = false;
    if (distance <= std::max(1.0f, step)) {
        impl_->x = impl_->targetX;
        impl_->y = impl_->targetY;
        done = true;
    } else if (distance > 0.0f) {
        impl_->x += (dx / distance) * step;
        impl_->y += (dy / distance) * step;
    }

    const float maxX = kScreenW - kSafeMargin - kLogicalW;
    const float maxY = kScreenH - kSafeMargin - kLogicalH;
    impl_->x = std::max(kSafeMargin, std::min(maxX, impl_->x));
    impl_->y = std::max(kSafeMargin, std::min(maxY, impl_->y));
    if (!done && nowMs >= impl_->stateStartMs && nowMs - impl_->stateStartMs >= impl_->stateDurationMs)
        done = true;
    if (done) impl_->beginRandomState(nowMs);
}

void MascotManager::render() const {
    if (!impl_ || !impl_->active) return;
    const LoadedAnimation* animation = impl_->currentAnimation();
    if (!animation || animation->frames.empty()) return;
    const size_t frame = impl_->frameIndex % animation->frames.size();
    vita2d_texture* texture = animation->frames[frame];
    if (!texture) return;

    const float tw = static_cast<float>(vita2d_texture_get_width(texture));
    const float th = static_cast<float>(vita2d_texture_get_height(texture));
    if (tw <= 0.0f || th <= 0.0f) return;
    const float scale = std::min(kLogicalW / tw, kLogicalH / th);
    const float drawW = tw * scale;
    const float drawH = th * scale;
    const float offsetX = (kLogicalW - drawW) * 0.5f;
    const float offsetY = (kLogicalH - drawH) * 0.5f;
    const bool mirror = impl_->nativeFacesRight != impl_->facingRight;

    if (!mirror) {
        vita2d_draw_texture_scale(texture, impl_->x + offsetX, impl_->y + offsetY, scale, scale);
    } else {
        // Negative X scale mirrors around the right edge of the centered draw rectangle.
        vita2d_draw_texture_scale(texture, impl_->x + offsetX + drawW, impl_->y + offsetY, -scale, scale);
    }
}

bool MascotManager::active() const {
    return impl_ && impl_->active;
}

const std::string& MascotManager::activeKey() const {
    static const std::string empty;
    return impl_ ? impl_->activeKey : empty;
}

} // namespace psvitaalive::ui
