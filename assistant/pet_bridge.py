"""Thin adapter to upstream public tray and bubble APIs; no renderer replacement."""
from __future__ import annotations

import os

from PySide6.QtCore import QObject, QTimer, Qt, Slot, QEvent
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .controller import Controller
from .stop import EmergencyHotkey, StopController
from .ui import ControlCenter, LABELS
from .execution_overlay import ExecutionOverlay
from .branding import application_icon
from .voice_host import VoiceHost


class PetBridge(QObject):
    """Own the Mavis controller and UI for the lifetime of the existing pet app."""
    def __init__(self, app, shell, config):
        super().__init__(app)
        self.app, self.shell = app, shell
        self.closed = False
        self.last_state = None
        self.menu = None
        self.actions = []
        self.stop = StopController()
        self.hotkey = EmergencyHotkey(self.stop)
        self.hotkey.start()
        self.controller = Controller(config.dir, self.stop, test_mode=os.environ.get("MAVIS_TEST_MODE") == "1", hotkey=self.hotkey)
        self.window = ControlCenter(self.controller, self.stop, self.hotkey)
        self.voice = VoiceHost(self.controller, self.stop, config.dir, self)
        self.voice.bind_window(self.window)
        self.window.install_voice(self.voice)
        self.last_voice_state = None
        self.voice.changed.connect(self._voice_state)
        self.overlay = ExecutionOverlay(self.controller.control_activity, self.stop.event, self)
        self.window.preview_requested.connect(self.overlay.preview)
        self.window.glow_changed.connect(self.overlay.set_enabled)
        self.controller.signals.snapshot.connect(self._state, Qt.ConnectionType.QueuedConnection)
        self.controller.start()
        if shell is None:
            self.tray = QSystemTrayIcon(application_icon(), self)
            self.tray_menu = QMenu()
            self.tray.setContextMenu(self.tray_menu)
            self.tray_menu.addAction("退出", app.quit)
            self.tray.show()
        else:
            self.tray = shell.tray
        self._tray_menu()
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._tray_menu)
        self.timer.start()
        # QApplication's Quit event first asks windows to close. A hide-on-close
        # control centre otherwise vetoes quit before aboutToQuit can run.
        app.installEventFilter(self)
        app.aboutToQuit.connect(self.close)
        self.window.show()

    def _tray_menu(self) -> None:
        tray = self.shell.tray if self.shell else self.tray
        menu = tray.contextMenu() if tray else None
        if menu is None or menu is self.menu:
            return
        self.menu = menu
        first = menu.actions()[0] if menu.actions() else None
        self.actions = []
        for text, callback in [("Mavis 控制中心", self.show), ("语音录音", lambda: self.voice.record("button")), ("关闭麦克风", lambda: self.voice.listen(False)), ("立即停止助手任务", self.stop.trip)]:
            action = QAction(text, menu)
            action.triggered.connect(callback)
            menu.insertAction(first, action)
            self.actions.append(action)

    @Slot(object)
    def _voice_state(self, value):
        state = value["state"]
        if self.shell is None or state == self.last_voice_state:
            return
        self.last_voice_state = state
        text = {"CAPTURING": "我在听……", "TRANSCRIBING": "正在本地识别", "PLAYBACK_GUARD": "播报保护中", "ERROR": "语音暂不可用，请查看控制中心"}.get(state)
        if text:
            from pet.multi_window_shared import presentation_targets
            for target in presentation_targets(self.shell):
                target.show_bubble(text, duration_ms=2500)

    def show(self) -> None:
        """Restore the control centre from the existing tray."""
        if self.closed:
            return
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        self.controller.submit("refresh")

    @Slot(object)
    def _state(self, snapshot: dict) -> None:
        if self.closed:
            return
        task = snapshot["task"]
        state = (task["id"], task["status"]) if task else None
        if self.shell is None or state is None or state == self.last_state:
            return
        self.last_state = state
        from pet.multi_window_shared import presentation_targets
        text = ("测试：" if task["mode"] == "test" else "") + LABELS.get(task["status"], task["status"])
        for target in presentation_targets(self.shell):
            target.show_bubble(text, duration_ms=3200)
            # M1 uses truthful text plus the already-running idle animation. No
            # invented animation IDs or success celebrations for simulated tasks.

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        """Revoke execution before the app's quit protocol or decoder teardown."""
        if watched is self.app and event.type() == QEvent.Type.Quit:
            self.close()
        return False

    def close(self) -> None:
        """Stop first, persist on the controller thread, release hotkey and UI resources."""
        if self.closed:
            return
        self.closed = True
        self.app.removeEventFilter(self)
        self.timer.stop()
        self.stop.trip()
        self.voice.close()
        self.overlay.close()
        self.controller.close()
        self.hotkey.close()
        self.window.exiting = True
        self.window.close()
        if self.shell is None:
            self.tray.hide()


def attach(app, shell, config) -> PetBridge:
    """Attach one Mavis host after upstream startup; the caller retains its lifetime."""
    return PetBridge(app, shell, config)
