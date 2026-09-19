#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTTP = ROOT / "Client PSVitaAlive/source/network/http_client.cpp"
ZIP = ROOT / "Client PSVitaAlive/source/archive/zip_extractor.cpp"
DOC = ROOT / "docs/NETWORK_TLS.md"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 match, got {count}")
    return text.replace(old, new, 1)


def patch_http() -> None:
    text = HTTP.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "    return bytes;\n}\n\n} // namespace\n\nconst char* toString(HttpResult r) {\n",
        "    return bytes;\n}\n\n"
        "// CURLOPT_XFERINFOFUNCTION keeps cancellation responsive even while a server\n"
        "// is connected but not delivering body data. writeCallback alone cannot see\n"
        "// cancellation during a low-speed/stalled period.\n"
        "static int transferProgressCallback(\n"
        "    void* userdata, curl_off_t, curl_off_t, curl_off_t, curl_off_t\n"
        ") {\n"
        "    TransferContext* ctx = static_cast<TransferContext*>(userdata);\n"
        "    if (!ctx) return 0;\n"
        "    if (ctx->shouldCancel && ctx->shouldCancel()) {\n"
        "        ctx->cancelled = true;\n"
        "        return 1; // libcurl -> CURLE_ABORTED_BY_CALLBACK\n"
        "    }\n"
        "    return 0;\n"
        "}\n\n"
        "} // namespace\n\nconst char* toString(HttpResult r) {\n",
        "transfer progress callback",
    )

    text = replace_once(
        text,
        "    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);\n    curl_easy_setopt(curl, CURLOPT_NOPROGRESS, 1L);\n    curl_easy_setopt(curl, CURLOPT_BUFFERSIZE, static_cast<long>(DOWNLOAD_BUFFER_SIZE));\n",
        "    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);\n"
        "#if LIBCURL_VERSION_NUM >= 0x075500\n"
        "    // Catalog URLs are external input. Keep both the initial transfer and all\n"
        "    // redirects on HTTP(S); modern libcurl otherwise supports many schemes.\n"
        "    curl_easy_setopt(curl, CURLOPT_PROTOCOLS_STR, \"http,https\");\n"
        "    curl_easy_setopt(curl, CURLOPT_REDIR_PROTOCOLS_STR, \"http,https\");\n"
        "#else\n"
        "    curl_easy_setopt(curl, CURLOPT_PROTOCOLS, (long)(CURLPROTO_HTTP | CURLPROTO_HTTPS));\n"
        "    curl_easy_setopt(curl, CURLOPT_REDIR_PROTOCOLS, (long)(CURLPROTO_HTTP | CURLPROTO_HTTPS));\n"
        "#endif\n"
        "    curl_easy_setopt(curl, CURLOPT_NOPROGRESS, 0L);\n"
        "    curl_easy_setopt(curl, CURLOPT_XFERINFOFUNCTION, transferProgressCallback);\n"
        "    curl_easy_setopt(curl, CURLOPT_XFERINFODATA, &ctx);\n"
        "    curl_easy_setopt(curl, CURLOPT_BUFFERSIZE, static_cast<long>(DOWNLOAD_BUFFER_SIZE));\n",
        "progress and protocol restrictions",
    )

    text = replace_once(
        text,
        "        // archive.org edge failover: switch not only on direct SSL CURLcodes, but also\n"
        "        // when a transport error (notably curl 56) contains explicit TLS/certificate\n"
        "        // diagnostics from the OpenSSL backend.\n"
        "        if (isArchive && tlsLikeFailure) {\n",
        "        // archive.org edge failover: storage nodes can fail as TLS errors, plain\n"
        "        // receive/send failures, timeouts, or half-open connections. Rotate away\n"
        "        // from the edge for all transport-like failures, not only certificate text.\n"
        "        const bool archiveTransportFailure =\n"
        "            tlsLikeFailure ||\n"
        "            result == CURLE_COULDNT_CONNECT ||\n"
        "            result == CURLE_OPERATION_TIMEDOUT ||\n"
        "            result == CURLE_RECV_ERROR ||\n"
        "            result == CURLE_SEND_ERROR ||\n"
        "            result == CURLE_GOT_NOTHING ||\n"
        "            result == CURLE_PARTIAL_FILE;\n"
        "        if (isArchive && archiveTransportFailure) {\n",
        "archive transport failover widening",
    )

    old_http_retry = '''            httpDiagnostic(httpRetry);
            lastFail = CURLE_HTTP_RETURNED_ERROR;
            lastTlsLikeFail = false;
            if (resumeOffset == 0 && ctx.fd >= 0 && ctx.downloaded > 0) {
                sceIoClose(ctx.fd);
                ctx.fd = sceIoOpen(destinationPath.c_str(), SCE_O_WRONLY | SCE_O_CREAT | SCE_O_TRUNC, 0777);
                ctx.downloaded = 0;
            }
            continue;
'''
    new_http_retry = '''            httpDiagnostic(httpRetry);
            lastFail = CURLE_HTTP_RETURNED_ERROR;
            lastTlsLikeFail = false;
            if (resumeOffset == 0 && ctx.fd >= 0 && ctx.downloaded > 0) {
                sceIoClose(ctx.fd);
                ctx.fd = sceIoOpen(destinationPath.c_str(), SCE_O_WRONLY | SCE_O_CREAT | SCE_O_TRUNC, 0777);
                ctx.downloaded = 0;
            }

            // 5xx from archive.org is commonly edge-specific. Resolve the item metadata
            // once and rotate to another storage node before spending more retries on
            // the same failing edge. 408/425/429 keep the normal retry path.
            if (isArchive && responseCode >= 500) {
                if (!archiveMetaTried) {
                    archiveMetaTried = true;
                    buildArchiveAlternateUrls(url, archiveAltUrls);
                    archiveAltIndex = 0;
                }
                if (archiveAltIndex < archiveAltUrls.size()) {
                    activeUrl = archiveAltUrls[archiveAltIndex++];
                    char sw[360];
                    sceClibSnprintf(sw, sizeof(sw),
                        "archive failover switch HTTP=%ld -> %s",
                        responseCode, activeUrl.c_str());
                    httpDiagnostic(sw);
                    curl_easy_setopt(curl, CURLOPT_URL, activeUrl.c_str());
                    curl_easy_setopt(curl, CURLOPT_FRESH_CONNECT, 1L);
                    curl_easy_setopt(curl, CURLOPT_FORBID_REUSE, 1L);
                    curl_easy_setopt(curl, CURLOPT_SSL_SESSIONID_CACHE, 0L);
                }
            }
            continue;
'''
    text = replace_once(text, old_http_retry, new_http_retry, "Archive HTTP 5xx failover")

    HTTP.write_text(text, encoding="utf-8")


def patch_zip() -> None:
    text = ZIP.read_text(encoding="utf-8")
    old = '''            if ((zs.valid & ZIP_STAT_COMP_METHOD) &&
                zs.comp_method != 0 && zs.comp_method != 8) {
                char warn[200];
                sceClibSnprintf(
                    warn, sizeof(warn),
                    "entry uses compression method=%u (%s) name=%s — may be unsupported on Vita",
                    static_cast<unsigned>(zs.comp_method),
                    compressionMethodName(static_cast<zip_uint16_t>(zs.comp_method)),
                    zs.name);
                diagnostics::log(std::string("[ZipExtractor] ") + warn);
            }
'''
    new = '''            if (zs.valid & ZIP_STAT_COMP_METHOD) {
                // libzip can report methods that the current build cannot decompress.
                // Fail before creating any output instead of discovering this halfway
                // through a multi-gigabyte extraction.
                if (!zip_compression_method_supported(static_cast<zip_int32_t>(zs.comp_method), 1)) {
                    char err[260];
                    sceClibSnprintf(
                        err, sizeof(err),
                        "unsupported ZIP compression method=%u (%s) entry=%s",
                        static_cast<unsigned>(zs.comp_method),
                        compressionMethodName(static_cast<zip_uint16_t>(zs.comp_method)),
                        zs.name);
                    setError(err);
                    zip_close(za);
                    return ZipResult::InvalidEntry;
                }
                if (zs.comp_method != 0 && zs.comp_method != 8) {
                    char warn[200];
                    sceClibSnprintf(
                        warn, sizeof(warn),
                        "entry uses compression method=%u (%s) name=%s",
                        static_cast<unsigned>(zs.comp_method),
                        compressionMethodName(static_cast<zip_uint16_t>(zs.comp_method)),
                        zs.name);
                    diagnostics::log(std::string("[ZipExtractor] ") + warn);
                }
            }
'''
    text = replace_once(text, old, new, "ZIP compression capability preflight")
    ZIP.write_text(text, encoding="utf-8")


def patch_docs() -> None:
    text = DOC.read_text(encoding="utf-8")
    marker = "- checks free space periodically while a long transfer is active.\n"
    if "XFERINFO" not in text:
        addition = (
            marker
            + "- uses libcurl's XFERINFO progress callback so cancellation is still observed while a connection is stalled;\n"
            + "- restricts initial URLs and redirects to HTTP/HTTPS only;\n"
            + "- rotates Archive.org storage hosts for transport failures and server-side 5xx responses, not only explicit TLS failures.\n"
        )
        if marker not in text:
            raise SystemExit("docs hardening marker not found")
        text = text.replace(marker, addition, 1)
    DOC.write_text(text, encoding="utf-8")


def main() -> None:
    patch_http()
    patch_zip()
    patch_docs()
    print("download hardening phase 2 applied")


if __name__ == "__main__":
    main()
