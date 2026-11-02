"""Regression checks for wrong identity, false success, budgets and secret output."""
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from uuid import uuid4
import zipfile

import pytest

from assistant.contracts import Goal,Observation,TaskStatus as S,Verification
from assistant.service import TaskService,InvalidTransition
from assistant.storage import Store
from assistant.policy import PolicyDenied,digest


@pytest.mark.parametrize("method,strength,evidence",[("visual","deterministic","model claims done"),("uia","deterministic","wrong predicate"),("window","deterministic","  ")])
def test_wrong_or_non_evidence_cannot_be_success(tmp_path,method,strength,evidence):
    service=TaskService(Store(tmp_path/"state.db"))
    task=service.create("window goal")
    service.transition(S.INTERPRETING);service.transition(S.EXECUTING)
    try:
        service.finish([Verification(task_id=task.id,generation=task.generation,goal_id="primary",method=method,result="passed",strength=strength,evidence=evidence)])
        assert service.task.status==S.UNVERIFIED
    finally:service.store.close()


def test_finish_after_deadline_never_turns_green(tmp_path):
    clock=[100.0]
    service=TaskService(Store(tmp_path/"state.db"),clock=lambda:clock[0])
    task=service.create("goal")
    service.transition(S.INTERPRETING);service.transition(S.EXECUTING)
    clock[0]=1001
    try:
        with pytest.raises(InvalidTransition):
            service.finish([Verification(task_id=task.id,generation=task.generation,goal_id="primary",method="window",result="passed",evidence="late")])
        assert service.task.status==S.TIMED_OUT
    finally:service.store.close()


def test_same_pid_hwnd_with_new_process_identity_is_rejected(monkeypatch):
    from assistant import notepad_backend
    node=notepad_backend.NotepadDraftBackend.__new__(notepad_backend.NotepadDraftBackend)
    target=Observation(captured_mono=time.monotonic(),context_digest="a"*64,identity_digest="b"*64,hwnd=1,pid=2,app="notepad.exe",integrity="medium")
    node.target=target
    monkeypatch.setattr(notepad_backend,"observe_window",lambda hwnd:target.model_copy(update={"identity_digest":"c"*64}))
    with pytest.raises(PolicyDenied,match="WINDOW_REPLACED"):node.observe_draft()


@pytest.mark.parametrize("text",["content\n","content\r","content\r\r"])
def test_text_reader_does_not_erase_mismatch(monkeypatch,text):
    from assistant import notepad_backend
    import win32gui
    node=notepad_backend.NotepadDraftBackend.__new__(notepad_backend.NotepadDraftBackend)
    target=Observation(captured_mono=time.monotonic(),context_digest="a"*64,identity_digest="b"*64,document_digest=digest("fixture"),hwnd=1,pid=2,app="notepad.exe",integrity="medium")
    node.target=target;node.stop=threading.Event();node.editor_id="42"
    pattern=SimpleNamespace(CurrentValue=text)
    pattern.QueryInterface=lambda interface:pattern
    node.types=SimpleNamespace(IUIAutomationValuePattern=object())
    node._editor=lambda:SimpleNamespace(GetRuntimeId=lambda:[42],GetCurrentPattern=lambda kind:pattern)
    monkeypatch.setattr(notepad_backend,"observe_window",lambda hwnd:target)
    monkeypatch.setattr(win32gui,"GetWindowText",lambda hwnd:"fixture")
    assert node.read_text()==text


def test_sensitive_content_never_enters_db_or_diagnostics(tmp_path):
    from assistant.diagnostics import preview,write_package
    from assistant.settings import AppSettings
    store=Store(tmp_path/"state.db");service=TaskService(store)
    canary="sk-"+uuid4().hex
    try:
        service.create("输入"+canary)
        service.transition(S.INTERPRETING);service.transition(S.FAILED,error_code="TEST")
        assert canary not in store.tasks()[0].model_dump_json()
        data=preview(store,AppSettings(),provider_checks={},credential_state="present",last_error=canary,runtime={})
        path=tmp_path/"diagnostic.zip";write_package(path,data)
        with zipfile.ZipFile(path) as archive:
            assert archive.namelist()==["diagnostics.json"]
            assert canary.encode() not in archive.read("diagnostics.json")
    finally:store.close()
    assert canary.encode() not in (tmp_path/"state.db").read_bytes()


def test_history_denominator_includes_all_ended_tasks(tmp_path):
    from assistant.history import HistoryQuery
    store=Store(tmp_path/"state.db");service=TaskService(store)
    try:
        for expected in (S.FAILED,S.UNVERIFIED):
            service.create("test",mode="test");service.transition(S.INTERPRETING);service.transition(S.EXECUTING)
            service.finish([]) if expected==S.UNVERIFIED else service.transition(expected)
        task=service.create("verified",mode="test",goals=(Goal(predicate="fixture.counter_equals"),))
        service.transition(S.INTERPRETING);service.transition(S.EXECUTING)
        service.finish([Verification(task_id=task.id,generation=task.generation,goal_id="primary",method="fixture",result="passed",evidence="counter oracle")])
        stats=store.history(HistoryQuery(days=0),"test")["statistics"]
        assert stats["ended"]==3 and stats["verified_succeeded"]==1 and stats["rate"]==1/3
    finally:store.close()


def test_three_repeated_no_progress_requests_require_clarification(tmp_path):
    import asyncio
    from assistant.gateway import ToolGateway
    from assistant.policy import Policy,Scope
    from assistant.provider import Completion,ProviderSettings
    from assistant.runtime import AgentRuntime
    from assistant.system_backend import RegisteredSystemBackend
    class Backend(RegisteredSystemBackend):
        def __init__(self):self.calls=0
        def permits(self,action):return True
        def execute(self,action,stop):self.calls+=1;return "no change"
    class Model:
        settings=ProviderSettings()
        async def complete(self,*args):
            return Completion({"role":"assistant","content":None,"tool_calls":[{"id":"test","type":"function","function":{"name":"launch_app","arguments":'{"app_id":"notepad.exe"}'}}]},None,None)
    store=Store(tmp_path/"state.db");service=TaskService(store);backend=Backend()
    observation=lambda:Observation(captured_mono=service.clock(),context_digest="a"*64,hwnd=123,pid=999999,app="notepad.exe",integrity="medium")
    runtime=AgentRuntime(service,ToolGateway(service,Policy(Scope(enabled=True,apps=frozenset({"notepad.exe"}))),object(),backend),Model(),observation,lambda task:[],allowed_tools=("launch_app",))
    try:
        result=asyncio.run(runtime.begin("no progress probe",mode="test"))
        assert result.status==S.WAITING_CLARIFICATION and backend.calls==2 and result.llm_round_count==3
    finally:store.close()
