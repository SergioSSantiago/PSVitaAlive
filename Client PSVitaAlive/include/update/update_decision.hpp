#pragma once

#include "update/install_state.hpp"

#include <string>
#include <vector>

namespace psvitaalive {
namespace update {

enum class SfoPolicy {
    Fallback = 0, // default: match can confirm current; mismatch alone is NOT UpdateAvailable
    Trusted,      // maintainer guarantees APP_VER tracks releases
    Ignore        // never use APP_VER
};

struct FileSignature {
    std::string path; // relative to ux0:app/TITLEID/
    std::string algorithm; // "md5" | "sha256"
    std::string digest;    // lowercase hex preferred
    std::vector<std::string> candidatePaths; // optional historical
    std::string role; // optional: auxiliary
};

struct KnownRelease {
    int revision = 0;
    std::string version;
    std::string versionDate;
    std::vector<FileSignature> signatures;
};

struct UpdateDetectionMeta {
    bool present = false;
    int revision = 0;
    SfoPolicy sfoPolicy = SfoPolicy::Fallback;
    std::vector<FileSignature> signatures; // current release
    std::vector<KnownRelease> knownReleases;
};

struct ReceiptEvidence {
    bool present = false;
    bool fingerprintMatchesInstalled = false;
    std::string catalogVersion;
    std::string versionDate;
    int releaseRevision = 0;
};

struct FingerprintEvidence {
    bool matchedCurrent = false;
    bool matchedHistory = false;
    int historyRevision = 0;
    std::string historyVersion;
};

struct SfoEvidence {
    bool hasAppVer = false;
    std::string appVer;
};

/**
 * Pure decision matrix (no I/O). Host-testable.
 *
 * Absolute rules:
 * - hash mismatch  != UpdateAvailable
 * - SFO mismatch   != UpdateAvailable (unless sfo_policy == trusted)
 * - UpdateAvailable requires positive evidence of an older known release
 */
InstallDetectResult decideInstallState(
    bool titleInstalled,
    const std::string& catalogVersion,
    const UpdateDetectionMeta& meta,
    const ReceiptEvidence& receipt,
    const FingerprintEvidence& fingerprint,
    const SfoEvidence& sfo);

/** Normalize version tokens for trusted SFO compare (returns -1,0,1). */
int compareNormalizedVersions(const std::string& a, const std::string& b);

/** True when APP_VER is a common placeholder that must not drive UpdateAvailable under fallback. */
bool isUnreliableSfoVersion(const std::string& appVer);

SfoPolicy parseSfoPolicy(const std::string& s);

} // namespace update
} // namespace psvitaalive
