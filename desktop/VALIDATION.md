# Desktop alpha validation — 2026-10-16

The macOS Apple Silicon alpha is ready for local product/security review. Full six-platform Phase 5 acceptance remains open: native Windows, Intel macOS and Linux x64 runs, physical OS lock/sleep testing, and native file-dialog walkthroughs still need verification. No installers have been published, and no branch has been pushed or merged.

## Source and artifacts

- Branch: `phase5-desktop-alpha`; isolated worktree: `/private/tmp/ciphermoth-desktop`.
- Verified base: latest local/GitHub master and v3.0.0 release commit `12946f3cc4b6333d27753d9b101b67b8d3fe8649` at the start of implementation.
- Reused spike: `experiment/desktop-feasibility` at `9d3a4ea`. The main checkout, experimental worktree and private planning reports were preserved.
- Commits use the existing maintainer identity, Alexandru Grajdeanu `<grajdeanu.alex@gmail.com>`, as author and committer. See `git log 12946f3..HEAD` for focused implementation commits.
- Local macOS app: `desktop/src-tauri/target/release/bundle/macos/CipherMoth Alpha.app`.
- Local archive: `/private/tmp/CipherMoth-Alpha-macos-arm64.zip` (not a published installer).
- Final production shell SHA256: `eae86183f9b59d8b835098441c907a2121e68fcedb30df5472d4e97ff3d61a30`.

Open the complete `.app` in Finder, create a master password, and add a password. Log out or press Command+Shift+L to lock; quit and reopen to unlock the persisted vault. Copy the complete app to Applications if desired. The worktree/archive are in a temporary location and should be retained elsewhere before OS temporary-file cleanup. The app stores its vault separately under its application-local identity, never inside this worktree or bundle.

This is an unsigned/local development artifact. `codesign` reports a linker ad-hoc signature, no TeamIdentifier, no sealed resources, and no hardened-runtime signing flag. The Tauri configuration requests hardened runtime for future signing; it does not establish enforcement in this unsigned bundle. No library-validation bypass entitlement was added.

## Implemented behavior

The real v3 Python core runs as a PyInstaller onedir sidecar behind private framed stdin/stdout IPC, with the actual FastAPI lifespan and SQLite storage layer. No HTTP server runs. Python owns the keys and sessions. React receives opaque session tokens held in memory; Rust carries requests without implementing vault cryptography. The shared HTTP deployment remains supported.

The existing React vault supports creation/unlock, entry CRUD/search/organization, notes, TOTP, history, Trash, attachments, password rotation and encrypted backups through its platform adapter. Native clipboard timers, file dialogs, external-link allowlisting, startup/retry handling, manual/idle locking and OS lock handlers are implemented. Startup compatibility checks, bounded crash recovery and platform process cleanup were ported from the spike. Source development launches Vite and the dedicated Python venv without freezing after edits; that launch was verified locally.

Backups stream ciphertext directly between an OS-authorized file and the existing Python backup endpoints. The renderer receives only a single-use file grant. A regression round-trips more than 25 MiB of attachment data and validates restoration, exceeding the old 24 MiB frame limit. Cancellation, disk-full failure and destination races are tested; existing files are never overwritten. Full 1 GiB operation and native dialog interactions were not automated locally. Hard-link publication requires a supporting filesystem; a forced OS kill can leave an encrypted `.partial` file. See [README.md](README.md) for these limitations.

## Automated results

| Check | Result |
| --- | --- |
| Shared backend suite | **783 passed**, 2 deselected; 350.47 s |
| Shared frontend suite | **139 passed**, 11 files |
| Repository `make check` | Passed; 6 existing React refresh warnings, no errors |
| Desktop Python lint/format | Passed, 17 files |
| macOS packaged desktop core suite | **27 passed**, 62.54 s |
| Linux arm64 packaged desktop core suite | **26 passed, 1 skipped**, 52.80 s |
| Frozen v3 cryptographic vectors | **27 passed** on macOS arm64 and Linux arm64 |
| Actual packaged SQLite | **3.53.1** on both tested platforms |
| Python runtime | **3.13.15** on both tested platforms |
| Rust tests | **5 passed** on macOS arm64 and Linux arm64 |
| Rust formatting / Clippy with warnings denied | Passed on both tested platforms |
| Intel macOS Rust shell cross-check | `cargo check --target x86_64-apple-darwin` passed |
| Existing Docker/server smoke suite | **26 checks passed** against locally built backend/frontend images |
| GitHub six-target desktop CI | Prepared, **not run**; branch remains unpublished |

The core suite exercises wrong/correct unlock, persistence, ciphertext metadata/canaries, CRUD/notes/TOTP/Trash/history, binary attachments, rotation/revocation, large backup restore, idle expiry, malformed/oversized frames, cancellation, shutdown, one-session enforcement, file permissions, and damaged/unsupported vault refusal. It uses real framed desktop transport rather than HTTP sockets. The Linux per-process socket assertion is skipped because process dump protection prevents inspection; the native harness separately verifies no new listening socket in the isolated container's network namespace.

The Docker smoke run used isolated `cm-phase5-desktop-*` projects and synthetic volumes. Its local `phase5-local` image tags were not pushed. The Linux native container `cm-phase5-linux-arm64-20261016` was stopped after verification. No existing installation or user vault was migrated or modified.

## Native application evidence

The QA artifact runs the real React forms inside WKWebView on macOS and WebKitGTK on Linux, with the packaged v3 core. It creates the vault and first password through the UI, retrieves it through native IPC, rejects ungranted capabilities, exercises request timeout, locks/re-unlocks, kills/restarts the core, closes/reopens the app and checks for orphan processes. These are native application tests, not browser Playwright tests.

macOS also verifies clipboard expiry while Finder is focused, preservation of replacement clipboard text, and delivery through the Cocoa workspace-sleep notification handler. Physical machine sleep and screen locking were **not** performed. Linux exercises the native lock callback directly, not delivery from a real desktop/logind session. The root Linux container uses Xvfb and disables the WebKit sandbox only in the test environment; it is not proof of normal desktop/Wayland sandbox behavior. No sandbox-disable option is built into the application.

An additional native Save/Open-dialog automation attempt reached the save operation but was blocked by macOS: `osascript is not allowed to send keystrokes (1002)`. No Accessibility permissions were changed. The opt-in harness is retained for a host with automation permission; this attempted walkthrough is not counted as passing. The core file workflow, large-backup round trip and fault handling passed separately.

Synthetic password, entry-name and raw-key canaries were absent from the eight files in the macOS QA data/log tree. The QA app's known WebKit/cache/HTTP storage/saved-state directories contained no files. This is a scoped leakage check, not a forensic scan of the entire OS.

Local evidence, retained outside Git:

- `/private/tmp/ciphermoth-native-qa-final/results.json` — final macOS native run.
- `/private/tmp/ciphermoth-linux-phase5/final-native/results.json` — final Linux arm64 installed `.deb` run.
- `/private/tmp/ciphermoth-desktop-frozen-tests.log` and `/private/tmp/ciphermoth-linux-phase5/final-core-tests.log`.
- `/private/tmp/ciphermoth-desktop-backend-verified.log`, `/private/tmp/ciphermoth-desktop-final-frontend-tests.log`, `/private/tmp/ciphermoth-desktop-final-check.log`.
- `/private/tmp/ciphermoth-phase5-compose-smoke.log` — existing server/Docker behavior.
- `/private/tmp/ciphermoth-final-bundle-vectors.json`, `/private/tmp/ciphermoth-final-startup.json`.

## Performance snapshot

Host: Apple M3 Max, 14 CPU cores, 96 GiB RAM, macOS 26.6.2. These are development-machine observations, not release benchmarks.

| Measurement | Result / scope |
| --- | --- |
| Packaged core spawn to ready | Median **0.302 s**, five fresh synthetic databases, warm filesystem cache; range 0.299–0.306 s |
| Native shell-observed core readiness | Approximately **0.33–0.36 s** in final macOS lifecycle run |
| Earlier launch through first UI create/save/retrieve | **3.33 s**; includes KDFs and UI automation, not a pure startup measurement |
| Final full initial native scenario | **18.65 s**, including two lock/unlock cycles and deliberate clipboard waits |
| macOS shell RSS | **102.8 MiB** at final scenario checkpoint |
| macOS core RSS | **159.8 MiB** at that checkpoint; excludes webview subprocesses, not a peak-memory claim |
| macOS `.app` disk usage | **51.1 MiB** |
| Local macOS ZIP | **25.1 MiB** (26,295,552 bytes) |
| Linux arm64 production `.deb` | Approximately **30.8 MiB** |

## Targeted security review and remaining gates

An independent implementation review covered IPC trust boundaries, bundled executable selection, capabilities, lifecycle, backup files, clipboard and lock behavior. Confirmed defects were fixed: preserving an injected empty session store, killing the key-owning core for manual/idle lock, failing closed on Windows Job Object setup, preventing external webview navigation, and clearing owned clipboard contents on session/core failure. Final artifact inspection found no remaining confirmed high-impact defect; this is not the planned external human cryptographic audit.

The final shell/frontend exclude QA commands, notification injection, test canaries and development Python paths. Compiled Tauri features exclude devtools. Capabilities expose only narrow application commands and event subscription; bundle symlinks do not escape resources. Native lock hides the old window and navigates to a fresh login document before relying on renderer events.

Before full Phase 5 acceptance: run the six-target native CI, validate Windows ACLs/clipboard/WTS/power behavior, exercise actual macOS/Linux sleep and screen-lock delivery, and manually walk through native file pickers and attachment/backup saves. Windows x64/arm64, Linux x64 and Intel macOS packaged applications have not been built or executed in this session. The Intel shell cross-check is not a substitute for that.

Before Phase 6 distribution: Developer ID signing/notarization of every bundled native library, Windows signing/SmartScreen work, a distribution/update design, external human cryptographic audit, and platform acceptance testing. Clipboard history hints can be ignored, Linux clipboard ownership checks are content-based, and screen-capture exclusion has platform limitations. No claim of protection from OS compromise or same-user memory inspection is made.
