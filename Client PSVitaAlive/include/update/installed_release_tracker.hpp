#pragma once

#include <cstdint>
#include <string>

namespace psvitaalive {
namespace update {

struct InstallReceipt {
    int schemaVersion = 1;
    std::string appId;
    std::string titleId;
    std::string catalogVersion;
    std::string versionDate;
    int releaseRevision = 0;
    std::string verifyPath;
    std::string verifyAlgorithm;
    std::string verifyDigest;
};

class InstalledReleaseTracker {
public:
    static std::string dataRoot();
    static std::string receiptPath(const std::string& titleId);
    static bool writeReceipt(const InstallReceipt& r);
    static bool readReceipt(const std::string& titleId, InstallReceipt& out);
    static void removeReceipt(const std::string& titleId);
    static bool ensureDir();
};

} // namespace update
} // namespace psvitaalive
