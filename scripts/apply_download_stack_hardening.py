#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTTP = ROOT / "Client PSVitaAlive/source/network/http_client.cpp"
DM = ROOT / "Client PSVitaAlive/source/network/download_manager.cpp"
ZIP = ROOT / "Client PSVitaAlive/source/archive/zip_extractor.cpp"
DOC = ROOT / "docs/NETWORK_TLS.md"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 match, got {count}")
    return text.replace(old, new, 1)


def replace_between(text: str, start: str, end: str, new_block: str, label: str) -> str:
    a = text.find(start)
    if a < 0:
        raise SystemExit(f"{label}: start marker not found")
    b = text.find(end, a)
    if b < 0:
        raise SystemExit(f"{label}: end marker not found")
    return text[:a] + new_block + text[b:]


def patch_http() -> None:
    text = HTTP.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "    int retryAfterSeconds = 0; // from Retry-After header (429/503)\n    std::string etag;\n",
        "    int retryAfterSeconds = 0; // from Retry-After header (429/503)\n    long responseCode = 0; // current HTTP response, reset on each status line\n    bool discardedErrorBody = false;\n    std::string etag;\n",
        "http context response state",
    )

    helper_start = "static const char* findHeaderIgnoreCase(const char* buffer, const char* header) {"
    helper_end = "static void updateSpeed(TransferContext* ctx) {"
    helpers = r'''static bool startsWithAsciiNoCase(const char* buffer, size_t bytes, const char* prefix) {
    if (!buffer || !prefix) return false;
    const size_t n = std::strlen(prefix);
    if (bytes < n) return false;
    for (size_t i = 0; i < n; ++i) {
        char a = buffer[i];
        char b = prefix[i];
        if (a >= 'A' && a <= 'Z') a = static_cast<char>(a - 'A' + 'a');
        if (b >= 'A' && b <= 'Z') b = static_cast<char>(b - 'A' + 'a');
        if (a != b) return false;
    }
    return true;
}

static std::string headerValue(const char* buffer, size_t bytes, const char* header) {
    if (!buffer || !header || !startsWithAsciiNoCase(buffer, bytes, header)) return {};
    size_t p = std::strlen(header);
    while (p < bytes && (buffer[p] == ' ' || buffer[p] == '\t')) ++p;
    size_t end = bytes;
    while (end > p && (buffer[end - 1] == '\r' || buffer[end - 1] == '\n' ||
                       buffer[end - 1] == ' ' || buffer[end - 1] == '\t')) --end;
    return std::string(buffer + p, end - p);
}

static bool parseHttpStatusLine(const char* buffer, size_t bytes, long& statusOut) {
    statusOut = 0;
    if (!startsWithAsciiNoCase(buffer, bytes, "HTTP/")) return false;
    size_t p = 5;
    while (p < bytes && buffer[p] != ' ') ++p;
    while (p < bytes && buffer[p] == ' ') ++p;
    if (p + 2 >= bytes || buffer[p] < '0' || buffer[p] > '9' ||
        buffer[p + 1] < '0' || buffer[p + 1] > '9' ||
        buffer[p + 2] < '0' || buffer[p + 2] > '9') return false;
    statusOut = (buffer[p] - '0') * 100L + (buffer[p + 1] - '0') * 10L + (buffer[p + 2] - '0');
    return true;
}

'''
    text = replace_between(text, helper_start, helper_end, helpers, "safe header helpers")

    cb_start = "static size_t headerCallback(char* buffer, size_t size, size_t nitems, void* userdata) {"
    cb_end = "static size_t writeCallback(void* ptr, size_t size, size_t nmemb, void* userdata) {"
    callback = r'''static size_t headerCallback(char* buffer, size_t size, size_t nitems, void* userdata) {
    TransferContext* ctx = static_cast<TransferContext*>(userdata);
    const size_t bytes = size * nitems;
    if (!ctx || bytes == 0) return bytes;

    // libcurl explicitly does NOT NUL-terminate header lines and invokes this callback
    // for every response in a redirect/auth chain. Treat status lines as response
    // boundaries so Content-Length/ETag from a 30x/401 cannot leak into the final body.
    long status = 0;
    if (parseHttpStatusLine(buffer, bytes, status)) {
        ctx->responseCode = status;
        ctx->total = 0;
        ctx->totalFromContentRange = false;
        ctx->rangeValid = false;
        ctx->rangeStart = 0;
        ctx->rangeEnd = 0;
        ctx->rangeMismatch = false;
        ctx->retryAfterSeconds = 0;
        ctx->etag.clear();
        ctx->lastModified.clear();
        ctx->firstWrite = true;
        char msg[96];
        sceClibSnprintf(msg, sizeof(msg), "response status=%ld", status);
        httpDiagnostic(msg);
        return bytes;
    }

    const std::string contentLength = headerValue(buffer, bytes, "Content-Length:");
    if (!contentLength.empty()) {
        unsigned long long value = 0;
        if (std::sscanf(contentLength.c_str(), "%llu", &value) == 1)
            ctx->total = static_cast<uint64_t>(value);
    }

    const std::string contentRange = headerValue(buffer, bytes, "Content-Range:");
    if (!contentRange.empty()) {
        uint64_t rangeStart = 0;
        uint64_t rangeEnd = 0;
        uint64_t rangeTotal = 0;
        if (parseContentRangeTotal(contentRange, rangeStart, rangeEnd, rangeTotal)) {
            ctx->total = rangeTotal;
            ctx->totalFromContentRange = true;
            ctx->rangeValid = true;
            ctx->rangeStart = rangeStart;
            ctx->rangeEnd = rangeEnd;
            char rangeMsg[240];
            sceClibSnprintf(rangeMsg, sizeof(rangeMsg),
                "content-range start=%llu end=%llu total=%llu resume=%llu",
                (unsigned long long)rangeStart,
                (unsigned long long)rangeEnd,
                (unsigned long long)rangeTotal,
                (unsigned long long)ctx->resumeOffset);
            httpDiagnostic(rangeMsg);
            if (ctx->resumeOffset > 0 && rangeStart != ctx->resumeOffset) {
                ctx->rangeMismatch = true;
                char mm[220];
                sceClibSnprintf(mm, sizeof(mm),
                    "content-range MISMATCH start=%llu requested=%llu — will abort append",
                    (unsigned long long)rangeStart,
                    (unsigned long long)ctx->resumeOffset);
                httpDiagnostic(mm);
            }
        } else {
            unsigned long long rangeTotal416 = 0;
            if (std::sscanf(contentRange.c_str(), "bytes */%llu", &rangeTotal416) == 1 &&
                rangeTotal416 > 0) {
                ctx->total = static_cast<uint64_t>(rangeTotal416);
                ctx->totalFromContentRange = true;
                char rangeMsg[180];
                sceClibSnprintf(rangeMsg, sizeof(rangeMsg),
                    "content-range unsatisfied total=%llu",
                    (unsigned long long)rangeTotal416);
                httpDiagnostic(rangeMsg);
            } else {
                httpDiagnostic("content-range present but unparseable");
            }
        }
    }

    const std::string etag = headerValue(buffer, bytes, "ETag:");
    if (!etag.empty()) ctx->etag = etag;
    const std::string modified = headerValue(buffer, bytes, "Last-Modified:");
    if (!modified.empty()) ctx->lastModified = modified;
    const std::string retryAfter = headerValue(buffer, bytes, "Retry-After:");
    if (!retryAfter.empty()) {
        int sec = 0;
        if (std::sscanf(retryAfter.c_str(), "%d", &sec) == 1 && sec > 0) {
            if (sec > 30) sec = 30;
            ctx->retryAfterSeconds = sec;
        }
    }
    return bytes;
}

'''
    text = replace_between(text, cb_start, cb_end, callback, "header callback")

    text = replace_once(
        text,
        "    if (ctx->shouldCancel && ctx->shouldCancel()) {\n        ctx->cancelled = true;\n        return 0;\n    }\n\n    if (ctx->firstWrite) {\n        ctx->firstWrite = false;\n        long responseCode = 0;\n        curl_easy_getinfo(ctx->curl, CURLINFO_RESPONSE_CODE, &responseCode);\n",
        "    if (ctx->shouldCancel && ctx->shouldCancel()) {\n        ctx->cancelled = true;\n        return 0;\n    }\n\n    long responseCode = ctx->responseCode;\n    if (responseCode == 0)\n        curl_easy_getinfo(ctx->curl, CURLINFO_RESPONSE_CODE, &responseCode);\n\n    // Never write a final HTTP error page into payload.part. 4xx/5xx bodies are\n    // still consumed so curl_easy_perform can return CURLE_OK and the caller can\n    // classify/retry by HTTP status without corrupting an existing partial file.\n    if (responseCode != 200 && responseCode != 206) {\n        if (!ctx->discardedErrorBody) {\n            char msg[128];\n            sceClibSnprintf(msg, sizeof(msg), \"discarding non-payload response body status=%ld\", responseCode);\n            httpDiagnostic(msg);\n            ctx->discardedErrorBody = true;\n        }\n        return bytes;\n    }\n\n    if (ctx->firstWrite) {\n        ctx->firstWrite = false;\n",
        "discard HTTP error bodies",
    )

    text = replace_once(
        text,
        "    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, CONNECT_TIMEOUT_SECONDS);\n    curl_easy_setopt(curl, CURLOPT_TCP_KEEPALIVE, 1L);\n",
        "    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, CONNECT_TIMEOUT_SECONDS);\n    curl_easy_setopt(curl, CURLOPT_TCP_KEEPALIVE, 1L);\n#if LIBCURL_VERSION_NUM >= 0x071900\n    // Detect half-open Wi-Fi/NAT connections sooner during multi-gigabyte transfers.\n    curl_easy_setopt(curl, CURLOPT_TCP_KEEPIDLE, 30L);\n    curl_easy_setopt(curl, CURLOPT_TCP_KEEPINTVL, 15L);\n#endif\n",
        "TCP keepalive tuning",
    )

    text = replace_once(
        text,
        "        ctx.total = 0;\n        ctx.totalFromContentRange = false;\n        curlError[0] = '\\0';\n        result = curl_easy_perform(curl);\n",
        "        ctx.total = 0;\n        ctx.totalFromContentRange = false;\n        ctx.rangeValid = false;\n        ctx.rangeStart = 0;\n        ctx.rangeEnd = 0;\n        ctx.rangeMismatch = false;\n        ctx.responseCode = 0;\n        ctx.discardedErrorBody = false;\n        ctx.firstWrite = true;\n        ctx.etag.clear();\n        ctx.lastModified.clear();\n        ctx.retryAfterSeconds = 0;\n        curlError[0] = '\\0';\n        result = curl_easy_perform(curl);\n",
        "attempt response reset",
    )

    text = replace_once(
        text,
        "        const bool transientHttp =\n                responseCode == 429 || responseCode == 502 || responseCode == 503 ||\n                responseCode == 504 || responseCode == 520 || responseCode == 522 ||\n                responseCode == 524;\n",
        "        const bool transientHttp =\n                responseCode == 408 || responseCode == 425 || responseCode == 429 ||\n                responseCode == 500 || responseCode == 502 || responseCode == 503 ||\n                responseCode == 504 || responseCode == 520 || responseCode == 521 ||\n                responseCode == 522 || responseCode == 523 || responseCode == 524;\n",
        "transient HTTP status set",
    )

    HTTP.write_text(text, encoding="utf-8")


def patch_download_manager() -> None:
    text = DM.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "    // Soft size limit: catalog/HTML sizes are often approximate.\n    // Abort only well past the hint (35% + 64 MiB), not on a small overrun.\n    auto sizeHardLimit = [](uint64_t expected) -> uint64_t {\n        if (expected == 0) return 0;\n        const uint64_t pct = expected / 100ULL * 35ULL;\n        const uint64_t floor = 64ULL * 1024ULL * 1024ULL;\n        return expected + (pct > floor ? pct : floor);\n    };\n\n    bool sizeLimitHit = false;\n    uint64_t lastSaved = offset;\n",
        "    // Catalog and MediaFire page sizes are hints. Only enforce a hard overrun\n    // after HttpClient has received an authoritative Content-Length/Content-Range.\n    auto sizeHardLimit = [](uint64_t total) -> uint64_t {\n        if (total == 0) return 0;\n        const uint64_t slack = 8ULL * 1024ULL * 1024ULL;\n        return total > (~0ULL - slack) ? ~0ULL : total + slack;\n    };\n\n    bool sizeLimitHit = false;\n    bool diskSpaceHit = false;\n    bool remoteTotalKnown = false;\n    uint64_t lastSaved = offset;\n    uint64_t lastSpaceCheck = 0;\n    constexpr uint64_t kMetadataSaveStep = 8ULL * 1024ULL * 1024ULL;\n    constexpr uint64_t kSpaceCheckStep = 32ULL * 1024ULL * 1024ULL;\n    constexpr uint64_t kFreeSpaceReserve = 16ULL * 1024ULL * 1024ULL;\n",
        "download manager guards",
    )

    text = replace_once(
        text,
        "        // Prefer real Content-Length when the server sends it.\n        if (p.total > 0) job.expectedSize = p.total;\n        const uint64_t limit = sizeHardLimit(job.expectedSize);\n        if (limit > 0 && job.downloadedSize > limit) {\n",
        "        // p.total is only non-zero when HttpClient observed a remote length.\n        if (p.total > 0) {\n            job.expectedSize = p.total;\n            remoteTotalKnown = true;\n        }\n        const uint64_t limit = remoteTotalKnown ? sizeHardLimit(job.expectedSize) : 0;\n        if (limit > 0 && job.downloadedSize > limit) {\n",
        "authoritative size guard",
    )

    text = replace_once(
        text,
        "        if (onProgress_) {\n",
        "        if (!diskSpaceHit &&\n            (lastSpaceCheck == 0 || job.downloadedSize < lastSpaceCheck ||\n             job.downloadedSize - lastSpaceCheck >= kSpaceCheckStep)) {\n            uint64_t freeB = 0, totalB = 0;\n            if (StorageManager::queryUx0Space(freeB, totalB) && freeB < kFreeSpaceReserve) {\n                diskSpaceHit = true;\n                job.cancelRequested = true;\n                char m[180];\n                sceClibSnprintf(m, sizeof(m),\n                    \"[DownloadManager] low-space guard free=%llu downloaded=%llu reserve=%llu\",\n                    (unsigned long long)freeB,\n                    (unsigned long long)job.downloadedSize,\n                    (unsigned long long)kFreeSpaceReserve);\n                diagnostics::log(m);\n            }\n            lastSpaceCheck = job.downloadedSize;\n        }\n        if (onProgress_) {\n",
        "runtime free-space guard",
    )

    text = replace_once(
        text,
        "        if (job.downloadedSize >= lastSaved + 256 * 1024 || job.downloadedSize < lastSaved) {\n",
        "        if ((job.downloadedSize >= lastSaved && job.downloadedSize - lastSaved >= kMetadataSaveStep) ||\n            job.downloadedSize < lastSaved) {\n",
        "metadata write throttling",
    )

    old_mediafire = '''            if (mediafire) {
                st.removeFile(job.temporaryPath);
                offset = 0;
                job.downloadedSize = 0;
                std::string direct;
                std::string mfErr;
                uint64_t mfSize = 0;
                if (resolveMediaFireDirectUrl(http_, job.url, direct, mfErr, &mfSize) && !direct.empty()) {
                    effectiveUrl = direct;
                    if (mfSize > 0) job.expectedSize = mfSize;
                    diagnostics::log("[DownloadManager] MediaFire re-resolved for retry");
                } else {
                    diagnostics::log(std::string("[DownloadManager] MediaFire re-resolve failed: ") + mfErr);
                }
            } else if (job.downloadedSize == 0) {
'''
    new_mediafire = '''            if (mediafire) {
                // MediaFire direct URLs expire, but the bytes already downloaded do not.
                // Re-resolve the page and attempt a normal Range resume against the new
                // direct URL. HttpClient will safely truncate/restart if that CDN edge
                // ignores Range or serves a changed resource.
                const int64_t sz = st.fileSize(job.temporaryPath);
                offset = sz > 0 ? static_cast<uint64_t>(sz) : 0;
                job.downloadedSize = offset;
                std::string direct;
                std::string mfErr;
                uint64_t mfSize = 0;
                if (resolveMediaFireDirectUrl(http_, job.url, direct, mfErr, &mfSize) && !direct.empty()) {
                    effectiveUrl = direct;
                    if (mfSize > 0) job.expectedSize = mfSize;
                    job.validatorUrl.clear();
                    job.etag.clear();
                    job.lastModified.clear();
                    remoteTotalKnown = false;
                    char mfMsg[180];
                    sceClibSnprintf(mfMsg, sizeof(mfMsg),
                        "[DownloadManager] MediaFire re-resolved resume_offset=%llu expected_hint=%llu",
                        (unsigned long long)offset,
                        (unsigned long long)job.expectedSize);
                    diagnostics::log(mfMsg);
                } else {
                    diagnostics::log(std::string("[DownloadManager] MediaFire re-resolve failed: ") + mfErr);
                    if (outer + 1 < outerAttempts) continue;
                    break;
                }
            } else if (job.downloadedSize == 0) {
'''
    text = replace_once(text, old_mediafire, new_mediafire, "MediaFire resume preservation")

    text = replace_once(
        text,
        "            sizeLimitHit = false;\n            job.cancelRequested = false;\n",
        "            sizeLimitHit = false;\n            diskSpaceHit = false;\n            remoteTotalKnown = false;\n            lastSpaceCheck = 0;\n            job.cancelRequested = false;\n",
        "retry guard reset",
    )

    text = replace_once(
        text,
        "    if (sizeLimitHit) {\n",
        "    if (diskSpaceHit) {\n        st.removeFile(job.temporaryPath);\n        job.downloadedSize = 0;\n        job.state = DownloadState::Failed;\n        job.lastError = \"not enough free space while downloading\";\n        saveMetadata(job);\n        st.removeFile(job.finalPath);\n        diagnostics::log(\"[DownloadManager] aborted by runtime low-space guard\");\n        return false;\n    }\n    if (sizeLimitHit) {\n",
        "disk-space result",
    )

    DM.write_text(text, encoding="utf-8")


def patch_zip() -> None:
    text = ZIP.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "        // Pre-scan: sum uncompressed sizes, log large/unusual entries, then verify free space.\n    uint64_t uncompressedTotal = 0;\n    const int64_t archiveSize = st.fileSize(zipPath);\n",
        "    // Pre-scan: sum uncompressed sizes, log large/unusual entries, then verify free space.\n    uint64_t uncompressedTotal = 0;\n    const uint64_t archiveDiskSize = diskFileSize64(zipPath);\n",
        "ZIP archive size caching",
    )

    text = replace_once(
        text,
        "            if (!isDir && (zs.valid & ZIP_STAT_SIZE) && zs.size > 0) {\n                uncompressedTotal += static_cast<uint64_t>(zs.size);\n                prog.bytesTotal += static_cast<uint64_t>(zs.size);\n            }\n",
        "            if (!isDir && (zs.valid & ZIP_STAT_SIZE) && zs.size > 0) {\n                const uint64_t entrySize = static_cast<uint64_t>(zs.size);\n                if (entrySize > (~0ULL - uncompressedTotal) || entrySize > (~0ULL - prog.bytesTotal)) {\n                    setError(std::string(\"ZIP uncompressed size overflow at entry: \") + zs.name);\n                    zip_close(za);\n                    return ZipResult::InvalidEntry;\n                }\n                uncompressedTotal += entrySize;\n                prog.bytesTotal += entrySize;\n            }\n",
        "ZIP size overflow guard",
    )

    text = replace_once(
        text,
        "        const uint64_t margin = (32ULL * 1024ULL * 1024ULL) + (uncompressedTotal / 20ULL);\n        const uint64_t required = uncompressedTotal + margin;\n",
        "        const uint64_t margin = (32ULL * 1024ULL * 1024ULL) + (uncompressedTotal / 20ULL);\n        const uint64_t required = uncompressedTotal > (~0ULL - margin) ? ~0ULL : uncompressedTotal + margin;\n",
        "ZIP required-space overflow guard",
    )

    text = text.replace("archive=%lld", "archive=%llu")
    text = text.replace("(long long)archiveSize", "(unsigned long long)archiveDiskSize")

    text = replace_once(
        text,
        "        const unsigned method = (zs.valid & ZIP_STAT_COMP_METHOD) ? static_cast<unsigned>(zs.comp_method) : 0u;\n        const uint64_t archiveDiskSize = diskFileSize64(zipPath);\n        bool fileOk = true;\n",
        "        const unsigned method = (zs.valid & ZIP_STAT_COMP_METHOD) ? static_cast<unsigned>(zs.comp_method) : 0u;\n        bool fileOk = true;\n",
        "remove per-entry archive reopen",
    )

    text = replace_once(
        text,
        "        sceIoClose(fd);\n        zip_fclose(zf);\n\n        if (fileOk) {\n",
        "        const int zipCloseResult = zip_fclose(zf);\n        const int ioCloseResult = sceIoClose(fd);\n        if (fileOk && zipCloseResult != 0) {\n            char detail[240];\n            sceClibSnprintf(detail, sizeof(detail),\n                \"zip_fclose failed entry=%s code=%d written=%llu\",\n                name, zipCloseResult, (unsigned long long)writtenTotal);\n            setError(detail);\n            outcome = ZipResult::IoError;\n            fileOk = false;\n        }\n        if (fileOk && ioCloseResult < 0) {\n            char detail[240];\n            sceClibSnprintf(detail, sizeof(detail),\n                \"sceIoClose failed entry=%s ret=%d written=%llu\",\n                name, ioCloseResult, (unsigned long long)writtenTotal);\n            setError(detail);\n            outcome = ZipResult::IoError;\n            fileOk = false;\n        }\n\n        if (fileOk) {\n",
        "ZIP close result checks",
    )

    text = replace_once(
        text,
        "    zip_close(za);\n    if (outcome == ZipResult::Ok) {\n",
        "    const int archiveCloseResult = zip_close(za);\n    if (archiveCloseResult != 0) {\n        if (outcome == ZipResult::Ok) {\n            setError(std::string(\"zip_close failed: \") + zipArchiveError(za));\n            outcome = ZipResult::IoError;\n        }\n        zip_discard(za);\n    }\n    if (outcome == ZipResult::Ok) {\n",
        "ZIP archive close check",
    )

    ZIP.write_text(text, encoding="utf-8")


def patch_docs() -> None:
    text = DOC.read_text(encoding="utf-8")
    marker = "## Optional: mbedTLS-backed curl (build-time)\n"
    if "## Download integrity hardening" not in text:
        addition = '''## Download integrity hardening\n\nThe production client also:\n\n- parses libcurl header callbacks using the explicit byte count (header lines are not NUL-terminated);\n- resets response metadata at every HTTP status line so redirect/auth headers cannot contaminate the final response;\n- discards final 4xx/5xx response bodies instead of writing HTML/error payloads into `.part` files;\n- retries additional transient HTTP statuses (408/425/500/521/523 in addition to 429/502/503/504/520/522/524);\n- enables TCP keepalive tuning for long downloads when supported by the linked libcurl;\n- only enforces size-overrun guards after a real Content-Length/Content-Range has been observed;\n- throttles metadata writes to reduce storage churn during multi-GB transfers;\n- re-resolves expired MediaFire URLs while preserving the existing partial file and attempts a safe Range resume;\n- checks free space periodically while a long transfer is active.\n\nZIP extraction caches archive size once, rejects aggregate-size overflow, and checks both `zip_fclose()` and Vita file-close results before declaring an entry complete.\n\n'''
        if marker not in text:
            raise SystemExit("docs marker not found")
        text = text.replace(marker, addition + marker, 1)
    DOC.write_text(text, encoding="utf-8")


def main() -> None:
    patch_http()
    patch_download_manager()
    patch_zip()
    patch_docs()
    print("download stack hardening applied")


if __name__ == "__main__":
    main()
