// Host-side unit tests for pure update decision matrix.
// Build: g++ -std=c++17 -I../include test_update_decision.cpp ../source/update/update_decision.cpp -o test_update_decision && ./test_update_decision

#include "update/update_decision.hpp"

#include <cstdio>
#include <cstdlib>
#include <string>

using namespace psvitaalive::update;

static int g_fails = 0;

static void expect(bool cond, const char* name) {
    if (!cond) {
        std::printf("FAIL: %s\n", name);
        ++g_fails;
    } else {
        std::printf("OK:   %s\n", name);
    }
}

static void expectState(InstallDetectState got, InstallDetectState want, const char* name) {
    if (got != want) {
        std::printf("FAIL: %s (got=%d want=%d)\n", name, (int)got, (int)want);
        ++g_fails;
    } else {
        std::printf("OK:   %s\n", name);
    }
}

int main() {
    UpdateDetectionMeta emptyMeta{};
    UpdateDetectionMeta fallbackMeta{};
    fallbackMeta.present = true;
    fallbackMeta.sfoPolicy = SfoPolicy::Fallback;
    fallbackMeta.revision = 4;

    UpdateDetectionMeta trustedMeta = fallbackMeta;
    trustedMeta.sfoPolicy = SfoPolicy::Trusted;

    ReceiptEvidence noReceipt{};
    FingerprintEvidence noFp{};
    SfoEvidence sfo0000{};
    sfo0000.hasAppVer = true;
    sfo0000.appVer = "00.00";

    // K: not installed
    {
        auto r = decideInstallState(false, "2.4", emptyMeta, noReceipt, noFp, sfo0000);
        expectState(r.state, InstallDetectState::NotInstalled, "K NotInstalled");
    }

    // A: SFO=00.00, fingerprint current, no receipt -> Installed
    {
        FingerprintEvidence fp{};
        fp.matchedCurrent = true;
        auto r = decideInstallState(true, "2.4", fallbackMeta, noReceipt, fp, sfo0000);
        expectState(r.state, InstallDetectState::Installed, "A fingerprint current");
    }

    // B: receipt current + fingerprint matches
    {
        ReceiptEvidence rec{};
        rec.present = true;
        rec.fingerprintMatchesInstalled = true;
        rec.catalogVersion = "2.4";
        rec.releaseRevision = 4;
        auto r = decideInstallState(true, "2.4", fallbackMeta, rec, noFp, sfo0000);
        expectState(r.state, InstallDetectState::Installed, "B receipt current");
    }

    // C: receipt older
    {
        ReceiptEvidence rec{};
        rec.present = true;
        rec.fingerprintMatchesInstalled = true;
        rec.catalogVersion = "2.3";
        rec.releaseRevision = 3;
        auto r = decideInstallState(true, "2.4", fallbackMeta, rec, noFp, sfo0000);
        expectState(r.state, InstallDetectState::UpdateAvailable, "C receipt older");
    }

    // C2: phase-1 PSVitaAlive receipt without fingerprint detects a newer catalog release.
    // This mirrors Golden Balloon installed as 1.7.1 and catalog updated to 1.7.2.
    {
        ReceiptEvidence rec{};
        rec.present = true;
        rec.fingerprintMatchesInstalled = false;
        rec.catalogVersion = "1.7.1";
        auto r = decideInstallState(true, "1.7.2", emptyMeta, rec, noFp, sfo0000);
        expectState(r.state, InstallDetectState::UpdateAvailable, "C2 phase1 receipt 1.7.1 -> 1.7.2");
        expect(r.source == "receipt", "C2 source receipt");
        expect(r.installedVersion == "1.7.1", "C2 installed version preserved");
    }

    // C3: phase-1 receipt equal to catalog remains Installed.
    {
        ReceiptEvidence rec{};
        rec.present = true;
        rec.catalogVersion = "1.7.2";
        auto r = decideInstallState(true, "1.7.2", emptyMeta, rec, noFp, sfo0000);
        expectState(r.state, InstallDetectState::Installed, "C3 phase1 receipt current");
    }

    // C4: phase-1 receipt newer than catalog must never offer a downgrade.
    {
        ReceiptEvidence rec{};
        rec.present = true;
        rec.catalogVersion = "1.7.3";
        auto r = decideInstallState(true, "1.7.2", emptyMeta, rec, noFp, sfo0000);
        expectState(r.state, InstallDetectState::InstalledUnknown, "C4 phase1 no downgrade");
    }

    // C5: reliable SFO saying current wins over an older/stale phase-1 receipt.
    {
        ReceiptEvidence rec{};
        rec.present = true;
        rec.catalogVersion = "1.7.1";
        SfoEvidence sfo{};
        sfo.hasAppVer = true;
        sfo.appVer = "1.7.2";
        auto r = decideInstallState(true, "1.7.2", emptyMeta, rec, noFp, sfo);
        expectState(r.state, InstallDetectState::Installed, "C5 current SFO beats stale receipt");
    }

    // C6: reliable SFO newer than catalog blocks a downgrade even if receipt is older.
    {
        ReceiptEvidence rec{};
        rec.present = true;
        rec.catalogVersion = "1.7.1";
        SfoEvidence sfo{};
        sfo.hasAppVer = true;
        sfo.appVer = "1.7.3";
        auto r = decideInstallState(true, "1.7.2", emptyMeta, rec, noFp, sfo);
        expectState(r.state, InstallDetectState::InstalledUnknown, "C6 newer SFO blocks downgrade");
    }

    // D: history fingerprint
    {
        FingerprintEvidence fp{};
        fp.matchedHistory = true;
        fp.historyRevision = 3;
        fp.historyVersion = "2.3";
        auto r = decideInstallState(true, "2.4", fallbackMeta, noReceipt, fp, sfo0000);
        expectState(r.state, InstallDetectState::UpdateAvailable, "D history fingerprint");
    }

    // E / F: unknown fingerprint + SFO mismatch -> InstalledUnknown
    {
        auto r = decideInstallState(true, "2.4", fallbackMeta, noReceipt, noFp, sfo0000);
        expectState(r.state, InstallDetectState::InstalledUnknown, "E/F unknown fingerprint");
    }

    // G: once update_detection metadata exists, an unverified receipt stays invalid.
    {
        ReceiptEvidence rec{};
        rec.present = true;
        rec.fingerprintMatchesInstalled = false;
        rec.catalogVersion = "2.3";
        auto r = decideInstallState(true, "2.4", fallbackMeta, rec, noFp, sfo0000);
        expectState(r.state, InstallDetectState::InstalledUnknown, "G invalidated receipt");
    }

    // H: SFO matches catalog under fallback -> Installed
    {
        SfoEvidence sfo{};
        sfo.hasAppVer = true;
        sfo.appVer = "2.4";
        auto r = decideInstallState(true, "2.4", fallbackMeta, noReceipt, noFp, sfo);
        expectState(r.state, InstallDetectState::Installed, "H SFO match fallback");
    }

    // I: SFO lower, fallback, no other evidence -> InstalledUnknown
    {
        SfoEvidence sfo{};
        sfo.hasAppVer = true;
        sfo.appVer = "1.0";
        auto r = decideInstallState(true, "2.4", fallbackMeta, noReceipt, noFp, sfo);
        expectState(r.state, InstallDetectState::InstalledUnknown, "I SFO lower fallback");
    }

    // J: SFO lower + trusted -> UpdateAvailable
    {
        SfoEvidence sfo{};
        sfo.hasAppVer = true;
        sfo.appVer = "1.0";
        auto r = decideInstallState(true, "2.4", trustedMeta, noReceipt, noFp, sfo);
        expectState(r.state, InstallDetectState::UpdateAvailable, "J SFO lower trusted");
    }

    // Receipt claims newer than catalog -> InstalledUnknown (no downgrade)
    {
        ReceiptEvidence rec{};
        rec.present = true;
        rec.fingerprintMatchesInstalled = true;
        rec.catalogVersion = "3.0";
        auto r = decideInstallState(true, "2.4", fallbackMeta, rec, noFp, sfo0000);
        expectState(r.state, InstallDetectState::InstalledUnknown, "no downgrade via receipt");
    }

    expect(isUnreliableSfoVersion("00.00"), "unreliable 00.00");
    expect(isUnreliableSfoVersion(""), "unreliable empty");
    expect(!isUnreliableSfoVersion("1.2.3"), "reliable 1.2.3");
    expect(compareNormalizedVersions("2.4", "2.4.0") == 0, "version normalize equal");
    expect(compareNormalizedVersions("2.3", "2.4") < 0, "version 2.3 < 2.4");
    expect(compareNormalizedVersions("1.7.1", "1.7.2") < 0, "version 1.7.1 < 1.7.2");

    if (g_fails) {
        std::printf("\n%d failure(s)\n", g_fails);
        return 1;
    }
    std::printf("\nAll tests passed.\n");
    return 0;
}
