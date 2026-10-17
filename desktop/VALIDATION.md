# Desktop alpha validation — 2026-10-17

The macOS Apple Silicon alpha has been copied to the user's Applications folder and tested independently of the build tree. The maintainer confirmed physical screen-lock, sleep/wake and native backup save/import behavior using synthetic data. [Draft PR #58](https://github.com/mr-grj/ciphermoth/pull/58) runs the real Phase 5 implementation on six native targets. Nothing has been merged or released, and the workflow uploads evidence rather than installers. This remains an unsigned development alpha, unsuitable for important real passwords.

## Source and artifacts

- Branch: `phase5-desktop-alpha`; isolated worktree: `~/Projects/ciphermoth-desktop` (moved with `git worktree move`, preserving commits, local files and build artifacts).
- Verified base: latest local/GitHub master and v3.0.0 release commit `12946f3cc4b6333d27753d9b101b67b8d3fe8649` at the start of implementation.
- Reused spike: `experiment/desktop-feasibility` at `9d3a4ea`. The main checkout, experimental worktree and private planning reports were preserved.
- Commits use the existing maintainer identity, Alexandru Grajdeanu `<grajdeanu.alex@gmail.com>`, as author and committer. See `git log 12946f3..HEAD` for focused implementation commits.
- Installed macOS app: `~/Applications/CipherMoth Alpha.app`.
- Local archive: `/private/tmp/CipherMoth-Alpha-final-macos-arm64.zip` (not a published installer).
- Installed production shell SHA256: `d4895958636a0064dc3af2174ed7da2137eb74929c27fadad2f67f868559bac7`.

Run `open "$HOME/Applications/CipherMoth Alpha.app"`, create a synthetic vault or unlock the existing synthetic alpha vault, and add a test password. Log out or press Command+Shift+L to lock; quit and reopen to unlock the persisted vault. The app uses `com.ciphermoth.desktop.alpha` and stores its data under `~/Library/Application Support/com.ciphermoth.desktop.alpha/`. It does not resolve Python on PATH or use the Docker/spike data location. Copy the complete bundle, never its executable alone.

This is an unsigned/local development artifact. `codesign` reports a linker ad-hoc signature, no TeamIdentifier, no sealed resources, and no hardened-runtime signing flag. The Tauri configuration requests hardened runtime for future signing; it does not establish enforcement in this unsigned bundle. No library-validation bypass entitlement was added.

The relocated development environment passed `make check` and a fresh source-mode vault creation/unlock test. Virtual-environment script paths were repaired and Tauri permission caches regenerated; the installed application continued running independently of the moved source tree.

## Implemented behavior

The real v3 Python core runs as a PyInstaller onedir sidecar behind private framed stdin/stdout IPC, with the actual FastAPI lifespan and SQLite storage layer. No HTTP server runs. Python owns the keys and sessions. React receives opaque session tokens held in memory; Rust carries requests without implementing vault cryptography. The shared HTTP deployment remains supported.

The existing React vault supports creation/unlock, entry CRUD/search/organization, notes, TOTP, history, Trash, attachments, password rotation and encrypted backups through its platform adapter. Native clipboard timers, file dialogs, external-link allowlisting, startup/retry handling, manual/idle locking and OS lock handlers are implemented. Startup compatibility checks, bounded crash recovery and platform process cleanup were ported from the spike. Source development launches Vite and the dedicated Python venv without freezing after edits; that launch was verified locally.

Backups stream ciphertext directly between an OS-authorized file and the existing Python backup endpoints. The renderer receives only a single-use file grant. The installed native QA app exports and restores a 26,217,209-byte backup containing five binary attachments, then compares every restored byte. It calls the same Rust file-transfer function through a QA-only fixed destination; the real Save/Open panels were separately confirmed manually. Cancellation, simulated disk-full failure and destination races are tested; existing files are never overwritten. Killing the frozen core during export produced no completed backup; killing it after import began writing rolled back the destination after restart. No plaintext staging was observed. An additional installed production-core test exported and restored 1,069,609,948 bytes (about 1,020 MiB), with 41 entries and all 204 attachment hashes verified. It rejected a write exceeding complete-backup capacity and a sparse 1 GiB + 1 byte import. This near-limit check used framed native-file IPC directly, not the Tauri renderer; exact 1 GiB and near-limit GUI timing remain untested. Hard-link publication requires a supporting filesystem; a forced OS kill can leave an encrypted `.partial` file. See [README.md](README.md).

## Automated results

| Check | Result |
| --- | --- |
| Shared backend suite | **783 passed**, 2 deselected; 348.28 s |
| Shared frontend suite | **139 passed**, 11 files |
| Repository `make check` | Passed; 6 existing React refresh warnings, no errors |
| Desktop Python lint/format | Passed |
| macOS packaged desktop core suite | **30 passed**, 55.99 s |
| Linux packaged desktop core suites | **29 passed, 1 skipped** on each architecture |
| Frozen v3 cryptographic vectors | **27 passed** per target; see native matrix below |
| Actual packaged SQLite | **3.53.1** in all six packaged runtimes |
| Python runtime | **3.13.15** in all six packaged runtimes |
| Rust tests | **8 passed** on macOS arm64; native CI also runs the suite |
| Rust formatting / Clippy with warnings denied | Passed locally; every native CI job runs formatting and Clippy |
| Intel macOS Rust shell cross-check | `cargo check --target x86_64-apple-darwin` passed |
| Existing Docker/server smoke suite | **26 checks passed** against locally built backend/frontend images |
| GitHub six-target desktop CI | **All six targets passed**; [run 39020791230](https://github.com/mr-grj/ciphermoth/actions/runs/39020791230) |

The core suite exercises wrong/correct unlock, persistence, ciphertext metadata/canaries, CRUD/notes/TOTP/Trash/history, binary attachments, rotation/revocation, large backup restore, idle expiry, malformed/oversized frames, cancellation, shutdown, one-session enforcement, file permissions, and damaged/unsupported vault refusal. It uses real framed desktop transport rather than HTTP sockets. The Linux per-process socket assertion is skipped because process dump protection prevents inspection; the native harness separately checks no new listening socket in the disposable runner/container network namespace. Native Linux x86_64 vault operations and frozen vectors completed without reproducing the historical Argon2id deadlock.

The Docker smoke run used isolated `cm-phase5-desktop-*` projects and synthetic volumes. Its local `phase5-local` image tags were not pushed. The Linux native container `cm-phase5-linux-arm64-20261016` was stopped after verification. No existing installation or user vault was migrated or modified.

## Six-target native CI

[Final native run](https://github.com/mr-grj/ciphermoth/actions/runs/39020791230) passed all six targets on implementation commit `ab0c9e53437afe25c79be36195d48c345f5af99f`. The later handoff commit changes desktop documentation only. The standard PR CI also passed backend/frontend checks and Docker/Compose installation on amd64 and arm64.

| Target | Production build / installed QA | Core tests | Python / SQLite | Measured installer |
| --- | --- | --- | --- | --- |
| macOS arm64 | Passed / passed | 30 passed | 3.13.15 / 3.53.1 | 26.4 MiB QA `.dmg` |
| macOS x86_64 | Passed / passed | 30 passed | 3.13.15 / 3.53.1 | 26.7 MiB QA `.dmg` |
| Windows x64 | Passed / passed | 30 passed | 3.13.15 / 3.53.1 | 21.7 MiB production `.exe` |
| Windows arm64 | Passed / passed | 30 passed | 3.13.15 / 3.53.1 | 21.1 MiB production `.exe` |
| Linux x64 | Passed / passed | 29 passed, 1 skipped | 3.13.15 / 3.53.1 | 33.2 MiB production `.deb` |
| Linux arm64 | Passed / passed | 29 passed, 1 skipped | 3.13.15 / 3.53.1 | 31.2 MiB production `.deb` |

Every target passed 27 frozen cryptographic vectors, the bounded framed-core suite, eight Rust tests, formatting/Clippy, frontend tests, and the installed native workflow. The latter covers real vault creation/unlock, CRUD/organization, persistence, binary attachments, a 26,217,209-byte backup restoration, blocked-renderer idle expiry, rotation, capability rejection, core termination/restart and shell exit cleanup. macOS copies the complete QA bundle before launch; Windows installs NSIS and Linux installs the Debian package. Production artifacts are built separately; automation adds QA-only commands to a separate artifact, never to the production capability set.

macOS CI retains the QA DMG size after the second bundle build; the local production Apple Silicon app/ZIP sizes are recorded below. These artifacts were built for validation and were not published. GitHub retains evidence for 14 days; downloaded copies are under `/private/tmp/ciphermoth-ci-final/`.

Earlier failures were resolved rather than excluded: Windows vector fixtures needed explicit UTF-8; UI/clipboard acceptance waits needed completion acknowledgements; a 24 MiB malformed-frame parameter was being repeated in pytest output and now has a short identifier. The prior Intel installed-app run aborted during lock/reload, consistent with the macOS release-profile defect reproduced locally; the corrected Intel run passes. These reporting/timing defects are separate from the actual application abort. No native Linux x86_64 Argon2id deadlock reproduced.

## Native application evidence

The QA artifact runs the real React forms inside WKWebView on macOS, WebView2 on Windows and WebKitGTK on Linux, with the packaged v3 core. It creates the vault and first password through the UI, retrieves it through native IPC, rejects ungranted capabilities, exercises request timeout, locks/re-unlocks, kills/restarts the core, closes/reopens the app and checks for orphan processes. These are native application tests, not browser Playwright tests.

macOS automation verifies clipboard expiry while Finder is focused, preservation of replacement clipboard text, owned-secret clearing on normal quit, and invocation through the Cocoa workspace-sleep handler. Separately, the maintainer reported successful physical Control–Command–Q screen-lock and Apple-menu Sleep/wake tests, and explicitly confirmed that Command–H past the configured hidden timeout required the master password on return. These are manual acceptance results, not notification-injection evidence. User switching remains untested. Linux CI exercises the native lock callback, not delivery from a physical desktop/logind session. Xvfb is not proof of normal Wayland behavior. No sandbox-disable option is built into the application.

Native Save/Open-dialog automation is unavailable because macOS Accessibility is disabled. No privacy settings were changed. The maintainer instead tested Backup → native Save → Import → native Open → backup password, and confirmed that the dialogs and completion messages worked. The opt-in automation remains available on an authorized test host.

Synthetic password, entry-name and raw-key canaries were absent from the macOS QA data/log tree. This is a scoped leakage check, not a forensic scan of the entire OS. Socket inspection found no backend listener; the shipped UI/CSP and sidecar contain no normal-operation network dependency. This is not a packet-capture claim about unrelated OS services.

Local evidence, retained outside Git:

- `/private/tmp/ciphermoth-native-final-20261017-h/results.json` — installed macOS QA app, full transport and lifecycle run.
- `/private/tmp/ciphermoth-phase5-core-bounded-tests.log` — production frozen core suite.
- `/private/tmp/ciphermoth-phase5-final-test.log`, `/private/tmp/ciphermoth-phase5-last-check.log` — backend/frontend suites and repository checks.
- `/private/tmp/ciphermoth-phase5-server-smoke.log` — isolated Docker/server regression run.
- `/private/tmp/ciphermoth-backup-boundary-20261017/results.json` — near-limit backup, all attachment hashes, capacity/oversize rejection and operation resource measurements.
- `/private/tmp/ciphermoth-backup-crash-final/result.json` — actual frozen-core export/import crash checks.
- `/private/tmp/ciphermoth-phase5-installed-artifact.json`, `/private/tmp/ciphermoth-phase5-final-startup.json` — production bundle audit and startup samples.

## Performance snapshot

Host: Apple M3 Max, 14 CPU cores, 96 GiB RAM, macOS 26.6.2. These are development-machine observations, not release benchmarks.

| Measurement | Result / scope |
| --- | --- |
| Installed production core spawn to ready | Median **0.325 s**, five fresh synthetic databases; first 0.708 s, subsequent 0.322–0.328 s; OS caches were not flushed |
| Installed native QA app launch to interactive screen | **0.682 s** first launch, **0.630 s** reopen, measured by host; QA uses the production UI/core with additional test hooks |
| Native shell-observed initial core readiness | **0.367 s**, reopen **0.363 s** |
| Tauri backup export/import and byte verification | **7.393 s**, 26,217,209-byte backup |
| Full initial acceptance scenario | **104.157 s**, including deliberate 35-second JavaScript blocking, clipboard waits, multiple lock/unlock and rotation cycles; not startup latency |
| macOS shell / core RSS | **113.2 / 177.2 MiB** at final scenario checkpoint |
| Total sampled RSS peak | **751.3 MiB** across the full acceptance scenario, including shell/core descendants and newly launched WebKit XPC processes; shared pages can be double-counted |
| macOS `.app` disk usage | **52.3 MiB** on disk; 54,637,854 logical bytes |
| Local macOS ZIP | **25.5 MiB** (26,712,896 bytes) |
| Packaged-core near-limit backup export / import | **2.098 / 3.625 s**, 1,069,609,948 bytes; excludes subsequent attachment hash verification |
| Core RSS during near-limit export / import | **517.2 / 207.3 MiB** sampled peaks; CPU **2.725 / 3.563 s** |
| Packaged-core unlock of near-limit vault | **0.157 s**, **159.0 MiB** sampled peak RSS, **0.568 s** CPU |

## Targeted security review and remaining gates

An independent implementation review covered IPC trust boundaries, bundled executable selection, capabilities, lifecycle, backup files, clipboard and lock behavior. The original implementation fixed injected-session-store handling, core termination on lock, Windows Job Object failure, external navigation and owned-clipboard clearing. Finalization additionally fixed:

- Unbounded outbound queue growth when a sidecar or shell stops reading. Both directions now have bounded queues; unsent timed-out requests are discarded and cancellation failure terminates the core.
- Native file selections surviving a lock. Lock invalidates grants and pending attachment saves; a completed picker cannot write plaintext after lock.
- Reliance on JavaScript timing for key destruction. A native watchdog consumes trusted core expiry metadata and enforces idle/hidden policy while the renderer is blocked. The installed app test blocks JavaScript for 35 seconds and observes core termination at the configured 30-second deadline.
- Windows vector validation using the machine's legacy text encoding. Vector JSON is explicitly UTF-8, with a cp1252 regression test. No crypto primitive or format changed.
- A release-only macOS lock/reload abort, reproduced twice in the installed QA app. The release profile used `panic = "abort"`, which disables the Objective-C exception catcher used by Wry when navigation cancels an outstanding IPC response. The profile now uses `unwind`, as required by [objc2's exception-handling contract](https://docs.rs/objc2/latest/objc2/exception/fn.catch.html). Both crashed synthetic vaults reopened and retained their expected entries. Two complete installed macOS runs passed with the corrected profile, including repeated lock/reload and normal quit.

The final independent source review found no remaining demonstrated desktop implementation blocker. This is not an external human cryptographic audit. Once a mutation has reached the core, a timeout alone cannot promise rollback; callers must refresh the resulting state.

The final shell/frontend exclude QA commands, notification injection, test canaries and development Python paths. Compiled Tauri features exclude devtools. Capabilities expose only narrow application commands and event subscription; bundle symlinks do not escape resources. Native lock hides the old window and navigates to a fresh login document before relying on renderer events.

Phase 5 implementation, local validation and the six-target native matrix are complete for a development alpha. Physical Windows WTS/power and Linux desktop sleep/lock delivery, Windows inherited ACL behavior, macOS user switching, exact 1 GiB and near-limit GUI backup behavior and unsupported filesystems remain explicit acceptance limits. The macOS screen-lock/sleep and backup-picker manual checks are complete; they do not establish another platform's behavior.

Before Phase 6 distribution: Developer ID signing/notarization of every bundled native library, Windows signing/SmartScreen work, a distribution/update design, external human cryptographic audit, and platform acceptance testing. Clipboard history hints can be ignored, Linux clipboard ownership checks are content-based, and screen-capture exclusion has platform limitations. No claim of protection from OS compromise or same-user memory inspection is made.
