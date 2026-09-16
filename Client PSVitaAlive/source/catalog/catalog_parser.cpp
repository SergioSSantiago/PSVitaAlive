#include "catalog/catalog_parser.hpp"

#include <psp2/json.h>
#include <psp2/sysmodule.h>
#include <psp2/kernel/clib.h>
#include <psp2/kernel/threadmgr.h>
#include <psp2/io/fcntl.h>

#include <cstdlib>
#include <cctype>
#include <string>

namespace psvitaalive {

namespace {

constexpr const char* IMAGE_MANIFEST_ROOT = "ux0:data/psvitaalive/cache/catalog";
constexpr const char* IMAGE_CATALOG_TAG = "psva_cat=";

class VitaJsonAllocator : public sce::Json::MemAllocator {
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

std::string getString(const sce::Json::Value& object, const char* key) {
    const sce::Json::Value& value = object[key];
    if (!value) return {};
    return value.getString().c_str();
}

uint64_t getUnsigned(const sce::Json::Value& object, const char* key) {
    const sce::Json::Value& value = object[key];
    if (!value) return 0;
    return value.getUInteger();
}

std::string formatSize(uint64_t bytes) {
    if (bytes == 0) return {};
    char buffer[64];
    if (bytes >= 1024ULL * 1024ULL * 1024ULL) {
        const double gb = static_cast<double>(bytes) / (1024.0 * 1024.0 * 1024.0);
        sceClibSnprintf(buffer, sizeof(buffer), "%.2f GB", gb);
        return buffer;
    }
    if (bytes >= 1024ULL * 1024ULL) {
        const double mb = static_cast<double>(bytes) / (1024.0 * 1024.0);
        sceClibSnprintf(buffer, sizeof(buffer), "%.1f MB", mb);
        return buffer;
    }
    if (bytes >= 1024ULL) {
        sceClibSnprintf(buffer, sizeof(buffer), "%llu KB", static_cast<unsigned long long>(bytes / 1024ULL));
        return buffer;
    }
    sceClibSnprintf(buffer, sizeof(buffer), "%llu B", static_cast<unsigned long long>(bytes));
    return buffer;
}

std::string firstArrayString(const sce::Json::Value& object, const char* key) {
    const sce::Json::Value& value = object[key];
    if (!value) return {};
    const sce::Json::Array& array = value.getArray();
    if (array.empty()) return {};
    return value[static_cast<SceSize>(0)].getString().c_str();
}

void parseStringArray(const sce::Json::Value& object, const char* key, std::vector<std::string>& out) {
    const sce::Json::Value& value = object[key];
    if (!value) return;
    const sce::Json::Array& array = value.getArray();
    for (SceSize i = 0; i < array.size(); ++i) {
        const sce::Json::Value& entry = value[i];
        if (entry) {
            const std::string text = entry.getString().c_str();
            if (!text.empty()) out.push_back(text);
        }
    }
}

const char* imageCatalogPrefixForPath(const std::string& path) {
    if (path.find("catalog_psvita_games.json") != std::string::npos) return "PV";
    if (path.find("catalog_psp_games.json") != std::string::npos) return "PSP";
    if (path.find("catalog_ps1_games.json") != std::string::npos) return "PS1";
    return "H";
}

bool isAuthoritativeCatalogPath(const std::string& path) {
    // CatalogManager validates network downloads as <catalog>.new first. Do not
    // publish a cleanup manifest from that speculative file: it becomes
    // authoritative only after the manager successfully promotes it.
    return path.find(".new") == std::string::npos &&
           path.find(".tmp") == std::string::npos;
}

std::string tagCatalogImageUrl(const std::string& url, const char* prefix) {
    if (url.empty() || !prefix || !*prefix) return url;
    if (url.find("#psva_cat=") != std::string::npos ||
        url.find("&psva_cat=") != std::string::npos) {
        return url;
    }
    std::string tagged = url;
    tagged += (url.find('#') == std::string::npos) ? '#' : '&';
    tagged += IMAGE_CATALOG_TAG;
    tagged += prefix;
    return tagged;
}

std::string imageManifestPath(const char* prefix) {
    return std::string(IMAGE_MANIFEST_ROOT) + "/images_" + prefix + ".manifest";
}

bool writeAll(SceUID fd, const char* data, size_t size) {
    if (fd < 0 || !data) return false;
    size_t written = 0;
    while (written < size) {
        const int result = sceIoWrite(fd, data + written, static_cast<SceSize>(size - written));
        if (result <= 0) return false;
        written += static_cast<size_t>(result);
    }
    return true;
}

bool writeManifestLine(SceUID fd, const char* imageNamespace, const std::string& url) {
    if (fd < 0 || !imageNamespace || url.empty()) return true;
    std::string line(imageNamespace);
    line.push_back(static_cast<char>(9));
    line += url;
    line.push_back(static_cast<char>(10));
    return writeAll(fd, line.data(), line.size());
}

std::string makeDownloadFileName(const std::string& url, const std::string& id) {
    if (url.empty()) return {};
    std::string clean = url;
    const std::size_t query = clean.find('?');
    if (query != std::string::npos) clean.erase(query);
    const std::size_t fragment = clean.find('#');
    if (fragment != std::string::npos) clean.erase(fragment);
    const std::size_t slash = clean.find_last_of('/');
    std::string fileName = slash != std::string::npos ? clean.substr(slash + 1) : clean;

    // VitaDB / similar redirectors expose get_hb_url.php — that is not a payload name.
    // Force a .vpk so FormatDetector and InstallDispatcher treat the file as homebrew.
    auto lower = [](std::string s) {
        for (char& c : s) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        return s;
    };
    const std::string low = lower(fileName);
    const bool badName =
        fileName.empty() ||
        low == "get_hb_url.php" ||
        low.find("get_hb_url") != std::string::npos ||
        (low.size() >= 4 && (low.rfind(".php") == low.size() - 4 ||
                             low.rfind(".asp") == low.size() - 4 ||
                             low.rfind(".aspx") == low.size() - 5 ||
                             low.rfind(".html") == low.size() - 5 ||
                             low.rfind(".htm") == low.size() - 4));
    if (badName) {
        const std::string base = id.empty() ? "download" : id;
        return base + ".vpk";
    }
    return fileName;
}

void parseLinks(const sce::Json::Value& application, ui::CatalogItem& item, SceUID zrifIdxFd, uint32_t* zrifWritten) {
    const sce::Json::Value& linksValue = application["links"];
    if (!linksValue) return;

    const sce::Json::Array& links = linksValue.getArray();
    std::string fallbackDownloadUrl;
    std::string fallbackDownloadName;

    for (SceSize i = 0; i < links.size(); ++i) {
        const sce::Json::Value& link = linksValue[i];
        const std::string type = getString(link, "type");
        const std::string name = getString(link, "name");
        const std::string url = getString(link, "url");
        if (url.empty()) continue;

        ui::CatalogLink detail;
        detail.type = type;
        detail.name = name;
        detail.url = url;
        // Keep zRIF off the heap: write to sidecar index, leave detail.zrif empty.
        {
            std::string z = getString(link, "zrif");
            if (z.empty()) z = getString(link, "zRIF");
            if (z.empty()) z = getString(link, "license");
            if (!z.empty() && zrifIdxFd >= 0) {
                sceIoWrite(zrifIdxFd, url.c_str(), static_cast<SceSize>(url.size()));
                const char tab = static_cast<char>(9);
                sceIoWrite(zrifIdxFd, &tab, 1);
                sceIoWrite(zrifIdxFd, z.c_str(), static_cast<SceSize>(z.size()));
                const char nl = static_cast<char>(10);
                sceIoWrite(zrifIdxFd, &nl, 1);
                if (zrifWritten) ++(*zrifWritten);
            }
        }
        detail.contentId = getString(link, "content_id");
        if (detail.contentId.empty()) detail.contentId = getString(link, "contentId");
        detail.recommended = link["recommended"].getBoolean();
        // Optional per-link size (numeric bytes preferred).
        if (link["size"]) {
            const uint64_t bytes = getUnsigned(link, "size");
            if (bytes > 0) detail.size = formatSize(bytes);
            else {
                const std::string raw = getString(link, "size");
                if (!raw.empty()) detail.size = raw;
            }
        }
        // Optional ZIP extract destination (skip path picker when set).
        {
            std::string ep = getString(link, "extract_path");
            if (ep.empty()) ep = getString(link, "extractPath");
            while (!ep.empty() && (ep.front() == ' ' || ep.front() == static_cast<char>(9))) ep.erase(ep.begin());
            while (!ep.empty() && (ep.back() == ' ' || ep.back() == static_cast<char>(9))) ep.pop_back();
            if (!ep.empty()) {
                if (ep.back() != '/' && ep.back() != ':') ep.push_back('/');
                detail.extractPath = ep;
            }
        }
        // Plugin link metadata (taiHEN config append).
        {
            detail.section = getString(link, "section");
            detail.line = getString(link, "line");
            while (!detail.section.empty() && (detail.section.front() == ' ' || detail.section.front() == static_cast<char>(9)))
                detail.section.erase(detail.section.begin());
            while (!detail.section.empty() && (detail.section.back() == ' ' || detail.section.back() == static_cast<char>(9)))
                detail.section.pop_back();
            while (!detail.line.empty() && (detail.line.front() == ' ' || detail.line.front() == static_cast<char>(9)))
                detail.line.erase(detail.line.begin());
            while (!detail.line.empty() && (detail.line.back() == ' ' || detail.line.back() == static_cast<char>(9)))
                detail.line.pop_back();
            // Default extract_path for plugins when omitted.
            const std::string typLower = type;
            // type is original case; compare loosely
            auto isPlugin = false;
            {
                std::string tl;
                for (char c : type) tl.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
                isPlugin = (tl == "plugin" || tl == "plugins");
            }
            if (isPlugin && detail.extractPath.empty()) {
                detail.extractPath = "ur0:tai/";
            }
        }
        item.linkDetails.push_back(detail);

        std::string display = type;
        if (!name.empty()) {
            if (!display.empty()) display += ": ";
            display += name;
        }
        if (!display.empty()) item.links.push_back(display);

        if (type == "Download" || type == "download" || type == "Downloads") {
            const std::string fileName = makeDownloadFileName(url, item.id);
            if (detail.recommended) {
                item.downloadUrl = url;
                item.downloadFileName = fileName;
            } else if (fallbackDownloadUrl.empty()) {
                fallbackDownloadUrl = url;
                fallbackDownloadName = fileName;
            }
        }
    }

    if (item.downloadUrl.empty() && !fallbackDownloadUrl.empty()) {
        item.downloadUrl = fallbackDownloadUrl;
        item.downloadFileName = fallbackDownloadName;
    }
}

} // namespace

bool CatalogParser::parseFile(const std::string& path, std::vector<ui::CatalogItem>& outItems) {
    outItems.clear();

    // Sidecar zRIF index next to the catalog JSON. Install looks up by URL so
    // we never keep thousands of license strings in RAM (Vita Games OOM).
    const std::string zrifIndexPath = path + ".zrifidx";
    sceIoRemove(zrifIndexPath.c_str());
    const SceUID zrifIdxFd = sceIoOpen(
        zrifIndexPath.c_str(), SCE_O_WRONLY | SCE_O_CREAT | SCE_O_TRUNC, 0777);
    uint32_t zrifWritten = 0;

    const int moduleResult = sceSysmoduleLoadModule(SCE_SYSMODULE_JSON);
    if (moduleResult < 0) {
        sceClibPrintf("[CatalogParser] Failed to load JSON module: 0x%08X\n", moduleResult);
        if (zrifIdxFd >= 0) sceIoClose(zrifIdxFd);
        return false;
    }

    VitaJsonAllocator allocator;
    sce::Json::InitParameter params;
    params.allocator = &allocator;
    params.userData = nullptr;
    params.bufSize = 64 * 1024;

    sce::Json::Initializer initializer;
    const int initResult = initializer.initialize(&params);
    if (initResult < 0) {
        sceClibPrintf("[CatalogParser] JSON initializer failed: 0x%08X\n", initResult);
        if (zrifIdxFd >= 0) sceIoClose(zrifIdxFd);
        return false;
    }

    sce::Json::Value root;
    const int parseResult = sce::Json::Parser::parse(root, path.c_str());
    if (parseResult < 0) {
        sceClibPrintf("[CatalogParser] JSON parse failed: 0x%08X\n", parseResult);
        initializer.terminate();
        if (zrifIdxFd >= 0) sceIoClose(zrifIdxFd);
        return false;
    }

    const char* imagePrefix = imageCatalogPrefixForPath(path);
    const bool publishManifest = isAuthoritativeCatalogPath(path);
    const std::string manifestPath = imageManifestPath(imagePrefix);
    const std::string manifestTemp = manifestPath + ".new";
    SceUID manifestFd = -1;
    bool manifestOk = false;
    if (publishManifest) {
        sceIoRemove(manifestTemp.c_str());
        manifestFd = sceIoOpen(
            manifestTemp.c_str(), SCE_O_WRONLY | SCE_O_CREAT | SCE_O_TRUNC, 0666);
        manifestOk = manifestFd >= 0;
        if (manifestOk) {
            char header[80];
            const int len = sceClibSnprintf(
                header, sizeof(header), "PSVAIMG1 %llu",
                static_cast<unsigned long long>(sceKernelGetSystemTimeWide()));
            manifestOk = len > 0 && writeAll(manifestFd, header, static_cast<size_t>(len));
            const char nl = static_cast<char>(10);
            if (manifestOk) manifestOk = writeAll(manifestFd, &nl, 1);
        }
    }

    const sce::Json::Array& applications = root.getArray();
    for (SceSize i = 0; i < applications.size(); ++i) {
        const sce::Json::Value& app = root[i];
        ui::CatalogItem item;

        item.id = getString(app, "id");
        item.titleId = getString(app, "title_id");
        item.name = getString(app, "name");
        item.description = getString(app, "description");
        // long_description skipped — was a major RAM cost on Vita Games catalog.
        if (item.description.size() > 480) item.description.resize(480);
        item.longDescription.clear();
        item.version = getString(app, "version");
        item.versionDate = getString(app, "version_date");
        if (item.versionDate.empty()) item.versionDate = getString(app, "date");
        item.requirements = getString(app, "requirements");
        item.status = getString(app, "status");
        item.category = getString(app, "category_id");
        if (item.category.empty()) item.category = getString(app, "category");
        item.subcategory = firstArrayString(app, "subcategory_ids");
        item.changelog.clear(); // skipped for RAM (detail can show description only)
        item.size = formatSize(getUnsigned(app, "size"));
        item.icon = getString(app, "icon");
        item.cover = getString(app, "cover");
        parseStringArray(app, "screenshots", item.screenshots);
        if (item.screenshots.size() > 4) item.screenshots.resize(4);
        item.author = firstArrayString(app, "author_ids");
        if (item.author.empty()) item.author = getString(app, "author");

        parseLinks(app, item, zrifIdxFd, &zrifWritten);

        // Official game catalogs may use cover instead of icon and may not have
        // a Homebrew-style status. Keep the UI stable with a neutral badge.
        if (item.icon.empty()) item.icon = item.cover;
        if (item.status.empty()) item.status = "Available";

        if (item.id.empty() || item.name.empty()) {
            sceClibPrintf("[CatalogParser] Skipping invalid application at index %u\n", static_cast<unsigned>(i));
            continue;
        }

        // Internal-only catalog tag. It never reaches libcurl: ImageCache strips
        // it before network I/O, but uses it to produce H/PV/PSP/PS1 filenames.
        item.icon = tagCatalogImageUrl(item.icon, imagePrefix);
        item.cover = tagCatalogImageUrl(item.cover, imagePrefix);
        for (std::string& screenshot : item.screenshots) {
            screenshot = tagCatalogImageUrl(screenshot, imagePrefix);
        }

        if (manifestOk) {
            manifestOk = writeManifestLine(manifestFd, "app", item.icon) && manifestOk;
            manifestOk = writeManifestLine(manifestFd, "app", item.cover) && manifestOk;
            for (const std::string& screenshot : item.screenshots) {
                manifestOk = writeManifestLine(manifestFd, "shot", screenshot) && manifestOk;
            }
        }

        outItems.push_back(std::move(item));
    }

    initializer.terminate();
    if (zrifIdxFd >= 0) sceIoClose(zrifIdxFd);
    if (manifestFd >= 0) sceIoClose(manifestFd);

    if (publishManifest) {
        if (!outItems.empty() && manifestOk) {
            sceIoRemove(manifestPath.c_str());
            if (sceIoRename(manifestTemp.c_str(), manifestPath.c_str()) < 0) {
                sceIoRemove(manifestTemp.c_str());
            }
        } else {
            sceIoRemove(manifestTemp.c_str());
        }
    }

    sceClibPrintf("[CatalogParser] Loaded %u applications (zrif index entries=%u)\n",
                  static_cast<unsigned>(outItems.size()),
                  static_cast<unsigned>(zrifWritten));
    return !outItems.empty();
}

} // namespace psvitaalive
