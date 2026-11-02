"""Presentation must follow committed live execution without granting authority."""
from types import SimpleNamespace
import threading

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from assistant.presentation import ControlActivity
from assistant.execution_overlay import EdgeGlow, ExecutionOverlay


def task(mode="live", status="EXECUTING", identity="one"):
    return SimpleNamespace(id=identity, generation=1, mode=mode, status=status)


def test_only_committed_live_dispatch_starts_glow():
    state = ControlActivity()
    state.publish(task(), "task.transitioned")
    assert not state.active
    state.publish(task(mode="test"), "tool.started")
    assert not state.active
    state.publish(task(), "tool.started")
    assert state.active
    state.publish(task(), "tool.finished")
    assert state.active  # between primitives, still inside the same execution phase
    state.publish(task(status="VERIFYING"), "task.transitioned")
    assert not state.active
    state.publish(task(identity="two"), "task.created")
    assert not state.active


def test_pause_and_new_generation_cannot_reuse_previous_visual_activity():
    state = ControlActivity()
    state.publish(task(), "tool.started")
    state.publish(task(status="WAITING_APPROVAL"), "approval.requested")
    assert not state.active
    state.publish(task(), "task.transitioned")
    assert not state.active
    state.publish(task(), "tool.started")
    newer = task()
    newer.generation = 2
    state.publish(newer, "task.transitioned")
    assert not state.active


def test_overlay_is_input_transparent_and_stop_overrides_preview():
    app = QApplication.instance() or QApplication([])
    stopped = threading.Event()
    overlay = ExecutionOverlay(ControlActivity(), stopped, app)
    try:
        overlay.preview()
        overlay.sync()
        assert overlay.windows and all(w.isVisible() for w in overlay.windows)
        for window in overlay.windows:
            assert window.windowFlags() & Qt.WindowType.WindowTransparentForInput
            assert window.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
            assert not window.mask().contains(window.rect().center())
        stopped.set()
        overlay.sync()
        assert all(not w.isVisible() for w in overlay.windows)
        stopped.clear()
        overlay.sync()
        assert all(not w.isVisible() for w in overlay.windows)
    finally:
        overlay.close()


def test_edge_render_has_transparent_center_and_visible_color():
    app = QApplication.instance() or QApplication([])
    window = EdgeGlow(app.primaryScreen())
    try:
        window.resize(720, 500)
        image = window.grab().toImage()
        assert image.pixelColor(360, 250).alpha() == 0
        assert image.pixelColor(360, 4).alpha() > 0
    finally:
        window.close()


def test_disable_and_reduced_motion_keep_stop_available(monkeypatch):
    from assistant import execution_overlay
    monkeypatch.setattr(execution_overlay, "motion_allowed", lambda: False)
    app = QApplication.instance() or QApplication([])
    state = ControlActivity()
    stopped = threading.Event()
    overlay = ExecutionOverlay(state, stopped, app)
    try:
        state.publish(task(), "tool.started")
        overlay.sync()
        assert all(w.isVisible() for w in overlay.windows)
        assert not overlay.animation.isActive()
        overlay.set_enabled(False)
        assert all(not w.isVisible() for w in overlay.windows)
        assert state.active  # presentation does not revoke or grant permissions
        overlay.set_enabled(True)
        stopped.set()
        overlay.sync()
        assert all(not w.isVisible() for w in overlay.windows)
    finally:
        overlay.close()


def test_native_probe_ui_preview_cannot_submit_tasks(tmp_path):
    from assistant.controller import Controller
    from assistant.stop import StopController
    from assistant.ui import ControlCenter
    app = QApplication.instance() or QApplication([])
    stop = StopController()
    controller = Controller(tmp_path, stop, test_mode=True)
    window = ControlCenter(controller, stop, SimpleNamespace(registered=False, error="test"))
    seen = []
    window.preview_requested.connect(lambda: seen.append(True))
    try:
        window.preview_button.click()
        assert seen == [True]
        assert controller.commands.empty()
        assert not controller.native_enabled
        assert "不操作电脑" in window.preview_note.text()
        stop.trip()
        window.preview_button.click()
        assert seen == [True]
        assert controller.commands.empty()
    finally:
        window.exiting = True
        window.close()
