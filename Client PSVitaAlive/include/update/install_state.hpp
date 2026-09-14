#pragma once

#include <string>

namespace psvitaalive {
namespace update {

/** Local install identity for catalog Homebrew (not official game catalogs). */
enum class InstallDetectState {
    Unknown = 0,
    NotInstalled,
    Installed,
    UpdateAvailable,
    /** App is present but we cannot prove which release it is (nightly/fork/unknown). */
    InstalledUnknown
};

struct InstallDetectResult {
    InstallDetectState state = InstallDetectState::Unknown;
    std::string installedVersion; // human-facing hint when known
    std::string source;           // receipt | fingerprint | sfo | none
};

} // namespace update
} // namespace psvitaalive
