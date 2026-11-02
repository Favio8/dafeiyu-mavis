"""Native/offscreen Qt smoke using only our own widgets and an isolated profile."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4


def main() -> int:
    """Run pet startup or Mavis approval/history/stop exercises without OS input injection."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--offscreen", action="store_true")
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--profile-label", default="")
    args = parser.parse_args()
    import re
    if not re.fullmatch(r"[A-Za-z0-9 _\-\u4e00-\u9fff]{0,40}", args.profile_label):
        parser.error("profile label must be a simple local directory label")
    import faulthandler
    faulthandler.dump_traceback_later(25, repeat=False, exit=True)
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    run = ("baseline" if args.baseline else "mavis") + f"-{args.scale:g}-" + uuid4().hex[:8]
    evidence = root / ".scratch/m0-m1/evidence" / run
    profile = root / ".scratch/m0-m1/profiles" / (args.profile_label + run)
    evidence.mkdir(parents=True)
    profile.mkdir(parents=True)
    for key in ("APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOME", "TEMP", "TMP"):
        os.environ[key] = str(profile)
    os.environ.update(ANONYMIZED_TELEMETRY="false", PYTHONUTF8="1", QT_SCALE_FACTOR=str(args.scale))
    os.environ.pop("QT_QPA_PLATFORM", None)
    if args.offscreen:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    if not args.baseline:
        os.environ.update(DAFEIYU_MAVIS="1", MAVIS_TEST_MODE="1", MAVIS_DATA_HOME=str(profile))
    else:
        os.environ.pop("DAFEIYU_MAVIS", None)
    from pet.qt_plugin_sanitizer import sanitize_plugin_path
    sanitize_plugin_path()
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QScrollArea
    from pet import app as pet_app
    from pet.multi_window_shared import presentation_targets
    import psutil
    start = time.monotonic()
    process = psutil.Process()
    initial_cpu = process.cpu_times()
    report = {"run": run, "platform": "offscreen" if args.offscreen else "native Windows", "scale_factor": args.scale,
              "profile": str(profile.relative_to(root)), "checks": {}, "heartbeat_ms": []}
    report["interaction"] = "Qt QAbstractButton.click on own widgets; no OS mouse injection or physical click claim"
    phase = [0]
    last_tick = [time.monotonic()]
    deadline = start + 90
    owned = {}
    frame_hashes = []
    original_start = pet_app.AppShell.start

    def wrapped_start(shell):
        original_start(shell)
        owned["shell"] = shell
        report["startup_to_shell_ms"] = (time.monotonic() - start) * 1000
        timer = QTimer(shell.app)
        timer.setInterval(50)
        owned["timer"] = timer
        timer.timeout.connect(tick)
        timer.start()
    pet_app.AppShell.start = wrapped_start
    # Baseline calls the original entry but excludes unrelated user-machine
    # housekeeping. These exclusions are explicit evidence, not a vanilla-install claim.
    pet_app._cleanup_stale_runtime_dirs = lambda: None
    pet_app.autostart_mod.cleanup_stale_entries = lambda: 0
    report["excluded_housekeeping"] = ["stale temporary directory deletion", "autostart registry cleanup"]

    def tick():
        # Upstream shutdown pumps Qt events while releasing decoders. Stop the
        # probe timer before quit, otherwise this callback re-enters and overwrites
        # the already-measured cancellation latency (and repeatedly reopens UI).
        if phase[0] == 7:
            return
        now = time.monotonic()
        report["heartbeat_ms"].append(round((now - last_tick[0]) * 1000, 3))
        last_tick[0] = now
        app = QApplication.instance()
        if now > deadline:
            report["error"] = "SMOKE_TIMEOUT"
            phase[0] = 7
            owned["timer"].stop()
            app.quit()
            return
        shell = owned["shell"]
        if args.baseline:
            if now - start < 6:
                return
            widgets = [w for w in app.topLevelWidgets() if w.isVisible()]
            report["checks"]["visible_owned_widgets"] = [type(w).__name__ for w in widgets]
            report["checks"]["tray_visible"] = bool(shell.tray and shell.tray.isVisible())
            for index, widget in enumerate(widgets):
                pixmap = widget.grab()
                pixmap.save(str(evidence / f"own-window-{index}.png"))
                if type(widget).__name__ == "ShellOverlayWindow":
                    import hashlib
                    from PySide6.QtGui import QImage
                    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
                    data = bytes(image.constBits())
                    report["checks"]["nontransparent_pixels"] = sum(alpha > 0 for alpha in data[3::4])
                    frame_hashes.append(hashlib.sha256(data).hexdigest())
            report["checks"]["presentation_targets"] = len(presentation_targets(shell))
            if len(frame_hashes) < 4:
                return
            report["checks"]["distinct_frames"] = len(set(frame_hashes))
            if not report["checks"].get("nontransparent_pixels") or len(set(frame_hashes)) < 2:
                report["error"] = "ANIMATION_NOT_OBSERVED"
            phase[0] = 7
            owned["timer"].stop()
            app.quit()
            return
        bridge = getattr(shell, "mavis", None)
        if not bridge or not bridge.window.latest:
            return
        window = bridge.window
        task = window.latest["task"]
        if phase[0] == 0:
            report["checks"]["hotkey_registered"] = bridge.hotkey.registered
            window.grab().save(str(evidence / "overview.png"))
            bridge.controller.submit("exercise")
            phase[0] = 1
        elif phase[0] == 1 and task and task["status"] == "WAITING_APPROVAL":
            window.resize(720, 540)
            phase[0] = 2
        elif phase[0] == 2:
            for area in window.stack.widget(0).findChildren(QScrollArea):
                area.ensureWidgetVisible(window.allow)
            window.grab().save(str(evidence / "approval-720.png"))
            report["checks"]["approval_button_reachable"] = window.rect().contains(window.allow.mapTo(window, window.allow.rect().center()))
            report["checks"]["stop_button_reachable"] = window.rect().contains(window.stop_button.mapTo(window, window.stop_button.rect().center()))
            window.allow.click()
            phase[0] = 3
        elif phase[0] == 3 and task and task["status"] == "SUCCEEDED" and window.history.topLevelItemCount():
            report["checks"]["fixture_verified"] = task["verification_status"] == "passed" and task["mode"] == "test"
            window.resize(1040, 720)
            window.nav.setCurrentRow(1)
            window.history.setCurrentItem(window.history.topLevelItem(0))
            phase[0] = 4
        elif phase[0] == 4 and window.detail.toPlainText():
            window.grab().save(str(evidence / "history.png"))
            report["checks"]["committed_history"] = "验证完成" in window.detail.toPlainText()
            window.nav.setCurrentRow(0)
            bridge.controller.submit("hang")
            phase[0] = 5
        elif phase[0] == 5 and task and task["status"] == "EXECUTING":
            owned["stop_at"] = time.monotonic()
            window.stop_button.click()
            report["checks"]["stop_latch_set_in_button_handler"] = bridge.stop.event.is_set()
            phase[0] = 6
        elif phase[0] == 6 and task and task["status"] == "CANCELLED":
            report["checks"]["cancel_visible_ms"] = (time.monotonic() - owned["stop_at"]) * 1000
            report["checks"]["stop_latch_and_terminate_ms"] = bridge.stop.last_stop_ms
            report["checks"]["hung_worker_exited"] = bridge.controller.worker.process.poll() is not None
            window.grab().save(str(evidence / "stopped.png"))
            window.close()
            report["checks"]["close_hides"] = not window.isVisible()
            bridge.show()
            report["checks"]["tray_restore"] = window.isVisible()
            phase[0] = 7
            owned["timer"].stop()
            app.quit()

    code = pet_app.main(["mavis-smoke"], enable_chat=False)
    faulthandler.cancel_dump_traceback_later()
    report["exit_code"] = code
    report["elapsed_s"] = time.monotonic() - start
    report["rss_mib"] = process.memory_info().rss / 1024**2
    cpu = process.cpu_times()
    report["cpu_seconds"] = cpu.user + cpu.system - initial_cpu.user - initial_cpu.system
    report["note"] = "One short startup sample; not a steady-state/performance acceptance or physical hotkey test. No other windows captured."
    (evidence / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "heartbeat_ms"}, ensure_ascii=False, indent=2))
    print("evidence=" + str(evidence))
    return 1 if "error" in report else code


if __name__ == "__main__":
    raise SystemExit(main())
