// Host-side unit tests for pure update decision matrix.
// g++ -std=c++17 -IClient\ PSVitaAlive/include tests/test_update_decision.cpp Client\ PSVitaAlive/source/update/update_decision.cpp -o test_ud && ./test_ud

#include "update/update_decision.hpp"
#include <cstdio>
using namespace psvitaalive::update;
static int g_fails = 0;
static void expectState(InstallDetectState got, InstallDetectState want, const char* name) {
    if (got != want) { std::printf("FAIL: %s (got=%d want=%d)\n", name, (int)got, (int)want); ++g_fails; }
    else std::printf("OK:   %s\n", name);
}
static void expect(bool c, const char* n) { if (!c) { std::printf("FAIL: %s\n", n); ++g_fails; } else std::printf("OK:   %s\n", n); }
int main() {
    UpdateDetectionMeta emptyMeta{};
    UpdateDetectionMeta fallbackMeta{}; fallbackMeta.present = true; fallbackMeta.sfoPolicy = SfoPolicy::Fallback; fallbackMeta.revision = 4;
    UpdateDetectionMeta trustedMeta = fallbackMeta; trustedMeta.sfoPolicy = SfoPolicy::Trusted;
    ReceiptEvidence noReceipt{}; FingerprintEvidence noFp{};
    SfoEvidence sfo0000{}; sfo0000.hasAppVer = true; sfo0000.appVer = "00.00";
    expectState(decideInstallState(false, "2.4", emptyMeta, noReceipt, noFp, sfo0000).state, InstallDetectState::NotInstalled, "K NotInstalled");
    { FingerprintEvidence fp{}; fp.matchedCurrent = true;
      expectState(decideInstallState(true, "2.4", fallbackMeta, noReceipt, fp, sfo0000).state, InstallDetectState::Installed, "A fingerprint current"); }
    { ReceiptEvidence rec{}; rec.present = true; rec.fingerprintMatchesInstalled = true; rec.catalogVersion = "2.4"; rec.releaseRevision = 4;
      expectState(decideInstallState(true, "2.4", fallbackMeta, rec, noFp, sfo0000).state, InstallDetectState::Installed, "B receipt current"); }
    { ReceiptEvidence rec{}; rec.present = true; rec.fingerprintMatchesInstalled = true; rec.catalogVersion = "2.3"; rec.releaseRevision = 3;
      expectState(decideInstallState(true, "2.4", fallbackMeta, rec, noFp, sfo0000).state, InstallDetectState::UpdateAvailable, "C receipt older"); }
    { FingerprintEvidence fp{}; fp.matchedHistory = true; fp.historyRevision = 3; fp.historyVersion = "2.3";
      expectState(decideInstallState(true, "2.4", fallbackMeta, noReceipt, fp, sfo0000).state, InstallDetectState::UpdateAvailable, "D history fingerprint"); }
    expectState(decideInstallState(true, "2.4", fallbackMeta, noReceipt, noFp, sfo0000).state, InstallDetectState::InstalledUnknown, "E/F unknown fingerprint");
    { ReceiptEvidence rec{}; rec.present = true; rec.fingerprintMatchesInstalled = false; rec.catalogVersion = "2.3";
      expectState(decideInstallState(true, "2.4", fallbackMeta, rec, noFp, sfo0000).state, InstallDetectState::InstalledUnknown, "G invalidated receipt"); }
    { SfoEvidence sfo{}; sfo.hasAppVer = true; sfo.appVer = "2.4";
      expectState(decideInstallState(true, "2.4", fallbackMeta, noReceipt, noFp, sfo).state, InstallDetectState::Installed, "H SFO match fallback"); }
    { SfoEvidence sfo{}; sfo.hasAppVer = true; sfo.appVer = "1.0";
      expectState(decideInstallState(true, "2.4", fallbackMeta, noReceipt, noFp, sfo).state, InstallDetectState::InstalledUnknown, "I SFO lower fallback"); }
    { SfoEvidence sfo{}; sfo.hasAppVer = true; sfo.appVer = "1.0";
      expectState(decideInstallState(true, "2.4", trustedMeta, noReceipt, noFp, sfo).state, InstallDetectState::UpdateAvailable, "J SFO lower trusted"); }
    { ReceiptEvidence rec{}; rec.present = true; rec.fingerprintMatchesInstalled = true; rec.catalogVersion = "3.0";
      expectState(decideInstallState(true, "2.4", fallbackMeta, rec, noFp, sfo0000).state, InstallDetectState::InstalledUnknown, "no downgrade via receipt"); }
    expect(isUnreliableSfoVersion("00.00"), "unreliable 00.00");
    expect(compareNormalizedVersions("2.3", "2.4") < 0, "version 2.3 < 2.4");
    if (g_fails) { std::printf("%d failures\n", g_fails); return 1; }
    std::printf("All tests passed.\n"); return 0;
}
