"""User-started GUI pilot: a real foreground gesture, no focus-stealing workaround."""
import queue
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from assistant.stop import StopController
from mavis_gui_probe import main as run_probe


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume-test-window", required=True)
    args = parser.parse_args()
    from pet.qt_plugin_sanitizer import sanitize_plugin_path
    sanitize_plugin_path()
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget
    app = QApplication([])
    window = QWidget()
    window.setWindowTitle("Mavis 真实 GUI 验证")
    window.resize(580, 240)
    window.setStyleSheet("QWidget {background:#F7F9FC;color:#172033;font:16px 'Microsoft YaHei UI';} QPushButton {padding:12px;}")
    layout = QVBoxLayout(window)
    label = QLabel("点击开始后，在之前新开的空白测试记事本中输入测试文本。\n\n请保持记事本前台几秒；Ctrl+Alt+F12 可立即停止。不会保存文件。")
    label.setWordWrap(True)
    layout.addWidget(label)
    start = QPushButton("开始真实 GUI 测试")
    end = QPushButton("停止并关闭")
    layout.addWidget(start)
    layout.addWidget(end)
    stop = StopController()
    results = queue.Queue()
    outcome = [1]
    def work():
        import comtypes
        comtypes.CoInitialize()
        try:
            # Only the recorded pilot window may be reused; no history actions or grants replayed.
            code = run_probe(["--resume-test-window", args.resume_test_window], stop)
            results.put(code)
        except (Exception, SystemExit) as exc:
            print("GUI_PILOT_ERROR=" + (str(exc) if isinstance(exc,SystemExit) else type(exc).__name__), flush=True)
            results.put(1)
        finally:
            comtypes.CoUninitialize()
    def begin():
        print("HUMAN_SETUP=local_start_button", flush=True)
        start.setEnabled(False)
        label.setText("测试进行中，请保持记事本前台。每个字符都经过许可与独立读取验证。")
        threading.Thread(target=work, daemon=True, name="mavis-gui-pilot").start()
    start.clicked.connect(begin)
    end.clicked.connect(app.quit)
    def poll():
        try:
            code = results.get_nowait()
        except queue.Empty:
            return
        outcome[0] = code
        timer.stop()
        label.setText("测试通过，结果已记录。未保存任何文件。" if code == 0 else "测试已停止，未宣称成功。失败原因已记录。")
        QTimer.singleShot(1500, app.quit)
    timer = QTimer()
    timer.setInterval(100)
    timer.timeout.connect(poll)
    timer.start()
    QTimer.singleShot(300000, app.quit)
    app.aboutToQuit.connect(stop.trip)
    window.show()
    window.raise_()
    window.activateWindow()
    app.exec()
    return outcome[0]


if __name__ == "__main__":
    raise SystemExit(main())
