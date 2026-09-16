# BGDL preparation frame — PS Vita client

This document describes the UI handoff used before queuing commercial PKG downloads through the PS Vita system BGDL service.

## Problem

Commercial Vita / PSP / PS1 PKG links that target LiveArea are queued through `SceShellSvc` / BGDL. The enqueue path is synchronous from the client's point of view and can take long enough that the UI appears frozen between pressing **Download** and receiving the final **Queued** result.

An earlier attempt to run the BGDL enqueue itself on the install worker changed the execution context of the ShellSvc/IPMI calls and regressed working BGDL behaviour. The working rule is therefore:

> **Keep the BGDL enqueue on the main thread. Do not move it to the install worker just to animate the UI.**

## Solution

`InstallController` now uses a one-poll deferred BGDL flag.

When `requestInstall()` decides that a package must use BGDL it still performs the existing setup:

```text
set stage = BGDL
set state = Downloading
set message = Preparing license and queuing system download...
arm active BGDL job
return to UI
```

The armed flag deliberately reads as `false` on the first `status()` poll. This lets the main loop copy the already-published `Downloading / BGDL / Preparing` state into `FullCatalogScreen` without executing ShellSvc yet.

The resulting order is:

```text
User presses Download
        ↓
requestInstall() publishes BGDL preparation state
        ↓
status() poll #1
        ↓
BGDL is intentionally deferred
        ↓
main copies preparation state to FullCatalogScreen
        ↓
next updateAndDraw()
        ↓
preparation overlay is rendered and presented
        ↓
status() poll #2
        ↓
existing main-thread BGDL enqueue runs unchanged
        ↓
Queued / Failed result
```

This gives the user visible feedback before the synchronous BGDL call blocks the main thread.

## Implementation boundary

The fix is intentionally narrow:

- `BgdlClient` is unchanged.
- `PkgBgdlInstaller` is unchanged.
- The ShellSvc/IPMI enqueue sequence is unchanged.
- BGDL is **not** moved to a worker thread.
- Homebrew VPK, ZIP extraction, plugin installation and direct PSP/PS1 Adrenaline downloads keep their existing worker behaviour.
- The UI continues using the existing `BGDL` install stage and indeterminate preparation presentation; no fake percentage is introduced.

The deferral lives in `InstallController` as `DeferredBgdlFlag`. Assigning `true` arms the job and marks the next boolean read to be skipped. The following read returns the real active state. Assigning `false` clears both the active state and the pending deferral.

## Why one status poll is enough

The normal main loop presents `screen.updateAndDraw()` and then polls `installer.status()` to copy installer state into the UI for the next frame. After a BGDL request is created during a UI frame, the first deferred poll copies the preparation state. The next loop iteration therefore presents that overlay before the second poll enters BGDL.

This is a frame-ordering fix, not an asynchronous BGDL implementation.

## Expected user experience

Before the system queue is created, the install overlay should remain visible with the BGDL preparation state, for example:

```text
Preparing download
<catalog application name>
Preparing license and queuing system download...
```

The progress indicator is indeterminate because PSVitaAlive is not downloading the PKG itself during this stage. Once the system accepts the job, the existing success result tells the user that the download was queued and continues from the LiveArea notification area.

## Regression checklist

Test on real PS Vita hardware before considering the change validated:

1. Vita Game base PKG with valid `content_id` / zRIF.
2. Vita DLC PKG.
3. Vita Update PKG where supported by the catalog entry.
4. PSP / PS1 PKG with target **LiveArea**.
5. Confirm the preparation overlay is visible before the final Queued message.
6. Confirm the BGDL task appears in LiveArea notifications and downloads normally.
7. Confirm repeated BGDL installs still queue correctly.
8. Confirm BGDL failure still produces the existing error result.
9. Confirm Homebrew VPK install is unchanged.
10. Confirm ZIP / data-file install is unchanged.
11. Confirm PSP / PS1 target **Adrenaline** still bypasses BGDL and uses the direct worker path.

Useful log tags:

```text
[Installer]
[BGDL]
[PkgBgdl]
[LicenseHelper]
```

## Do not regress this design

If the UI needs richer animation in the future, keep the ShellSvc/IPMI enqueue context unchanged unless a new implementation has been proven on real hardware. Prefer rendering/presenting UI state **before** the blocking BGDL call rather than moving that call to another thread.
