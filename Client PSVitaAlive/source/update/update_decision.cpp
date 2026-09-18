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

bool versionsEqualLoose(const std::string& a, const std::string& b) {
    return compareNormalizedVersions(a, b) == 0;
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
        if (sfo.hasAppVer && !sfo.appVer.empty() && !isUnreliableSfoVersion(sfo.appVer)) {
            const int sfoCmp = compareNormalizedVersions(sfo.appVer, catalogVersion);
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

        if (!catalogVersion.empty() && versionsEqualLoose(sfo.appVer, catalogVersion)) {
            out.state = InstallDetectState::Installed;
            return out;
        }

        if (policy == SfoPolicy::Trusted && !catalogVersion.empty() &&
            !isUnreliableSfoVersion(sfo.appVer)) {
            if (compareNormalizedVersions(sfo.appVer, catalogVersion) < 0) {
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
