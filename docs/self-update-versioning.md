# PSVitaAlive self-update versioning

## Current rule

The PS Vita client must use the GitHub Release `tag_name` as the only source of truth for the remote client version.

Release `name` and `body` are free-form human-readable metadata. Numbers in release notes (file sizes, RAM amounts, years, issue IDs, counts, etc.) must never affect update detection.

Valid examples include tags such as:

- `02.04`
- `v02.04`
- `1.2.3`
- `BETA-0.1`

If a tag does not contain exactly one dotted numeric version, the client must fail the update check safely instead of guessing a version from other release metadata.

## Reason

Before this rule, the updater collected version-like numbers from `tag_name`, release `name`, and release `body`, then selected the numerically highest candidate. A number such as `64` in release notes could therefore override a real version such as `02.04` and cause the client to repeatedly download and install the same release.

## Future safeguards — not implemented yet

When release automation is revisited, consider adding validation that:

1. the GitHub Release tag matches the client `VITA_VERSION` in `Client PSVitaAlive/CMakeLists.txt`;
2. the published VPK reports the same internal version as the release tag;
3. malformed or ambiguous release tags are rejected before publication.

These checks are documentation only for now; no release workflow or GitHub Actions behavior is changed by this note.
