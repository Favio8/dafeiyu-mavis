"""Real Qt event loop and controller thread, with isolated SQLite and private workers."""
from types import SimpleNamespace

from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from assistant.controller import Controller
from assistant.stop import StopController
from assistant.ui import ControlCenter


def until(predicate, timeout=10000):
    """Poll an observable state under a real Qt event loop with a bounded deadline."""
    if predicate():
        return
    loop = QEventLoop()
    poll, deadline = QTimer(), QTimer()
    poll.setInterval(10)
    poll.timeout.connect(lambda: loop.quit() if predicate() else None)
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    poll.start()
    deadline.start(timeout)
    loop.exec()
    poll.stop()
    deadline.stop()
    assert predicate(), "Qt state did not arrive before the bounded deadline"


def test_real_approval_history_navigation_and_stop(tmp_path):
    app = QApplication.instance() or QApplication([])
    stop = StopController()
    controller = Controller(tmp_path, stop, test_mode=True)
    window = ControlCenter(controller, stop, SimpleNamespace(registered=True, error=None))
    window.show()
    controller.start()
    try:
        until(lambda: window.latest is not None)
        assert window.history.topLevelItemCount() == 0
        QTest.mouseClick(window.exercise, Qt.MouseButton.LeftButton)
        until(lambda: window.allow.isEnabled())
        original = window.latest["task"]["id"]
        controller.submit("exercise")
        until(lambda: "已有活动任务" in window.notice.text())
        assert controller.worker.process.poll() is None  # second command cannot kill first worker
        assert window.latest["task"]["id"] == original
        QTest.mouseClick(window.allow, Qt.MouseButton.LeftButton)
        until(lambda: window.latest["task"]["status"] == "SUCCEEDED")
        window.nav.setCurrentRow(1)
        until(lambda: window.history.topLevelItemCount() > 0)
        window.history.setCurrentItem(window.history.topLevelItem(0))
        until(lambda: "验证完成" in window.detail.toPlainText())
        assert "已消耗" in window.detail.toPlainText()
        assert window.history.currentItem().text(2) == "文字"
        before_refresh = window.latest
        controller.submit("refresh")
        until(lambda: window.latest is not before_refresh)
        assert window.history.currentItem().data(0, Qt.ItemDataRole.UserRole) == original
        controller.submit("hang")
        until(lambda: window.latest["task"]["status"] == "EXECUTING" and controller.worker and controller.worker.ready.is_set())
        QTest.mouseClick(window.stop_button, Qt.MouseButton.LeftButton)
        until(lambda: window.latest["task"]["status"] == "CANCELLED")
        assert controller.worker.process.poll() is not None
        assert window.stop_button.isVisible()  # remains available while on history tab
        window.close()
        assert not window.isVisible() and controller.is_alive()
        controller.submit("reset")
        until(lambda: not window.latest["stopped"])
    finally:
        controller.close()
        window.exiting = True
        window.close()
    assert controller.closed.is_set() and not controller.is_alive()


def test_live_text_is_truthfully_unavailable_and_plain_text(tmp_path):
    app = QApplication.instance() or QApplication([])
    stop = StopController()
    controller = Controller(tmp_path, stop)
    window = ControlCenter(controller, stop, SimpleNamespace(registered=False, error="HOTKEY_UNAVAILABLE"))
    controller.start()
    try:
        until(lambda: window.latest is not None)
        controller.submit("record", "<img src=x>打开网页")
        until(lambda: window.latest["task"] is not None and window.latest["task"]["status"] == "FAILED")
        assert window.latest["task"]["status"] == "FAILED"
        assert window.latest["task"]["action_count"] == 0
        assert "未执行" in window.outcome.text()
        assert "HOTKEY_UNAVAILABLE" in window.notice.text()
        assert window.latest["task"]["mode"] == "live"
        controller.submit("exercise")
        until(lambda: "TEST_MODE_REQUIRED" in window.notice.text())
    finally:
        controller.close()
        window.exiting = True
        window.close()


def test_pause_and_replan_does_not_replay_approval(tmp_path):
    app = QApplication.instance() or QApplication([])
    stop = StopController()
    controller = Controller(tmp_path, stop, test_mode=True)
    window = ControlCenter(controller, stop, SimpleNamespace(registered=True, error=None))
    controller.start()
    try:
        until(lambda: window.latest is not None)
        controller.submit("exercise")
        until(lambda: window.allow.isEnabled())
        controller.submit("pause")
        until(lambda: window.latest["task"]["status"] == "PAUSED")
        assert not window.allow.isEnabled()
        controller.submit("resume")
        until(lambda: window.latest["task"]["status"] == "FAILED")
        assert window.latest["task"]["action_count"] == 0
    finally:
        controller.close()
        window.exiting = True
        window.close()
