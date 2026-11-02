"""User-assisted physical hotkey test. Never synthesizes a hotkey or desktop input."""
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from assistant.stop import StopController, EmergencyHotkey
from assistant.ipc import WorkerSupervisor


def main() -> int:
    """Show readiness, await the user's key, and save only timing/process metadata."""
    import psutil
    from pet.qt_plugin_sanitizer import sanitize_plugin_path
    sanitize_plugin_path()
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget
    app = QApplication([])
    window = QWidget()
    window.setWindowTitle("Mavis 物理急停验证")
    window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    window.setMinimumSize(560, 220)
    window.setStyleSheet("QWidget {background:#F7F9FC;color:#172033;font:16px 'Microsoft YaHei UI';} QPushButton{padding:12px;}")
    layout = QVBoxLayout(window)
    label = QLabel("正在启动专用测试 worker…")
    label.setWordWrap(True)
    layout.addWidget(label)
    cancel = QPushButton("取消测试（不记为通过）")
    cancel.clicked.connect(app.quit)
    layout.addWidget(cancel)
    stop = StopController()
    hotkey = EmergencyHotkey(stop)
    worker = WorkerSupervisor(stop.event, test_mode=True)
    stop.own(worker)
    report = {"passed":False, "reason":"USER_CANCEL_OR_TIMEOUT", "injected_input":False}
    began, armed = time.monotonic(), [False]
    if not hotkey.start():
        raise SystemExit(hotkey.error)
    worker.start()
    timer = QTimer()
    timer.setInterval(50)
    def tick():
        if time.monotonic() - began > 300:
            app.quit()
        elif stop.last_stop_ms is not None and not armed[0]:
            report.update(reason="HOTKEY_BEFORE_WORKER_READY", handler_ms=stop.last_stop_ms)
            app.quit()
        elif worker.ready.is_set() and not armed[0]:
            worker.send("hang")
            armed[0] = True
            label.setText("已就绪。请现在按一次 Ctrl+Alt+F12。\n\n只停止专用测试 worker；不会修改文件或关闭其他程序。")
        elif armed[0] and stop.last_stop_ms is not None:
            report.update(passed=worker.process.poll() is not None and not psutil.pid_exists(worker.peer_pid),
                          reason="HOTKEY_RECEIVED", handler_ms=stop.last_stop_ms)
            timer.stop()
            app.quit()
    timer.timeout.connect(tick)
    timer.start()
    window.show()
    window.raise_()
    window.activateWindow()
    try:
        app.exec()
    finally:
        report["hotkey_received"] = stop.last_stop_ms is not None
        timer.stop()
        worker.close()
        hotkey.close()
    output = ROOT / ".scratch/m2/evidence" / ("physical-stop-" + str(time.time_ns()) + ".json")
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
