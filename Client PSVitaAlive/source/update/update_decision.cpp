#include "update/update_decision.hpp"

#include <cctype>
#include <sstream>
#include <vector>

namespace psvitaalive {
namespace update {
namespace {

std::string toLower(std::string s) {
    for (char& c : s) {
        if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
    }
    return s;
}

std::vector<int> parseVersionParts(const std::string& in) {
    std::vector<int> parts;
    int cur = 0;
    bool inNum = false;
    for (unsigned char ch : in) {
        if (std::isdigit(ch)) {
            cur = cur * 10 + (ch - '0');
            inNum = true;
        } else if (inNum) {
            parts.push_back(cur);
            cur = 0;
            inNum = false;
        }
    }
    if (inNum) parts.push_back(cur);
    while (!parts.empty() && parts.back() == 0) parts.pop_back();
    if (parts.empty()) parts.push_back(0);
    return parts;
}

std::string trimAscii(std::string s) {
    size_t first = 0;
    while (first < s.size() && std::isspace(static_cast<unsigned char>(s[first]))) ++first;
    size_t last = s.size();
    while (last > first && std::isspace(static_cast<unsigned char>(s[last - 1]))) --last;
    return s.substr(first, last - first);
}

bool parseUnsignedStrict(const std::string& s, int& out) {
    if (s.empty()) return false;
    int value = 0;
    for (unsigned char c : s) {
        if (!std::isdigit(c)) return false;
        value = value * 10 + (c - '0');
        if (value > 9999) return false;
    }
    out = value;
    return true;
}

// Some Vita projects must squeeze semantic X.Y.Z into SFO APP_VER's XX.YY
// field and encode it as XX.YZ. Example: 1.7.1 -> 01.71.
bool parseSemanticTripleForVita(const std::string& input, int& major, int& minor, int& patch) {
    std::string s = trimAscii(input);
    if (!s.empty() && (s.front() == 'v' || s.front() == 'V')) s.erase(s.begin());

    const size_t p1 = s.find('.');
    if (p1 == std::string::npos) return false;
    const size_t p2 = s.find('.', p1 + 1);
    if (p2 == std::string::npos || s.find('.', p2 + 1) != std::string::npos) return false;

    if (!parseUnsignedStrict(s.substr(0, p1), major) ||
        !parseUnsignedStrict(s.substr(p1 + 1, p2 - p1 - 1), minor) ||
        !parseUnsignedStrict(s.substr(p2 + 1), patch)) {
        return false;
    }

    // XX.YZ only has one decimal digit available for Y and one for Z.
    return major >= 0 && major <= 99 && minor >= 0 && minor <= 9 && patch >= 0 && patch <= 9;
}

bool parseVitaAppVer(const std::string& input, int& major, int& minorPatch) {
    const std::string s = trimAscii(input);
    const size_t dot = s.find('.');
    if (dot == std::string::npos || s.find('.', dot + 1) != std::string::npos) return false;

    const std::string majorPart = s.substr(0, dot);
    const std::string fractionalPart = s.substr(dot + 1);
    if (majorPart.empty() || majorPart.size() > 2 || fractionalPart.size() != 2) return false;
    if (!parseUnsignedStrict(majorPart, major) || !parseUnsignedStrict(fractionalPart, minorPatch)) return false;
    return major >= 0 && major <= 99 && minorPatch >= 0 && minorPatch <= 99;
}

} // namespace

int compareNormalizedVersions(const std::string& a, const std::string& b) {
    const auto pa = parseVersionParts(a);
    const auto pb = parseVersionParts(b);
    const size_t n = pa.size() > pb.size() ? pa.size() : pb.size();
    for (size_t i = 0; i < n; ++i) {
        const int x = i < pa.size() ? pa[i] : 0;
        const int y = i < pb.size() ? pb[i] : 0;
        if (x < y) return -1;
        if (x > y) return 1;
    }
    return 0;
}

namespace {

int compareSfoToCatalogVersion(const std::string& sfoVersion, const std::string& catalogVersion) {
    int catalogMajor = 0;
    int catalogMinor = 0;
    int catalogPatch = 0;
    int sfoMajor = 0;
    int sfoMinorPatch = 0;

    if (parseSemanticTripleForVita(catalogVersion, catalogMajor, catalogMinor, catalogPatch) &&
        parseVitaAppVer(sfoVersion, sfoMajor, sfoMinorPatch)) {
        const int catalogMinorPatch = catalogMinor * 10 + catalogPatch;
        if (sfoMajor < catalogMajor) return -1;
        if (sfoMajor > catalogMajor) return 1;
        if (sfoMinorPatch < catalogMinorPatch) return -1;
        if (sfoMinorPatch > catalogMinorPatch) return 1;
        return 0;
    }

    return compareNormalizedVersions(sfoVersion, catalogVersion);
}

} // namespace

bool isUnreliableSfoVersion(const std::string& appVer) {
    std::string s = toLower(appVer);
    while (!s.empty() && (s.front() == ' ' || s.front() == '\t')) s.erase(s.begin());
    while (!s.empty() && (s.back() == ' ' || s.back() == '\t')) s.pop_back();
    if (s.empty()) return true;
    if (s == "00.00" || s == "0.00" || s == "0" || s == "00" || s == "0.0" || s == "00.0")
        return true;
    bool allZero = true;
    bool anyDigit = false;
    for (unsigned char c : s) {
        if (std::isdigit(c)) {
            anyDigit = true;
            if (c != '0') allZero = false;
        }
    }
    return anyDigit && allZero;
}

SfoPolicy parseSfoPolicy(const std::string& s) {
    const std::string l = toLower(s);
    if (l == "trusted") return SfoPolicy::Trusted;
    if (l == "ignore") return SfoPolicy::Ignore;
    return SfoPolicy::Fallback;
}

InstallDetectResult decideInstallState(
    bool titleInstalled,
    const std::string& catalogVersion,
    const UpdateDetectionMeta& meta,
    const ReceiptEvidence& receipt,
    const FingerprintEvidence& fingerprint,
    const SfoEvidence& sfo) {

    InstallDetectResult out;
    if (!titleInstalled) {
        out.state = InstallDetectState::NotInstalled;
        out.source = "none";
        return out;
    }

    const SfoPolicy policy = meta.present ? meta.sfoPolicy : SfoPolicy::Fallback;

    if (receipt.present && receipt.fingerprintMatchesInstalled) {
        out.source = "receipt";
        out.installedVersion = receipt.catalogVersion;
        if (!catalogVersion.empty() && !receipt.catalogVersion.empty()) {
            const int cmp = compareNormalizedVersions(receipt.catalogVersion, catalogVersion);
            if (cmp == 0) {
                out.state = InstallDetectState::Installed;
                return out;
            }
            if (cmp < 0) {
                out.state = InstallDetectState::UpdateAvailable;
                return out;
            }
            out.state = InstallDetectState::InstalledUnknown;
            return out;
        }
        if (meta.present && meta.revision > 0 && receipt.releaseRevision > 0) {
            if (receipt.releaseRevision == meta.revision) {
                out.state = InstallDetectState::Installed;
                return out;
            }
            if (receipt.releaseRevision < meta.revision) {
                out.state = InstallDetectState::UpdateAvailable;
                return out;
            }
            out.state = InstallDetectState::InstalledUnknown;
            return out;
        }
        out.state = InstallDetectState::Installed;
        return out;
    }

    // Phase-1 compatibility for PSVitaAlive-managed installs.
    // Current receipts are written with the catalog version but without a live
    // fingerprint digest. queryLocalInstall therefore cannot mark them as a
    // fingerprint match once the catalog version changes. While the catalog has
    // no update_detection metadata (meta.present == false), the receipt is still
    // positive evidence of the last version installed by PSVitaAlive.
    //
    // Once catalog fingerprints are available (meta.present == true), this
    // compatibility path is disabled and the strict verified-receipt/fingerprint
    // rules above/below take over again.
    if (receipt.present && !receipt.fingerprintMatchesInstalled &&
        !meta.present && !receipt.catalogVersion.empty() && !catalogVersion.empty()) {

        // If APP_VER is actually reliable and already says current/newer, prefer
        // that evidence over a potentially stale receipt. Never offer a downgrade.
        // APP_VER may use Vita's XX.YY encoding for semantic X.Y.Z (01.71 = 1.7.1).
        if (sfo.hasAppVer && !sfo.appVer.empty() && !isUnreliableSfoVersion(sfo.appVer)) {
            const int sfoCmp = compareSfoToCatalogVersion(sfo.appVer, catalogVersion);
            if (sfoCmp == 0) {
                out.state = InstallDetectState::Installed;
                out.source = "sfo";
                out.installedVersion = sfo.appVer;
                return out;
            }
            if (sfoCmp > 0) {
                out.state = InstallDetectState::InstalledUnknown;
                out.source = "sfo";
                out.installedVersion = sfo.appVer;
                return out;
            }
        }

        out.source = "receipt";
        out.installedVersion = receipt.catalogVersion;
        const int cmp = compareNormalizedVersions(receipt.catalogVersion, catalogVersion);
        if (cmp < 0) {
            out.state = InstallDetectState::UpdateAvailable;
            return out;
        }
        if (cmp == 0) {
            out.state = InstallDetectState::Installed;
            return out;
        }

        // Receipt newer than catalog: do not offer an older package.
        out.state = InstallDetectState::InstalledUnknown;
        return out;
    }

    if (fingerprint.matchedCurrent) {
        out.state = InstallDetectState::Installed;
        out.source = "fingerprint";
        out.installedVersion = catalogVersion;
        return out;
    }
    if (fingerprint.matchedHistory) {
        out.state = InstallDetectState::UpdateAvailable;
        out.source = "fingerprint";
        out.installedVersion = fingerprint.historyVersion;
        return out;
    }

    if (policy != SfoPolicy::Ignore && sfo.hasAppVer && !sfo.appVer.empty()) {
        out.source = "sfo";
        out.installedVersion = sfo.appVer;

        if (!catalogVersion.empty() && compareSfoToCatalogVersion(sfo.appVer, catalogVersion) == 0) {
            out.state = InstallDetectState::Installed;
            return out;
        }

        if (policy == SfoPolicy::Trusted && !catalogVersion.empty() &&
            !isUnreliableSfoVersion(sfo.appVer)) {
            if (compareSfoToCatalogVersion(sfo.appVer, catalogVersion) < 0) {
                out.state = InstallDetectState::UpdateAvailable;
                return out;
            }
            out.state = InstallDetectState::InstalledUnknown;
            return out;
        }

        out.state = InstallDetectState::InstalledUnknown;
        return out;
    }

    out.state = InstallDetectState::InstalledUnknown;
    out.source = "none";
    if (sfo.hasAppVer) out.installedVersion = sfo.appVer;
    return out;
}

} // namespace update
} // namespace psvitaalive
