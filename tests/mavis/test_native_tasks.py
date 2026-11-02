"""Host workflow tests substitute only OS effects; no real applications are opened."""
from types import SimpleNamespace
import time

from assistant.contracts import Observation, TaskStatus as S
from assistant.native_tasks import NativeTasks
from assistant.service import TaskService
from assistant.stop import StopController
from assistant.storage import Store
from assistant.system_backend import RegisteredSystemBackend


def test_successful_launch_requires_an_observed_window(tmp_path, monkeypatch):
    from assistant import native_tasks
    import win32gui
    windows = []
    observed = Observation(captured_mono=time.monotonic(),context_digest="a"*64,hwnd=11,pid=9999,app="notepad.exe",integrity="medium")
    class Lease:
        def acquire(self): return True
        def close(self): pass
    class Backend(RegisteredSystemBackend):
        def __init__(self,*args): pass
        def execute(self, action, stop):
            windows.append(observed)
            return "OS fixture launch"
    monkeypatch.setattr(native_tasks,"DesktopLease",Lease)
    monkeypatch.setattr(native_tasks,"RegisteredSystemBackend",Backend)
    monkeypatch.setattr(native_tasks,"notepad_windows",lambda:list(windows))
    monkeypatch.setattr(native_tasks,"observe_window",lambda hwnd:observed)
    monkeypatch.setattr(win32gui,"GetForegroundWindow",lambda:11)
    stop = StopController()
    service = TaskService(Store(tmp_path/"state.db"),stop=stop.event)
    runner = NativeTasks(service,stop,SimpleNamespace(registered=True))
    try:
        runner.run("打开记事本")
        assert service.task.status == S.SUCCEEDED
        assert service.task.verification_status == "passed"
        assert service.task.action_count == 1
        assert runner.owned_draft == observed
    finally:
        service.store.close()


def test_unknown_command_and_no_owned_draft_fail_closed(tmp_path):
    stop = StopController()
    service = TaskService(Store(tmp_path/"state.db"),stop=stop.event)
    runner = NativeTasks(service,stop,SimpleNamespace(registered=True))
    try:
        runner.run("删除所有文件")
        assert service.task.status == S.FAILED and service.task.action_count == 0
        runner.run("输入：你好")
        assert service.task.status == S.FAILED and service.task.error_code == "OPEN_A_NEW_NOTEPAD_FIRST"
    finally:
        service.store.close()


def test_sensitive_native_command_is_redacted_before_persistence(tmp_path):
    stop = StopController()
    service = TaskService(Store(tmp_path/"state.db"),stop=stop.event)
    try:
        NativeTasks(service,stop,None).run("输入：密码123456")
        assert service.task.error_code == "SENSITIVE_TEXT_NOT_SUPPORTED"
        assert "123456" not in service.store.tasks()[0].model_dump_json()
    finally:
        service.store.close()
