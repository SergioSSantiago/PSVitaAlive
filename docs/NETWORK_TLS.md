# PSVitaAlive — TLS / libcurl notes

## Default stack (production today)

- **libcurl** from VitaSDK (e.g. 8.x)
- **OpenSSL 1.0.2** (EOL) as TLS backend
- App sets `CURLOPT_SSL_VERIFYPEER/HOST = 0` (no system CA store on Vita)

This works for GitHub and many hosts. Some **Internet Archive** storage nodes (`dn*.ca.archive.org`) fail TLS handshakes or drop the connection on this stack.

## Runtime mitigations (always on)

1. Re-apply verify-off + clear `CAINFO`/`CAPATH` every download attempt.
2. Keep a `CURLOPT_ERRORBUFFER` for the detailed backend error text returned by libcurl/OpenSSL.
3. Read `CURLINFO_SSL_VERIFYRESULT` after each transfer attempt for diagnostics.
4. Treat direct SSL errors as TLS failures. For Internet Archive, also treat transport failures such as `CURLE_RECV_ERROR` (56) as TLS-like when the error buffer explicitly contains SSL/TLS/certificate/OpenSSL/X509 diagnostics, or when curl 56 has a non-zero SSL verify result.
5. On an archive.org TLS-like failure, fetch `https://archive.org/metadata/<id>` and retry on alternate hosts (`server` / `d1` / `d2`), preferring non-`dn` / non-`.ca` edges.
6. After TLS-like failures, force a fresh connection and disable SSL session reuse for the retry. This avoids sticking to a bad connection/session while leaving normal successful transfers reusable.
7. Multi-gigabyte resumes use `CURLOPT_RESUME_FROM_LARGE` (`curl_off_t`) so offsets beyond the Vita's 32-bit `long` range are not truncated.
8. A resumed HTTP 206 response is accepted only when `Content-Range` starts exactly at the requested offset. If a server ignores Range and returns 200, the partial is truncated and the transfer restarts from zero instead of appending corrupt data.
9. Before declaring success, the downloaded file size is compared with the authoritative remote total when `Content-Length` or `Content-Range` supplied one.

Useful diagnostics in `ux0:data/psvitaalive/logs/session.log`:

- `attempt ... tls_like=... ssl_verify=... detail=...`
- `archive failover built N alternate URL(s)`
- `archive failover switch curl=... ssl_verify=... -> https://...`
- `retry resume from absolute=...`
- `RESULT ... effective_url=... curl_detail=...`

### Why curl 56 matters

`CURLE_RECV_ERROR` is a receive/transport error, not one of libcurl's dedicated certificate-verification return codes. On the Vita OpenSSL stack we have observed curl 56 accompanied by explicit certificate diagnostics such as `self signed certificate in certificate chain`. The client therefore does **not** reinterpret every curl 56 as SSL: it only enables the TLS-specific Archive.org failover when the backend diagnostics support that conclusion.

## ZIP/download integrity

The downloader and ZIP extractor deliberately keep strict integrity checks instead of trying to hide damaged transfers:

- interrupted downloads resume from the absolute number of bytes already on disk;
- invalid/mismatched HTTP ranges clean-restart instead of appending;
- ZIP/ZIP64 archives are checked for a valid beginning and an EOCD/ZIP64 marker near EOF before extraction;
- large ZIP files use a seekable `sceIo*`-backed libzip source with 64-bit Vita file offsets;
- extraction is streamed in small chunks rather than loading the archive or an entry into RAM;
- path traversal (`..`, absolute paths, mount-colon paths) is rejected;
- the extractor checks available `ux0:` space against the summed uncompressed size plus a filesystem margin;
- partial output files are removed if `zip_fread` or `sceIoWrite` fails;
- each extracted entry is checked against the uncompressed size reported by `zip_stat` when available.

These behaviors are intentionally conservative for PS Vita memory limits and multi-gigabyte game-data ZIPs.

## Official library references

libcurl:

- Error codes (`CURLE_RECV_ERROR`, SSL errors): https://curl.se/libcurl/c/libcurl-errors.html
- Detailed error buffer: https://curl.se/libcurl/c/CURLOPT_ERRORBUFFER.html
- Peer verification: https://curl.se/libcurl/c/CURLOPT_SSL_VERIFYPEER.html
- SSL verification result: https://curl.se/libcurl/c/CURLINFO_SSL_VERIFYRESULT.html
- 64-bit resume offset: https://curl.se/libcurl/c/CURLOPT_RESUME_FROM_LARGE.html
- SSL session cache: https://curl.se/libcurl/c/CURLOPT_SSL_SESSIONID_CACHE.html
- Fresh connections / no reuse: https://curl.se/libcurl/c/CURLOPT_FRESH_CONNECT.html and https://curl.se/libcurl/c/CURLOPT_FORBID_REUSE.html

libzip:

- Reference documentation: https://libzip.org/documentation/
- Reading entry data: https://libzip.org/documentation/zip_fread.html
- File error handling: https://libzip.org/documentation/zip_file_get_error.html
- Custom sources: https://libzip.org/documentation/zip_source_function.html
- Source reads: https://libzip.org/documentation/zip_source_read.html
- ZIP error codes: https://libzip.org/documentation/zip_errors.html

## Download integrity hardening

The production client also:

- parses libcurl header callbacks using the explicit byte count (header lines are not NUL-terminated);
- resets response metadata at every HTTP status line so redirect/auth headers cannot contaminate the final response;
- discards final 4xx/5xx response bodies instead of writing HTML/error payloads into `.part` files;
- retries additional transient HTTP statuses (408/425/500/521/523 in addition to 429/502/503/504/520/522/524);
- enables TCP keepalive tuning for long downloads when supported by the linked libcurl;
- only enforces size-overrun guards after a real Content-Length/Content-Range has been observed;
- throttles metadata writes to reduce storage churn during multi-GB transfers;
- re-resolves expired MediaFire URLs while preserving the existing partial file and attempts a safe Range resume;
- checks free space periodically while a long transfer is active.

ZIP extraction caches archive size once, rejects aggregate-size overflow, and checks both `zip_fclose()` and Vita file-close results before declaring an entry complete.

## Optional: mbedTLS-backed curl (build-time)

```bash
# On the build machine (VitaSDK)
vdpm mbedtls
vdpm curl-mbedtls   # if available on your channel

cd "Client PSVitaAlive"
rm -rf build && mkdir build && cd build
cmake .. -DPSVITAALIVE_USE_MBEDTLS_CURL=ON
cmake --build . -j$(nproc)
```

If `curl-mbedtls` is not installed, the default OpenSSL link remains the safe path (`-DPSVITAALIVE_USE_MBEDTLS_CURL=OFF`).

## Recommendation

1. Ship with **archive.org failover** as the default production path.
2. Keep the strict range/size checks enabled; they prevent silent corruption after retries.
3. Test mbedTLS on a side build before switching the official release.
