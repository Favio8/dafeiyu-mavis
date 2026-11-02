"""Host-owned voice session. Worker events cannot approve or dispatch tools."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import threading

from PySide6.QtCore import QObject, QTimer, Signal, Qt, QAbstractNativeEventFilter
from PySide6.QtWidgets import QApplication

from .ipc import WorkerSupervisor, ProtocolError
from .stop import EmergencyHotkey
from .voice_models import ModelManager
from .voice_preferences import VoicePreferences, save


class VoiceProcess(WorkerSupervisor):
    MODULE = "assistant.voice_worker"
    HOST_KINDS = {"hello", "ping", "stop", "voice_config", "voice_listen", "voice_record", "voice_end", "voice_cancel", "voice_speak", "voice_mute"}
    WORKER_KINDS = {"ready", "pong", "error", "voice_event"}


class RecordingHotkey(EmergencyHotkey):
    HOTKEY_ID = 0x4D57
    VKEY = 0x20  # Ctrl+Alt+Space

    def __init__(self, stop, callback, shortcut=None):
        super().__init__(stop, shortcut)
        self.callback = callback

    def _trigger(self):
        self.callback()


class SessionEvents(QAbstractNativeEventFilter):
    def __init__(self, host, window):
        super().__init__()
        self.host, self.hwnd = host, int(window.winId())
        ctypes.windll.wtsapi32.WTSRegisterSessionNotification(wintypes.HWND(self.hwnd), 0)

    def nativeEventFilter(self, event_type, message):  # noqa: N802
        msg = wintypes.MSG.from_address(int(message))
        if (msg.message == 0x2B1 and msg.wParam == 7) or (msg.message == 0x218 and msg.wParam == 4):
            self.host.stop.trip()
            self.host.suspend("会话锁定或休眠，麦克风已关闭")
        return False, 0

    def close(self):
        ctypes.windll.wtsapi32.WTSUnRegisterSessionNotification(wintypes.HWND(self.hwnd))


class VoiceHost(QObject):
    changed = Signal(object)
    activity = Signal(str, object)
    _incoming = Signal(object)
    _prepared = Signal(str)
    manual_requested = Signal()

    def __init__(self, controller, stop, data_dir: Path, parent=None):
        super().__init__(parent)
        self.controller, self.stop = controller, stop
        self.models = ModelManager(data_dir / "voice" / "models")
        self.process = None
        self.epoch = 0
        self.desired = False
        self.test_mode = True  # calibration never executes a task by default
        self.tts_enabled = True
        self.closed = False
        self.config = {"root": str(self.models.root), "word": "大肥鱼", "sensitivity": "标准", "device": "", "voice": "", "volume": 70}
        self.preferences_path = data_dir / "voice-preferences.json"
        preference_error = ""
        try:
            if self.preferences_path.exists():
                preferences = VoicePreferences.model_validate_json(self.preferences_path.read_text(encoding="utf-8"))
                self.config.update(preferences.model_dump(exclude={"tts_enabled"}))
                self.tts_enabled = preferences.tts_enabled
        except (ValueError, OSError):
            preference_error = "语音偏好无法读取，本次使用默认配置；原文件保留。"
        self.state = {"state": "OFF", "level": 0, "capture_open": False, "devices": [], "voices": [], "error": "", "last_text": "", "models": self.models.status(), "desired": False, "test_mode": True, "word": "大肥鱼"}
        self.state.update(error=preference_error, word=self.config["word"])
        from PySide6.QtMultimedia import QMediaDevices
        self.state["devices"] = [{"id": bytes(d.id()).hex(), "name": d.description(), "default": d.isDefault()} for d in QMediaDevices.audioInputs()]
        self.state["devices_checked"] = True
        self.last_final = None
        self._incoming.connect(self._event, Qt.ConnectionType.QueuedConnection)
        self._prepared.connect(self._prepared_done, Qt.ConnectionType.QueuedConnection)
        self.manual_requested.connect(lambda: self.record("hotkey"), Qt.ConnectionType.QueuedConnection)
        self.hotkey = RecordingHotkey(stop, self.manual_requested.emit)
        self.hotkey.start()
        self.state["hotkey"] = self.hotkey.registered
        self.monitor = QTimer(self)
        self.monitor.setInterval(200)
        self.monitor.timeout.connect(self._monitor)
        self.monitor.start()
        controller.signals.feedback.connect(self.feedback, Qt.ConnectionType.QueuedConnection)
        controller.signals.snapshot.connect(self._task_state, Qt.ConnectionType.QueuedConnection)
        self.session_events = None

    def bind_window(self, window):
        import sys
        if sys.platform == "win32":
            self.session_events = SessionEvents(self, window)
            QApplication.instance().installNativeEventFilter(self.session_events)

    def publish(self):
        self.state.update(desired=self.desired, test_mode=self.test_mode)
        self.changed.emit(dict(self.state))

    def _task_state(self, snapshot):
        from .contracts import TERMINAL
        task = snapshot["task"]
        busy = bool(task and task["status"] not in TERMINAL)
        if busy != self.state.get("busy", False):
            self.state["busy"] = busy
            self.publish()

    def _ensure(self):
        if self.stop.event.is_set():
            raise ValueError("急停已锁定，请先明确复位")
        if self.process and self.process.process.poll() is None:
            return
        if self.process:
            self.process.close()
        self.process = VoiceProcess(self.stop.event, on_message=self._incoming.emit, on_failure=self.stop.trip)
        self.stop.own(self.process)
        self.process.start()
        self.process.send("voice_config", json.dumps({**self.config, "epoch": self.epoch}))

    def _send(self, kind, value=None, *, invalidate=False):
        if invalidate:
            self.epoch += 1
        try:
            self._ensure()
            self.process.send(kind, json.dumps({**(value or {}), "epoch": self.epoch}, ensure_ascii=False))
        except (ValueError, RuntimeError, OSError, ProtocolError) as exc:
            self.state.update(error=str(exc), state="ERROR")
            self.desired = False
            self.publish()

    def refresh(self):
        self._send("ping")
        self.publish()

    def listen(self, enabled):
        self.desired = bool(enabled)
        self.state["error"] = ""
        self._send("voice_listen", {"enabled": self.desired}, invalidate=True)
        self.publish()

    def record(self, trigger="button"):
        self._send("voice_record", {"trigger": trigger}, invalidate=True)

    def end(self):
        self._send("voice_end")

    def cancel(self):
        self._send("voice_cancel", invalidate=True)

    def configure(self, **changes):
        if self.state["state"] in {"CAPTURING", "TRANSCRIBING", "PLAYBACK_GUARD"}:
            self.state["error"] = "请先结束录音或播报，再更换配置"
            self.publish()
            return
        candidate = {**self.config, **changes}
        from .voice_engine import keyword_tokens
        try:
            validated = VoicePreferences.model_validate({key: candidate[key] for key in ("word", "sensitivity", "device", "voice", "volume")})
            candidate.update(validated.model_dump(exclude={"tts_enabled"}))
            if candidate["word"] != self.config["word"]:
                keyword_tokens(candidate["word"], self.models.directory("kws") / "tokens.txt")
        except (OSError, ValueError) as exc:
            self.state["error"] = str(exc)
            self.publish()
            return
        self._candidate = candidate
        original = self.desired
        if original:
            self._send("voice_listen", {"enabled": False}, invalidate=True)
        self._send("voice_config", candidate, invalidate=True)
        if original:
            self._send("voice_listen", {"enabled": True})

    def speak(self, text):
        self.state["state"] = "PLAYBACK_GUARD"
        self._send("voice_speak", {"text": text[:300]}, invalidate=True)
        self.publish()

    def feedback(self, text):
        if self.tts_enabled and not self.stop.event.is_set():
            self.speak(text)

    def set_tts_enabled(self, enabled):
        self.tts_enabled = enabled
        self._save_preferences()

    def _save_preferences(self):
        try:
            save(self.preferences_path, VoicePreferences(**{k: self.config[k] for k in ("word", "sensitivity", "device", "voice", "volume")}, tts_enabled=self.tts_enabled))
        except OSError:
            self.state["error"] = "本次配置已生效，但语音偏好保存失败。"
            self.publish()

    def correct(self, text):
        if self.last_final and not self.test_mode and text.strip():
            self.controller.accept_voice({**self.last_final, "text": text.strip()})

    def prepare(self, import_dir=None, *, delete=False):
        if self.state.get("models_progress"):
            return
        if self.state["state"] not in {"OFF", "ERROR"}:
            self.state["error"] = "请先关闭监听并停止播报"
            self.publish()
            return
        if self.process:
            self.process.close()
        self.state["models_progress"] = "处理中"
        self.publish()
        def work():
            try:
                if delete:
                    self.models.delete()
                else:
                    self.models.prepare(Path(import_dir) if import_dir else None)
                self._prepared.emit("")
            except (ValueError, OSError, EOFError) as exc:
                self._prepared.emit(str(exc))
        threading.Thread(target=work, name="mavis-model-resources", daemon=True).start()

    def _prepared_done(self, error):
        self.state.update(models=self.models.status(), models_progress="", error=error)
        self.publish()

    def _event(self, message):
        if self.closed or message.kind != "voice_event":
            return
        value = json.loads(message.payload)
        event = value.pop("event")
        epoch = value.pop("epoch")
        if event in {"devices", "voices"}:
            self.state.update(value)
        elif epoch != self.epoch or self.stop.event.is_set():
            return
        if event not in {"devices", "voices"}:
            self.activity.emit(event, value)
        if event in {"devices", "voices"}:
            pass
        elif event == "state":
            self.state.update(value)
        elif event == "capture":
            self.state["capture_open"] = value["open"]
            if not value["open"]:
                self.state["level"] = 0
        elif event == "level":
            self.state["level"] = value["level"]
        elif event == "configured":
            self.state.update(word=value["word"], error="")
            if hasattr(self, "_candidate"):
                self.config = self._candidate
                del self._candidate
                self._save_preferences()
        elif event == "error":
            self.desired = False
            self.state.update(state="ERROR", error=value["code"])
        elif event == "final":
            self.last_final = value
            self.state["last_text"] = value["text"]
            if self.test_mode:
                metadata = {key: value[key] for key in ("trigger", "wakeword", "audio_duration_ms", "model_id", "model_hash", "asr_confidence", "result")}
                self.controller.submit("voice_diagnostic", metadata)
            else:
                self.controller.accept_voice(value)
        elif event == "attempt":
            self.controller.submit("voice_diagnostic", value)
        elif event == "playback_end" and value.get("error"):
            self.state["error"] = "本地播报失败，已保留文字反馈"
        self.publish()

    def _monitor(self):
        if self.process and self.process.process and self.process.process.poll() is not None and self.state["state"] != "OFF":
            self.desired = False
            self.state.update(state="OFF" if self.stop.event.is_set() else "ERROR", capture_open=False, level=0,
                error="急停已释放语音进程" if self.stop.event.is_set() else "语音进程已退出，请重新开启")
            self.publish()

    def suspend(self, reason):
        self.epoch += 1
        self.desired = False
        if self.process:
            self.process.close()
        self.state.update(state="OFF", capture_open=False, level=0, error=reason)
        self.publish()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.monitor.stop()
        self.hotkey.close()
        if self.session_events:
            QApplication.instance().removeNativeEventFilter(self.session_events)
            self.session_events.close()
        if self.process:
            self.process.close()
