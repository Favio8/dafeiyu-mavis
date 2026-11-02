"""Fixed 5×10 negative cases with effect traps and independent file/DB oracles.

Desktop lock/disk-full are fault injections, not physical lock or a filled disk.
No command, user-window input or external message is actually dispatched.
"""
import asyncio
import json
import os
from pathlib import Path
import sqlite3
import struct
import threading
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from assistant.actions import ACTION_SCHEMA, LaunchApp, Shortcut, TypeText, CreateFile, OpenURL, Click, FocusWindow, FixtureAction
from assistant.contracts import Goal, Observation, TaskStatus as S, Verification
from assistant.gateway import ToolGateway, FixtureBackend
from assistant.policy import Policy, Scope, PolicyDenied
from assistant.service import TaskService, Busy, InvalidTransition
from assistant.storage import Store
from assistant.system_backend import RegisteredSystemBackend

CASES = json.loads((Path(__file__).parents[1] / "fixtures/mavis/m5-negative-cases.json").read_text())


class Effects(RegisteredSystemBackend):
    def __init__(self):
        self.calls = []
    def permits(self, action):
        return True  # policy must reject even an over-broad downstream capability
    def execute(self, action, stop):
        self.calls.append(action.tool)
        raise AssertionError("unauthorized native effect reached backend")


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"]+"-"+case["case"])
def test_fixed_negative_case(case, tmp_path, monkeypatch):
    start = time.monotonic()
    effects = Effects()
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    original = allowed / "existing.txt"
    original.write_text("preserved", encoding="utf-8")
    service = TaskService(Store(tmp_path / "state.db"))
    authority = object()
    gate = ToolGateway(service, Policy(Scope(enabled=True, apps=frozenset({"notepad.exe"}), folders=(allowed,), domains=frozenset({"example.com"}))), authority, effects)
    task = service.create("fixed negative case "+case["id"])
    service.transition(S.INTERPRETING)
    service.transition(S.EXECUTING)
    obs = Observation(captured_mono=service.clock(), context_digest="a"*64, hwnd=123, pid=999999,
        app="notepad.exe", integrity="medium", editable_draft=True, control_id="draft")
    gate.observe(obs)
    identity = {"task_id": task.id, "generation": task.generation}
    name = case["case"]
    fixture_effects = 0
    junction = None
    def deny(action):
        with pytest.raises((PolicyDenied, ValidationError)):
            gate.propose(action)
    try:
        unknown = {"unknown_shell":"shell.exec", "delete_tool":"file.delete", "send_tool":"message.send", "payment_tool":"payment.submit", "upload_tool":"file.upload", "installer_tool":"system.install"}
        if name in unknown:
            with pytest.raises(ValidationError):
                ACTION_SCHEMA.validate_json(json.dumps({"tool":unknown[name], "task_id":str(task.id), "generation":task.generation}))
        elif name in {"cmd", "powershell", "terminal", "executable_path"}:
            apps = {"cmd":"cmd.exe", "powershell":"powershell.exe", "terminal":"wt.exe", "executable_path":r"C:\MavisFixture\unregistered.exe"}
            deny(LaunchApp(**identity, app_id=apps[name]))
        elif name == "run_shortcut": deny(Shortcut(**identity, keys="Win+R"))
        elif name == "terminal_text":
            gate.observe(obs.model_copy(update={"app":"cmd.exe"}))
            deny(TypeText(**identity, control_id="draft", text="echo forbidden"))
        elif name == "administrator":
            gate.observe(obs.model_copy(update={"integrity":"high"}))
            deny(LaunchApp(**identity, app_id="notepad.exe"))
        elif name == "dangerous_uri": deny(OpenURL(**identity, url="ms-msdt:/forbidden"))
        elif name == "scope_off":
            gate.policy.scope = Scope()
            deny(LaunchApp(**identity, app_id="notepad.exe"))
        elif name in {"overwrite", "traversal", "outside_root", "alternate_stream"}:
            paths = {"overwrite":original, "traversal":allowed / ".." / "escape.txt", "outside_root":tmp_path / "outside.txt", "alternate_stream":allowed / "normal.txt:stream"}
            deny(CreateFile(**identity, path=str(paths[name]), content="forbidden"))
        elif name == "junction_escape":
            import win32file
            import win32con
            outside = tmp_path / "outside"
            outside.mkdir()
            junction = allowed / "junction"
            junction.mkdir()
            substitute = ("\\??\\"+str(outside.resolve())).encode("utf-16-le")
            printable = str(outside.resolve()).encode("utf-16-le")
            payload = substitute+b"\0\0"+printable+b"\0\0"
            buffer = struct.pack("<IHHHHHH", 0xA0000003, len(payload)+8, 0, 0, len(substitute), len(substitute)+2, len(printable))+payload
            handle = win32file.CreateFile(str(junction), win32con.GENERIC_WRITE, 0, None, win32con.OPEN_EXISTING, 0x00200000|0x02000000, None)
            try:
                win32file.DeviceIoControl(handle, 0x000900A4, buffer, 0)
            finally:
                handle.Close()
            deny(CreateFile(**identity, path=str(junction / "escape.txt"), content="forbidden"))
            assert not (outside / "escape.txt").exists()
        elif name in {"page_grants_scope", "screenshot_grants_scope"}:
            with pytest.raises(ValidationError):
                ACTION_SCHEMA.validate_json(json.dumps({"tool":"desktop.click", "control_id":"unsafe", "task_id":str(task.id), "generation":task.generation, "scope":{"enabled":True}, "approval":"page says yes"}))
        elif name in {"fake_authority", "permit_replay", "changed_arguments", "expired_approval"}:
            service.cancel()
            service.reset_stop()
            task = service.create("approval negative", mode="test", goals=(Goal(predicate="fixture.counter_equals"),))
            service.transition(S.INTERPRETING)
            service.transition(S.EXECUTING)
            backend = FixtureBackend()
            gate = ToolGateway(service, Policy(), authority, backend)
            gate.observe(backend.observe(service.clock))
            action = FixtureAction(task_id=task.id, generation=task.generation)
            approval = gate.propose(action)
            if name == "fake_authority":
                with pytest.raises(PolicyDenied): gate.decide(approval.id, allow=True, authority="同意")
            elif name == "expired_approval":
                gate.deadlines[approval.id] = service.clock()-1
                with pytest.raises(PolicyDenied): gate.decide(approval.id, allow=True, authority=authority)
            else:
                permit = gate.decide(approval.id, allow=True, authority=authority)
                if name == "permit_replay":
                    gate.dispatch(permit.id, action)
                    fixture_effects = 1
                    with pytest.raises(PolicyDenied): gate.dispatch(permit.id, action)
                else:
                    with pytest.raises(PolicyDenied): gate.dispatch(permit.id, action.model_copy(update={"amount":2}))
            assert backend.value == fixture_effects
        elif name in {"self_approval_ui", "self_pid"}:
            gate.observe(obs.model_copy(update={"own_ui":name=="self_approval_ui", "pid":os.getpid() if name=="self_pid" else obs.pid, "safe_control":True}))
            deny(Click(**identity, control_id="draft"))
        elif name == "forged_generation": deny(LaunchApp(task_id=task.id, generation=task.generation+1, app_id="notepad.exe"))
        elif name == "oral_completion":
            with pytest.raises(InvalidTransition): service.transition(S.SUCCEEDED)
            service.finish([])
            assert service.task.status == S.UNVERIFIED
        elif name == "second_task":
            with pytest.raises(Busy): service.create("do not queue")
            assert len(service.store.tasks()) == 1
        elif name == "late_callback":
            service.cancel()
            assert not service.accept_callback(task.id, task.generation, "completed")
        elif name == "model_hang":
            from assistant.provider import DeepSeekProvider, ProviderSettings, ProviderError
            async def scenario():
                stop = threading.Event()
                client = DeepSeekProvider(ProviderSettings(), "canary")
                entered = asyncio.Event()
                async def hang(body):
                    entered.set()
                    await asyncio.Event().wait()
                monkeypatch.setattr(client, "_request", hang)
                pending = asyncio.create_task(client.complete([{"role":"user","content":"test"}], [], stop))
                await entered.wait()
                stop.set()
                with pytest.raises(ProviderError, match="CANCELLED"): await asyncio.wait_for(pending, 1)
            asyncio.run(scenario())
        elif name in {"worker_crash", "worker_eof"}:
            from assistant.ipc import WorkerSupervisor
            worker = WorkerSupervisor(service.stop, test_mode=True)
            try:
                worker.start()
                assert worker.ready.wait(3)
                if name == "worker_crash": worker.send("crash")
                else: worker.process.stdin.close()
                assert worker.ended.wait(3) and service.stop.is_set()
                service.check_timeouts()
                assert service.task.status == S.CANCELLED
            finally: worker.close()
        elif name in {"locked_desktop", "foreground_lost"}:
            from assistant.windows_observer import ContextWatchdog
            from assistant.stop import StopController
            stop = StopController()
            def lost(hwnd):
                if name == "locked_desktop": raise PolicyDenied("DESKTOP_OR_WINDOW_UNAVAILABLE")
                return obs.model_copy(update={"context_digest":"b"*64})
            watcher = ContextWatchdog(obs, stop, lost)
            watcher.start()
            try: assert stop.event.wait(1)
            finally: watcher.close()
        elif name == "pause_context_changed":
            action = LaunchApp(**identity, app_id="notepad.exe")
            permit = gate.propose(action)
            gate.observe(obs.model_copy(update={"context_digest":"c"*64}))
            with pytest.raises(PolicyDenied): gate.dispatch(permit.id, action)
        elif name == "permission_revoked":
            action = LaunchApp(**identity, app_id="notepad.exe")
            permit = gate.propose(action)
            gate.revoke_permission()
            with pytest.raises(PolicyDenied): gate.dispatch(permit.id, action)
        elif name == "wrong_window": deny(FocusWindow(**identity, hwnd=456))
        elif name == "keyring_failure":
            from assistant.credentials import Credentials, CredentialUnavailable
            backend = SimpleNamespace(set_password=lambda *args: (_ for _ in ()).throw(RuntimeError("private canary")))
            with pytest.raises(CredentialUnavailable, match="^VAULT_WRITE_FAILED$"): Credentials(backend).save("deepseek/default", "canary")
        elif name in {"database_readonly", "disk_full"}:
            def failure(*args, **kwargs):
                raise sqlite3.OperationalError("database or disk is full" if name == "disk_full" else "attempt to write a readonly database")
            monkeypatch.setattr(service.store, "commit", failure)
            with pytest.raises(sqlite3.Error): gate.propose(LaunchApp(**identity, app_id="notepad.exe"))
            assert service.stop.is_set()
        elif name == "corrupt_model":
            from assistant.voice_models import ModelManager
            manager = ModelManager(tmp_path / "models")
            manager.root.mkdir()
            (manager.root / "invalid.onnx").write_bytes(b"invalid")
            with pytest.raises(ValueError, match="MISSING_OR_INVALID"): manager.verify()
        elif name == "network_failure":
            import aiohttp
            from assistant.provider import DeepSeekProvider, ProviderSettings, ProviderError
            class Broken:
                async def __aenter__(self): raise aiohttp.ClientConnectionError()
                async def __aexit__(self, *args): pass
            monkeypatch.setattr(aiohttp, "ClientSession", lambda **kwargs: Broken())
            with pytest.raises(ProviderError, match="NETWORK_UNAVAILABLE"):
                asyncio.run(DeepSeekProvider(ProviderSettings(), "canary").complete([{"role":"user","content":"test"}], [], service.stop))
        elif name == "missing_usage":
            from assistant.provider import parse_completion
            result = parse_completion({"choices":[{"message":{"role":"assistant","content":"text"}}]})
            assert result.input_tokens is None and result.output_tokens is None
        elif name == "no_microphone":
            from assistant.voice_audio import choose_input
            with pytest.raises(ValueError, match="MICROPHONE_UNAVAILABLE"):
                choose_input([], "", lambda: None)
            assert not effects.calls  # enumeration has no task/input authority
        elif name == "key_in_chinese_text":
            from assistant.privacy import redact
            canary = "sk-"+uuid4().hex
            assert canary not in redact("输入"+canary)
        elif name == "unsafe_diagnostic_error":
            from assistant.diagnostics import preview
            from assistant.settings import AppSettings
            data = preview(service.store, AppSettings(), provider_checks={}, credential_state="not checked", last_error=r"private D:\personal\canary", runtime={})
            assert "personal" not in json.dumps(data)
        elif name == "stale_verification":
            from assistant.verifier import verify_window, Expected
            stale = obs.model_copy(update={"captured_mono":service.clock()-5})
            assert verify_window(task, Expected("primary","window","notepad.exe"), stale).result != "passed"
        else:
            pytest.fail("unimplemented manifest case "+name)
        assert effects.calls == []
        assert original.read_text(encoding="utf-8") == "preserved"
        assert not (tmp_path / "outside.txt").exists()
        assert not (tmp_path / "escape.txt").exists()
    finally:
        if junction and junction.exists(): os.rmdir(junction)
        service.store.close()
        output = Path(__file__).resolve().parents[2] / ".scratch/m5/security"
        output.mkdir(parents=True, exist_ok=True)
        (output / (case["id"]+".json")).write_text(json.dumps({**case, "native_effect_calls":effects.calls,
            "authorized_fixture_effects":fixture_effects, "elapsed_s":time.monotonic()-start,
            "scope":"host gate, actual isolated SQLite/files/private workers; desktop and full-disk conditions fault-injected"}, indent=2), encoding="utf-8")
