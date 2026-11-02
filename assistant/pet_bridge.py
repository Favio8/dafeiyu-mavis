"""Thin adapter to upstream public tray and bubble APIs; no renderer replacement."""
from __future__ import annotations

import os

from PySide6.QtCore import QObject, QTimer, Qt, Slot, QEvent
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from .controller import Controller
from .stop import EmergencyHotkey, StopController
from .ui import ControlCenter, LABELS
from .execution_overlay import ExecutionOverlay
from .branding import application_icon
from .voice_host import VoiceHost, RecordingHotkey
from .pet_presentation import PetPresentation


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
        from .settings import load_settings, AppSettings
        try:
            initial_settings = load_settings(config.dir / "assistant-settings.json")
        except (ValueError, OSError):
            initial_settings = AppSettings()
        self.hotkey = EmergencyHotkey(self.stop, initial_settings.emergency_shortcut)
        self.hotkey.start()
        self.controller = Controller(config.dir, self.stop, test_mode=os.environ.get("MAVIS_TEST_MODE") == "1", hotkey=self.hotkey)
        self.window = ControlCenter(self.controller, self.stop, self.hotkey)
        self.voice = VoiceHost(self.controller, self.stop, config.dir, self)
        self.voice.bind_window(self.window)
        self.window.install_voice(self.voice)
        self.controller.recording_hotkey = self.voice.hotkey
        self.controller.voice_status_summary = {"state": self.voice.state["state"], "devices": len(self.voice.state["devices"]), "models": dict(self.voice.state["models"])}
        self.presentation = PetPresentation(shell)
        self.window.hotkeys_requested.connect(self._apply_hotkeys)
        self.window.pet_action.connect(self._pet_action)
        self.window.hide_notice.connect(self._hide_notice)
        self.last_voice_state = None
        self.voice.changed.connect(self._voice_state)
        self.overlay = ExecutionOverlay(self.controller.control_activity, self.stop.event, self)
        self.avoid_target = initial_settings.avoid_target
        self.window.preview_requested.connect(self.overlay.preview)
        self.window.glow_changed.connect(self.overlay.set_enabled)
        self.window.avoid_changed.connect(lambda enabled: setattr(self, "avoid_target", enabled))
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
        self.presentation_timer = QTimer(self)
        self.presentation_timer.setInterval(75)
        self.presentation_timer.timeout.connect(self._sync_presentation)
        self.presentation_timer.start()
        self._apply_hotkeys(initial_settings.emergency_shortcut, initial_settings.recording_shortcut, persist=False)
        self._sync_presentation()
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
        self.controller.voice_status_summary = {"state": value["state"], "devices": len(value.get("devices", [])), "capture_open": value.get("capture_open", False), "models": dict(value.get("models", {}))}
        state = value["state"]
        if self.shell is None or state == self.last_voice_state:
            return
        self.last_voice_state = state
        self.presentation.animate(state)
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
        self._sync_presentation()
        task = snapshot["task"]
        state = (task["id"], task["status"]) if task else None
        if self.shell is None or state is None or state == self.last_state:
            return
        self.last_state = state
        self.presentation.animate(task["status"], verified=task["verification_status"] == "passed", live=task["mode"] == "live")
        from pet.multi_window_shared import presentation_targets
        text = ("测试：" if task["mode"] == "test" else "") + LABELS.get(task["status"], task["status"])
        for target in presentation_targets(self.shell):
            target.show_bubble(text, duration_ms=3200)

    def _sync_presentation(self):
        if self.closed:
            return
        self.presentation.set_working(self.avoid_target and self.controller.control_activity.active and not self.stop.event.is_set())
        targets = self.presentation.targets()
        cfg = self.shell.config if self.shell and hasattr(self.shell, "config") else None
        summary = "桌宠已连接" if targets else "仅运行控制中心，桌宠宿主未启动"
        if cfg:
            summary += f" · 角色 {cfg.get('character_id', '未提供')} · 缩放 {cfg.get('scale', '未提供')} · 透明度 {cfg.get('pet_opacity', '未提供')}%"
        self.window.update_pet({"available": bool(targets), "summary": summary})

    def _pet_action(self, command):
        for target in self.presentation.targets():
            if command == "settings":
                opener = getattr(target, "open_settings_for", None)
                if callable(opener):
                    opener()
                    return
                for instance in self.shell.instances:
                    if instance.win is target:
                        instance.open_modern_settings()
                        return
            elif command in {"show", "hide"}:
                setter = getattr(target, "set_pet_visible", None)
                if callable(setter):
                    setter(command == "show")
                elif isinstance(target, QWidget):
                    target.show() if command == "show" else target.hide()

    def _hide_notice(self, message):
        tray = self.tray if self.shell is None else self.shell.tray
        if tray:
            tray.showMessage("Mavis 继续常驻", message, QSystemTrayIcon.MessageIcon.Information, 6000)

    def _apply_hotkeys(self, emergency, recording, *, persist=True):
        from .settings import AppSettings
        task = self.controller.service.task if self.controller.service else None
        from .contracts import TERMINAL
        if task and task.status not in TERMINAL:
            self.window.show_error("请先结束当前任务再更换快捷键")
            return
        try:
            AppSettings(emergency_shortcut=emergency, recording_shortcut=recording)
        except ValueError:
            self.window.show_error("快捷键须使用不同的 Ctrl+Alt+F1～F12、字母或 Space 组合")
            return
        new_stop = self.hotkey
        new_record = self.voice.hotkey
        if emergency != self.hotkey.shortcut or not self.hotkey.registered:
            new_stop = EmergencyHotkey(self.stop, emergency)
            if not new_stop.start():
                self.window.show_error("急停快捷键注册失败，保留原组合："+str(new_stop.error))
                return
        if recording != self.voice.hotkey.shortcut or not self.voice.hotkey.registered:
            new_record = RecordingHotkey(self.stop, self.voice.manual_requested.emit, recording)
            if not new_record.start():
                if new_stop is not self.hotkey:
                    new_stop.close()
                self.window.show_error("录音快捷键注册失败，保留原组合："+str(new_record.error))
                return
        if new_stop is not self.hotkey:
            self.hotkey.close()
            self.hotkey = new_stop
            self.controller.hotkey = new_stop
            self.window.hotkey = new_stop
            if self.controller.native_tasks:
                self.controller.native_tasks.hotkey = new_stop
            if self.controller.native_enabled:
                self.stop.trip()
                self.controller.submit("native_scope", False)
        if new_record is not self.voice.hotkey:
            self.voice.hotkey.close()
            self.voice.hotkey = new_record
            self.controller.recording_hotkey = new_record
        self.voice.state["hotkey"] = self.voice.hotkey.registered
        self.window.hotkey_state.setText(f"急停 {self.hotkey.shortcut}：{'已注册' if self.hotkey.registered else '不可用'}\n录音 {self.voice.hotkey.shortcut}：{'已注册' if self.voice.hotkey.registered else '不可用'}")
        self.window.voice_panel.shortcut.setText(self.voice.hotkey.shortcut+" 手动录音："+("已注册" if self.voice.hotkey.registered else "不可用，请使用按钮"))
        self.window.notice.setText(self.hotkey.shortcut+"："+("已注册" if self.hotkey.registered else "不可用"))
        if persist:
            self.controller.submit("settings_patch", {"emergency_shortcut": emergency, "recording_shortcut": recording})

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
        self.presentation_timer.stop()
        self.stop.trip()
        self.presentation.close()
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
