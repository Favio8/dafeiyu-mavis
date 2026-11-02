"""Voice entry invariants at the existing controller, not a parallel task path."""
from types import SimpleNamespace

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from assistant.controller import Controller
from assistant.stop import StopController
from assistant.ui import ControlCenter
from assistant.voice_audio import PCMConverter
from assistant.voice_engine import normalize_voice_command, strip_wake_prefix
from test_ui import until


def final(text="帮我打开记事本"):
    return {"result": "command", "trigger": "wakeword", "wakeword": "大肥鱼", "audio_duration_ms": 2300,
        "model_id": "test-model", "model_hash": "a"*64, "asr_confidence": None,
        "raw_text": "大肥鱼"+text, "text": text}


def test_wake_boundary_keeps_keyword_in_command_body():
    assert strip_wake_prefix("大飞鱼，输入你好我是大肥鱼", "大肥鱼") == "输入你好我是大肥鱼"
    assert strip_wake_prefix("输入大肥鱼", "大肥鱼") == "输入大肥鱼"
    assert normalize_voice_command("请帮我打开记事本。") == "打开记事本"


def test_stream_resampling_has_same_output_across_pcm_block_boundaries():
    audio = (np.sin(np.arange(44100)*.04)*20000).astype("<i2").tobytes()
    whole = PCMConverter(44100, 1, "Int16").convert(audio)
    stream = PCMConverter(44100, 1, "Int16")
    split = np.concatenate([stream.convert(audio[i:i+1777]) for i in range(0, len(audio), 1777)])
    assert len(whole) == len(split) == 16000
    np.testing.assert_allclose(whole, split, atol=1e-5)


def test_final_voice_uses_shared_tasks_and_no_speech_creates_no_task(tmp_path):
    app = QApplication.instance() or QApplication([])
    stop = StopController()
    controller = Controller(tmp_path, stop)
    window = ControlCenter(controller, stop, SimpleNamespace(registered=False, error="test"))
    controller.start()
    try:
        until(lambda: window.latest is not None)
        data = final()
        metadata = {k: v for k, v in data.items() if k not in {"raw_text", "text"}}
        controller.submit("voice_diagnostic", {**metadata, "result": "no_speech"})
        until(lambda: len(window.latest["voice_attempts"]) == 1)
        assert window.latest["tasks"] == []
        controller.accept_voice(data)
        until(lambda: window.latest["task"] and window.latest["task"]["status"] == "FAILED")
        until(lambda: len(window.latest["voice_attempts"]) == 2)
        task = window.latest["task"]
        assert task["source"] == "voice"
        assert task["original_text"] == "大肥鱼帮我打开记事本"
        assert task["final_text"] == "打开记事本"
        assert task["action_count"] == 0
        assert window.latest["voice_attempts"][0]["task_id"] == task["id"]
        assert window.latest["voice_attempts"][0]["asr_confidence"] is None
        before = window.latest
        controller.accept_voice({"text": "打开记事本", "trigger": False})
        until(lambda: "未建立任务" in window.notice.text())
        assert window.latest is before  # malformed metadata cannot create a new task
    finally:
        controller.close()
        window.exiting = True
        window.close()


def test_busy_voice_does_not_approve_or_queue_another_task(tmp_path):
    app = QApplication.instance() or QApplication([])
    stop = StopController()
    controller = Controller(tmp_path, stop, test_mode=True)
    window = ControlCenter(controller, stop, SimpleNamespace(registered=True, error=None))
    controller.start()
    try:
        until(lambda: window.latest is not None)
        controller.submit("exercise")
        until(lambda: window.allow.isEnabled())
        task_id = window.latest["task"]["id"]
        controller.accept_voice(final("同意"))
        until(lambda: bool(window.latest["voice_attempts"]))
        assert window.latest["voice_attempts"][0]["result"] == "busy_ignored"
        assert window.latest["voice_attempts"][0]["asr_text"] is None
        assert window.latest["task"]["id"] == task_id
        assert window.latest["task"]["action_count"] == 0
        assert window.allow.isEnabled()
        controller.accept_voice(final("取消任务"))
        assert stop.event.is_set()
        until(lambda: window.latest["task"]["status"] == "CANCELLED")
        assert len(window.latest["tasks"]) == 1
    finally:
        controller.close()
        window.exiting = True
        window.close()


def test_voice_pause_is_acknowledged_before_next_native_dispatch(tmp_path):
    from assistant.native_tasks import NativeTasks
    from assistant.storage import Store
    from assistant.service import TaskService, InvalidTransition
    from assistant.contracts import TaskStatus as S
    stop = StopController()
    service = TaskService(Store(tmp_path / "pause.db"), stop=stop.event)
    try:
        service.create("test")
        service.transition(S.INTERPRETING)
        service.transition(S.EXECUTING)
        runner = NativeTasks(service, stop, None)
        service.pause_requested.set()
        with pytest.raises(InvalidTransition, match="PAUSED_BEFORE_DISPATCH"):
            runner._dispatch(None)
        assert service.task.status == S.PAUSED
        assert service.task.action_count == 0
    finally:
        service.store.close()


def test_voice_preferences_round_trip_never_restore_microphone_authority(tmp_path):
    from assistant.voice_preferences import VoicePreferences, save
    path = tmp_path / "voice-preferences.json"
    save(path, VoicePreferences(word="小助手", volume=45))
    restored = VoicePreferences.model_validate_json(path.read_text(encoding="utf-8"))
    assert restored.word == "小助手" and restored.volume == 45
    assert not {"listening", "native_enabled", "api_key"} & restored.model_dump().keys()
