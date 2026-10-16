"""Exercise the QA .app in a native webview, its real UI, and process lifecycle.

Uses only synthetic data in a required absolute directory. No backend listener,
no browser substitution, no production self-test command.
"""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

import psutil


def wait_report(path, process, timeout=60, dialogs=False):
    deadline = time.monotonic() + timeout
    stages = set()
    while time.monotonic() < deadline:
        if path.exists():
            report = json.loads(path.read_text())
            stage = report.get("stage")
            if stage and stage not in stages and __import__("sys").platform == "darwin":
                stages.add(stage)
                if stage == "clipboard_timeout":
                    assert (
                        subprocess.check_output(["pbpaste"]).decode()
                        == "Native-clipboard-canary"
                    )
                    subprocess.run(
                        ["osascript", "-e", 'tell application "Finder" to activate'],
                        check=True,
                    )
                    time.sleep(1.3)
                    assert subprocess.check_output(["pbpaste"]) == b"", (
                        "native clipboard did not clear in background"
                    )
                elif stage == "clipboard_replaced":
                    subprocess.run(["pbcopy"], input=b"User replacement", check=True)
                    time.sleep(1.3)
                    assert (
                        subprocess.check_output(["pbpaste"]) == b"User replacement"
                    ), "clipboard replacement erased"
                elif stage in ("backup_save", "backup_open"):
                    assert dialogs, "Build dialog QA only with --dialogs on macOS"
                    # The OS picker authorizes the path; it never enters JS.
                    destination = path.parent / "ciphermoth-backup.cmbackup"
                    script = """on run argv
tell application id "com.ciphermoth.desktop.qa" to activate
delay 1
tell application "System Events"
    tell process "ciphermoth-desktop"
        set frontmost to true
        keystroke "g" using {command down, shift down}
        delay 0.5
        keystroke (item 1 of argv)
        key code 36
        delay 0.8
        key code 36
    end tell
end tell
end run"""
                    if stage == "backup_save":
                        destination.unlink(missing_ok=True)
                    subprocess.run(
                        ["osascript", "-e", script, str(destination)],
                        check=True,
                        timeout=15,
                    )
            if not stage:
                assert report.get("ok"), report
                return report
        if process.poll() is not None:
            raise RuntimeError(f"App exited {process.returncode}")
        time.sleep(0.1)
    raise TimeoutError("Native webview did not report")


def gone(pid):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not psutil.pid_exists(pid):
            return True
        try:
            if psutil.Process(pid).status() == psutil.STATUS_ZOMBIE:
                return True
        except psutil.NoSuchProcess:
            return True
        time.sleep(0.05)
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--dialogs", action="store_true")
    args = parser.parse_args()
    assert args.app.is_absolute() and args.root.is_absolute()
    args.root.mkdir(parents=True, exist_ok=True)
    report_path = args.root / "webview.json"
    report_path.unlink(missing_ok=True)
    env = {**os.environ, "CIPHERMOTH_QA_ROOT": str(args.root)}
    listeners = (
        {
            (str(c.family), str(c.type), str(c.laddr))
            for c in psutil.net_connections(kind="inet")
            if c.status == psutil.CONN_LISTEN
        }
        if __import__("sys").platform.startswith("linux")
        else set()
    )
    started = time.monotonic()
    with (args.root / "shell.log").open("wb") as log:
        app = subprocess.Popen([str(args.app)], env=env, stdout=log, stderr=log)
        try:
            first = wait_report(report_path, app, dialogs=args.dialogs)
            first["launch_to_ui_s"] = round(time.monotonic() - started, 3)
            core_pid = first["core"]["info"]["pid"]
            if __import__("sys").platform.startswith("linux"):
                current = {
                    (str(c.family), str(c.type), str(c.laddr))
                    for c in psutil.net_connections(kind="inet")
                    if c.status == psutil.CONN_LISTEN
                }
                assert not current - listeners, (
                    "new listening socket in isolated test namespace"
                )
            first["shell_rss"] = psutil.Process(app.pid).memory_info().rss
            first["core_rss"] = psutil.Process(core_pid).memory_info().rss
            if not __import__("sys").platform.startswith("linux"):
                assert not [
                    c
                    for c in psutil.Process(core_pid).net_connections()
                    if c.status == psutil.CONN_LISTEN
                ]
            report_path.unlink()
            psutil.Process(core_pid).kill()
            restarted = wait_report(report_path, app, dialogs=args.dialogs)
            assert restarted["core"]["generation"] > first["core"]["generation"]
            assert "retrieve password through native IPC" in restarted["checks"]
            new_core = restarted["core"]["info"]["pid"]
            app.kill()
            app.wait(10)
            assert gone(new_core), "orphaned core after shell SIGKILL"
            report_path.unlink()
            app = subprocess.Popen([str(args.app)], env=env, stdout=log, stderr=log)
            reopened = wait_report(report_path, app, dialogs=args.dialogs)
            assert not reopened["fresh"]
            core_pid = reopened["core"]["info"]["pid"]
            if __import__("sys").platform == "darwin":
                subprocess.run(
                    [
                        "osascript",
                        "-e",
                        'tell application id "com.ciphermoth.desktop.qa" to quit',
                    ],
                    check=True,
                    timeout=10,
                )
            else:
                app.terminate()
            app.wait(10)
            assert gone(core_pid), "orphaned core after quit"
            result = {
                "first": first,
                "crash_restart": restarted,
                "reopen": reopened,
                "orphan_checks": True,
            }
            (args.root / "results.json").write_text(json.dumps(result, indent=2))
            print(json.dumps(result, indent=2))
        finally:
            if app.poll() is None:
                app.kill()
                app.wait(10)


if __name__ == "__main__":
    main()
