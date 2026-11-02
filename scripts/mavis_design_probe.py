"""Native Qt visual QA in a fresh profile; no API, OS input, or user screenshots."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", type=float, default=1)
    args = parser.parse_args()
    import os
    os.environ["QT_SCALE_FACTOR"] = str(args.scale)
    os.environ.pop("QT_QPA_PLATFORM", None)
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from pet.qt_plugin_sanitizer import sanitize_plugin_path
    sanitize_plugin_path()
    from PySide6.QtCore import QEventLoop, QTimer, QPoint
    from PySide6.QtWidgets import QApplication, QScrollArea, QWidget, QVBoxLayout, QLabel
    from PySide6.QtGui import QPainter
    from assistant.controller import Controller
    from assistant.stop import StopController
    from assistant.ui import ControlCenter
    from assistant.execution_overlay import ExecutionOverlay

    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    output = root / ".scratch/ui-design" / str(time.time_ns())
    output.mkdir(parents=True)
    report = {"platform": app.platformName(), "scale_factor": args.scale, "screens": [], "checks": {}, "pages": []}
    for screen in app.screens():
        report["screens"].append({"geometry": screen.geometry().getRect(), "dpr": screen.devicePixelRatio(), "logical_dpi": screen.logicalDotsPerInch()})

    def pump(ms=100):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def wait(predicate):
        deadline = time.monotonic() + 10
        while not predicate() and time.monotonic() < deadline:
            pump(25)
        if not predicate():
            raise RuntimeError("probe state timeout")

    stop = StopController()
    controller = Controller(output / "profile", stop, test_mode=True)
    controller.start()
    live_controller = None
    windows = []
    overlay = None
    try:
        wait(controller.ready.is_set)
        # Actual test-mode task/approval records; never fabricate usage or successes.
        controller.submit("exercise")
        wait(lambda: controller.service.task and controller.service.task.status == "WAITING_APPROVAL")
        for dark in (False, True):
            window = ControlCenter(controller, stop, SimpleNamespace(registered=False, error="视觉探针未注册热键"), dark=dark)
            windows.append(window)
            window.show()
            controller.submit("refresh")
            wait(lambda: window.latest is not None)
            for width in (1100, 720):
                window.resize(width, 760 if width == 1100 else 580)
                for page in range(window.nav.count()):
                    window.nav.setCurrentRow(page)
                    pump()
                    areas = window.stack.currentWidget().findChildren(QScrollArea)
                    no_horizontal = all(a.horizontalScrollBar().maximum() == 0 for a in areas)
                    reachable_stop = window.rect().contains(window.stop_button.mapTo(window, window.stop_button.rect().center()))
                    name = f"{'dark' if dark else 'light'}-{width}-{page}.png"
                    window.grab().save(str(output / name))
                    report["pages"].append({"file": name, "requested_width": width, "actual_width": window.width(), "no_horizontal_scroll": no_horizontal, "stop_reachable": reachable_stop})
            window.hide()
        report["checks"]["all_pages_fit"] = all(p["no_horizontal_scroll"] and p["stop_reachable"] and p["actual_width"] == p["requested_width"] for p in report["pages"])
        report["checks"]["all_navigation_icons"] = all(not windows[0].nav.item(i).icon().isNull() for i in range(8))

        live_controller = Controller(output / "profile-live", stop)
        live_window = ControlCenter(live_controller, stop, SimpleNamespace(registered=False, error="视觉探针未注册热键"))
        windows.append(live_window)
        live_controller.start()
        live_window.resize(1100, 760)
        live_window.show()
        wait(lambda: live_window.latest is not None)
        pump()
        live_window.grab().save(str(output / "live-overview-1100.png"))
        live_window.hide()

        # Own blank fixture for foreground/hit-test queries, not another app's data.
        fixture = QWidget()
        fixture.setWindowTitle("Mavis 流光验证 · 不操作电脑")
        fixture.setStyleSheet("background:#F7F7F8;color:#192130;font-size:26px;")
        fixture.setGeometry(app.primaryScreen().geometry())
        box = QVBoxLayout(fixture)
        title = QLabel("Mavis\n边缘流光预览 · 不操作电脑")
        title.setWordWrap(True)
        box.addWidget(title)
        fixture.show()
        fixture.activateWindow()
        pump(150)
        overlay = ExecutionOverlay(controller.control_activity, stop.event, app)
        foreground = None
        if sys.platform == "win32":
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.GetForegroundWindow.restype = wintypes.HWND
            user32.WindowFromPoint.argtypes = [wintypes.POINT]
            user32.WindowFromPoint.restype = wintypes.HWND
            user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.GetWindowLongW.restype = ctypes.c_long
            foreground = user32.GetForegroundWindow()
        overlay.preview()
        pump(150)
        primary = overlay.windows[0]
        first = primary.grab()
        first.save(str(output / "edge-transparent.png"))
        # Compose only images of our own two windows, retaining original alpha.
        composition = fixture.grab()
        painter = QPainter(composition)
        painter.drawPixmap(QPoint(0, 0), first)
        painter.end()
        composition.save(str(output / "edge-preview.png"))
        pump(250)
        second = primary.grab().toImage()
        report["checks"]["motion_preference"] = overlay._motion
        report["checks"]["frames_differ"] = first.toImage() != second
        report["checks"]["center_alpha_zero"] = first.toImage().pixelColor(first.width() // 2, first.height() // 2).alpha() == 0
        if sys.platform == "win32":
            report["checks"]["foreground_unchanged"] = foreground == user32.GetForegroundWindow()
            handles = [int(w.winId()) for w in overlay.windows]
            styles = [user32.GetWindowLongW(h, -20) for h in handles]
            report["checks"]["native_input_transparent"] = all(s & 0x20 and s & 0x08000000 and s & 0x80000 for s in styles)
            g = primary.geometry()
            dpr = primary.devicePixelRatioF()
            # Native hit testing uses physical pixels; probe documents the tested DPR.
            point = wintypes.POINT(round((g.x() + g.width() / 2) * dpr), round((g.y() + 4) * dpr))
            report["checks"]["edge_hit_skips_overlay"] = user32.WindowFromPoint(point) not in handles
        start = time.monotonic()
        stop.trip()
        wait(lambda: not any(w.isVisible() for w in overlay.windows))
        report["checks"]["stop_to_hidden_ms"] = round((time.monotonic() - start) * 1000, 2)
        report["checks"]["stop_latch"] = stop.event.is_set()
        fixture.close()
    finally:
        if overlay:
            overlay.close()
        controller.close()
        if live_controller:
            live_controller.close()
        for window in windows:
            window.exiting = True
            window.close()
    report["limitations"] = ["Qt button/state exercises and native read-only hit tests; no physical mouse/key injection", "Overlay preview is not proof of a live computer-use task", "Qt scale factor is not a mixed-monitor system-DPI acceptance", "No macOS/Linux real-host validation"]
    required = ["all_pages_fit", "all_navigation_icons", "center_alpha_zero", "stop_latch"]
    if sys.platform == "win32":
        required += ["foreground_unchanged", "native_input_transparent", "edge_hit_skips_overlay"]
    report["passed"] = all(report["checks"].get(key) for key in required)
    (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "checks": report["checks"], "evidence": str(output)}, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
