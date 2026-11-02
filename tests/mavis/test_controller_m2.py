"""Admission, consent and cancellation at the existing controller boundary."""
from types import SimpleNamespace
import threading

from PySide6.QtWidgets import QApplication

from assistant.controller import Controller
from assistant.stop import StopController
from assistant.ui import ControlCenter
from test_ui import until


def test_native_scope_needs_hotkey_test_and_is_session_only(tmp_path):
    app = QApplication.instance() or QApplication([])
    stop = StopController()
    hotkey = SimpleNamespace(registered=True, error=None, physical_seen=False)
    controller = Controller(tmp_path, stop, hotkey=hotkey)
    window = ControlCenter(controller, stop, hotkey)
    controller.start()
    try:
        until(lambda:window.latest is not None)
        controller.submit("native_scope", True)
        until(lambda:"TEST_HOTKEY_AND_RESET_FIRST" in window.notice.text())
        assert not controller.native_enabled
        hotkey.physical_seen = True  # unit boundary; actual physical probe is separately recorded
        controller.submit("native_scope", True)
        until(lambda:window.latest["native_enabled"])
        window.native_scope.setChecked(False)
        assert stop.event.is_set()  # immediate on UI thread; not queued behind native I/O
        until(lambda:not window.latest["native_enabled"])
        assert window.latest["tasks"] == []
    finally:
        controller.close()
        window.exiting = True
        window.close()


def test_model_diagnostics_do_not_make_user_tasks(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    from assistant.credentials import Credentials
    monkeypatch.setattr(Credentials, "read", lambda *args:None)
    stop = StopController()
    controller = Controller(tmp_path, stop)
    window = ControlCenter(controller, stop, SimpleNamespace(registered=False,error="unavailable"))
    controller.start()
    try:
        until(lambda:window.latest is not None)
        controller.submit("probe_connection")
        until(lambda:window.latest["provider_checks"]["connection"] == "CREDENTIAL_MISSING")
        assert not window.latest["tasks"] and window.latest["task"] is None
    finally:
        controller.close()
        window.exiting = True
        window.close()


def test_stop_between_task_start_and_worker_creation(tmp_path):
    app = QApplication.instance() or QApplication([])
    stop = StopController()
    controller = Controller(tmp_path, stop, test_mode=True)
    window = ControlCenter(controller, stop, SimpleNamespace(registered=True,error=None))
    controller.start()
    try:
        until(lambda:window.latest is not None)
        controller.service.subscribers.append(lambda e: stop.event.set() if e.payload_redacted == "EXECUTING" else None)
        controller.submit("hang")
        until(lambda:window.latest["task"] and window.latest["task"]["status"] == "CANCELLED")
        assert controller.is_alive()
        assert controller.worker.process is None or controller.worker.process.poll() is not None
    finally:
        controller.close()
        window.exiting = True
        window.close()


def test_second_command_is_not_queued_behind_blocking_native_work(tmp_path, monkeypatch):
    from assistant import native_tasks
    from assistant.contracts import TaskStatus as S
    entered, release = threading.Event(), threading.Event()
    calls = []
    class NativeStub:
        def __init__(self, service, *args):
            self.service = service
        def run(self, command):
            calls.append(command)
            self.service.create(command, mode="test")
            self.service.transition(S.INTERPRETING)
            self.service.transition(S.EXECUTING)
            entered.set()
            assert release.wait(5)
            self.service.finish([])
    monkeypatch.setattr(native_tasks,"NativeTasks",NativeStub)
    app = QApplication.instance() or QApplication([])
    stop = StopController()
    hotkey = SimpleNamespace(registered=True,error=None,physical_seen=True)
    controller = Controller(tmp_path,stop,hotkey=hotkey)
    window = ControlCenter(controller,stop,hotkey)
    controller.start()
    try:
        until(lambda:window.latest is not None)
        controller.submit("native_scope",True)
        until(lambda:window.latest["native_enabled"])
        controller.submit("record","first")
        assert entered.wait(3)
        controller.submit("record","second")
        until(lambda:"已有活动任务" in window.notice.text())
        release.set()
        until(lambda:window.latest["task"] and window.latest["task"]["status"] == "UNVERIFIED")
        controller.submit("refresh")
        until(lambda:controller.commands.empty())
        assert calls == ["first"]
    finally:
        release.set()
        controller.close()
        window.exiting = True
        window.close()
