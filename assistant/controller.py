"""Qt signal bridge to a single controller/SQLite writer thread."""
from __future__ import annotations

import queue
import sqlite3
import threading
import time
from pathlib import Path
from uuid import UUID

from PySide6.QtCore import QObject, Signal

from .actions import FixtureAction
from .contracts import Goal, TaskStatus as S, TERMINAL, VoiceAttempt
from .gateway import FixtureBackend, ToolGateway
from .ipc import WorkerSupervisor
from .policy import Policy, PolicyDenied
from .service import Busy, InvalidTransition, TaskService
from .storage import Store
from .presentation import ControlActivity


class Signals(QObject):
    """Signals may be emitted by the controller; connected widgets live on the Qt thread."""
    snapshot = Signal(object)
    details = Signal(object)
    error = Signal(str)
    feedback = Signal(str)


class Controller(threading.Thread):
    """Serial host command queue. Blocking I/O never runs in a widget callback."""
    def __init__(self, data_dir: Path, stop, *, test_mode: bool = False, hotkey=None):
        super().__init__(name="mavis-controller", daemon=True)
        self.data_dir, self.stop, self.test_mode = data_dir, stop, test_mode
        self.signals = Signals()
        self.commands = queue.Queue(maxsize=32)
        self.closed = threading.Event()
        self.ready = threading.Event()
        self.authority = object()
        self.worker = None
        self.last_error = None
        self.service = None
        self.provider_checks = {"connection": "待验证", "tools": "待验证"}
        self.hotkey, self.native_enabled, self.native_tasks = hotkey, False, None
        self._request_lock = threading.Lock()
        self._task_reserved = False
        self.control_activity = ControlActivity()
        self._feedback_task = None

    def _published(self, event) -> None:
        self.control_activity.publish(self.service.task, event.type)
        task = self.service.task
        if task and task.mode == "live" and task.status in TERMINAL and task.id != self._feedback_task and not self.stop.event.is_set():
            self._feedback_task = task.id
            self.signals.feedback.emit("已验证，操作完成。" if task.status == S.SUCCEEDED and task.verification_status == "passed" else "这次操作未完成，请查看任务记录。")
        self._snapshot()

    def accept_voice(self, value: dict) -> None:
        """Final local ASR only. Busy commands are diagnosed, never silently queued."""
        from .voice_engine import normalize_voice_command
        text = normalize_voice_command(value.get("text", ""))
        metadata = {key: value[key] for key in VoiceAttempt.model_fields if key in value}
        try:
            VoiceAttempt.model_validate({**metadata, "asr_text": None})
        except ValueError:
            self.signals.error.emit("语音事件不完整，未建立任务")
            return
        if not text:
            self.submit("voice_diagnostic", {**metadata, "result": "empty", "asr_text": None})
            return
        active = self.service and self.service.task and self.service.task.status not in TERMINAL
        if text in {"停止", "取消", "取消任务", "停止任务"}:
            self.stop.trip()  # does not queue behind native I/O or model work
            self.submit("voice_diagnostic", {**metadata, "result": "empty", "asr_text": None})
            return
        if active and text in {"暂停", "暂停任务"}:
            self.service.pause_requested.set()
            self.submit("voice_pause")
            self.submit("voice_diagnostic", {**metadata, "result": "empty", "asr_text": None})
            return
        if active and self.service.task.status == S.WAITING_CLARIFICATION:
            self.submit("voice_answer", {**value, "task_id": str(self.service.task.id), "generation": self.service.task.generation})
            return
        with self._request_lock:
            busy = self._task_reserved or active
            if not busy:
                self._task_reserved = True
        if busy:
            self.submit("voice_diagnostic", {**metadata, "result": "busy_ignored", "asr_text": None})
            self.signals.error.emit("已有活动任务；这条语音指令未排队")
            return
        try:
            self.commands.put_nowait(("voice_final", {**value, "text": text}))
        except queue.Full:
            with self._request_lock:
                self._task_reserved = False
            self.signals.error.emit("语音指令未提交，请稍后重说")

    def submit(self, command: str, value=None) -> None:
        """Queue a local UI command. No IPC message is routed to this command surface."""
        if command not in {"record", "exercise", "hang", "approve", "deny", "pause", "resume", "reset", "details", "refresh", "exit", "probe_connection", "probe_tools", "native_scope", "voice_diagnostic", "voice_pause", "voice_answer"}:
            raise ValueError("unknown local UI command")
        task_request = command in {"record", "exercise", "hang"}
        if task_request:
            with self._request_lock:
                if self._task_reserved or (self.service and self.service.task and self.service.task.status not in TERMINAL):
                    self.signals.error.emit("已有活动任务，请先停止或等待结束")
                    return
                self._task_reserved = True
        try:
            self.commands.put_nowait((command, value))
        except queue.Full:
            if task_request:
                with self._request_lock:
                    self._task_reserved = False
            self.signals.error.emit("操作请求过多，请稍后重试")

    def _snapshot(self) -> None:
        task = self.service.task
        pending = next((a for a in self.gateway.approvals.values() if task and a.task_id == task.id and a.status == "pending"), None)
        self.signals.snapshot.emit({"task": task.model_dump(mode="json") if task else None,
            "tasks": [t.model_dump(mode="json") for t in self.service.store.tasks(mode="test" if self.test_mode else "live")],
            "approval": pending.model_dump(mode="json") if pending else None,
            "stopped": self.stop.event.is_set(), "test_mode": self.test_mode,
            "provider_checks": dict(self.provider_checks), "native_enabled":self.native_enabled,
            "voice_attempts": [v.model_dump(mode="json") for v in self.service.store.voice_attempts()]})

    def _probe_model(self, kind: str) -> None:
        import asyncio
        from .credentials import Credentials, CredentialUnavailable
        from .provider import DeepSeekProvider, ProviderSettings, ProviderError
        from .model_diagnostics import probe
        if self.service.task and self.service.task.status not in TERMINAL:
            raise Busy("请先结束当前任务再测试模型")
        if self.stop.event.is_set():
            raise InvalidTransition("请先明确复位急停")
        self.provider_checks[kind] = "测试中"
        self._snapshot()
        try:
            secret = Credentials().read("deepseek/default")
            if not secret:
                raise ProviderError("CREDENTIAL_MISSING")
            client = DeepSeekProvider(ProviderSettings(), secret)
            result = asyncio.run(probe(client, kind, self.stop.event))
            self.provider_checks[kind] = "通过" if result["passed"] else "未通过"
        except (ProviderError, CredentialUnavailable) as exc:
            self.provider_checks[kind] = str(exc)

    def _new(self, text: str, *, fixture: bool = False, source="text", original_text=None):
        if self.service.task and self.service.task.status not in TERMINAL:
            raise Busy("已有活动任务，请先停止或等待结束")
        if self.worker:
            self.worker.close()
            self.worker = None
        if fixture and not self.test_mode:
            raise PolicyDenied("TEST_MODE_REQUIRED")
        task = self.service.create(text, source=source, original_text=original_text, mode="test" if self.test_mode else "live",
                    goals=(Goal(predicate="fixture.counter_equals", description="测试计数器按批准值增加"),) if fixture else None)
        self.service.transition(S.INTERPRETING)
        self.gateway.actions.clear()
        self.gateway.steps.clear()
        self.gateway.approvals.clear()
        self.gateway.deadlines.clear()
        return task

    def _handle(self, command: str, value) -> bool:
        if command == "exit":
            self.service.cancel()
            return False
        if command in {"probe_connection", "probe_tools"}:
            self._probe_model(command.removeprefix("probe_"))
        elif command == "voice_diagnostic":
            self.service.store.voice_attempt(VoiceAttempt.model_validate(value))
        elif command == "voice_answer":
            if self.service.accept_callback(UUID(value["task_id"]), value["generation"], "voice.clarification") and self.service.task.status == S.WAITING_CLARIFICATION:
                self.service.persist(self.service.task, "voice.clarification", str(value["text"]))
                metadata = {key: value[key] for key in VoiceAttempt.model_fields if key in value}
                self.service.store.voice_attempt(VoiceAttempt(**{**metadata, "result": "command", "task_id": self.service.task.id, "asr_text": value["text"]}))
                self.signals.error.emit("澄清答案已记录；当前 M2 执行路径尚未接入澄清后恢复")
        elif command == "voice_final":
            metadata = {key: value[key] for key in VoiceAttempt.model_fields if key in value}
            if self.native_enabled and not self.test_mode:
                self.native_tasks.run(value["text"], source="voice", original_text=value.get("raw_text", value["text"]))
            else:
                self._new(value["text"], source="voice", original_text=value.get("raw_text", value["text"]))
                self.service.transition(S.FAILED, error_code="COMPUTER_CONTROL_DISABLED")
            self.service.store.voice_attempt(VoiceAttempt(**{**metadata, "result": "command", "task_id": self.service.task.id, "asr_text": value["text"]}))
        elif command == "record":
            if self.native_enabled and not self.test_mode:
                self.native_tasks.run(str(value))
            else:
                self._new(str(value))
                self.service.transition(S.FAILED, error_code="COMPUTER_CONTROL_DISABLED")
        elif command == "native_scope":
            if type(value) is not bool or self.test_mode:
                raise PolicyDenied("LIVE_LOCAL_UI_REQUIRED")
            if value and (not self.hotkey or not self.hotkey.registered or self.stop.event.is_set()):
                raise PolicyDenied("NATIVE_CONTROL_NOT_ARMED")
            if value and not getattr(self.hotkey, "physical_seen", False):
                raise PolicyDenied("TEST_HOTKEY_AND_RESET_FIRST")
            self.native_enabled = value
            if not value:
                self.service.cancel()
        elif command in {"exercise", "hang"}:
            task = self._new("本地审批演练" if command == "exercise" else "挂起 worker 急停演练", fixture=True)
            self.service.transition(S.EXECUTING)
            self.worker = WorkerSupervisor(self.stop.event, test_mode=True)
            self.stop.own(self.worker)
            try:
                self.worker.start(task.id, task.generation)
            except RuntimeError:
                if not self.stop.event.is_set():
                    raise
            deadline = time.monotonic() + 10
            while not self.worker.ready.is_set() and not self.stop.event.is_set():
                if time.monotonic() >= deadline:
                    self.stop.trip()
                    break
                self.stop.event.wait(.025)
            if self.stop.event.is_set():
                self.worker.close()
                self.service.cancel()
                self._snapshot()
                return True
            if command == "hang":
                try:
                    self.worker.send("hang")
                except ValueError:
                    if not self.stop.event.is_set():
                        raise
                    self.service.cancel()
            else:
                self.expected = self.backend.value + 1
                self.gateway.observe(self.backend.observe(self.service.clock))
                self.action = FixtureAction(task_id=task.id, generation=task.generation)
                self.gateway.propose(self.action)
        elif command in {"approve", "deny"}:
            self.gateway.observe(self.backend.observe(self.service.clock))
            permit = self.gateway.decide(UUID(value), allow=command == "approve", authority=self.authority)
            if permit:
                result = self.gateway.dispatch(permit.id, self.action)
                if result.status == "ok" and self.service.task.status == S.EXECUTING:
                    self.service.finish([self.backend.verify(self.service.task, self.expected)])
            if self.worker:
                self.worker.close()
        elif command in {"pause", "voice_pause"}:
            if command == "voice_pause" and (not self.service.task or self.service.task.status in TERMINAL or self.service.task.status == S.PAUSED):
                self._snapshot()
                return True
            self.service.pause()
            if self.worker:
                self.worker.close()
            self.service.pause_acknowledged()
        elif command == "resume":
            self.service.resume(self.backend.observe(self.service.clock))
            # A paused test proposal is never replayed; a new exercise is required.
            self.service.transition(S.FAILED, error_code="M1_REPLAN_NOT_CONNECTED")
        elif command == "reset":
            if self.service.task and self.service.task.status not in TERMINAL:
                raise Busy("当前任务尚未停止")
            self.stop.reset()
            self.service.reset_stop()
        elif command == "details":
            events = self.service.store.events(UUID(value))
            approvals = self.service.store.approvals(UUID(value))
            self.signals.details.emit({"events": [e.model_dump(mode="json") for e in events],
                                      "approvals": [a.model_dump(mode="json") for a in approvals]})
        self._snapshot()
        return True

    def run(self) -> None:
        """Own all database work; on failure trip the independent latch and report a safe error."""
        store = None
        try:
            store = Store(self.data_dir / ("state-test.db" if self.test_mode else "state.db"))
            self.service = TaskService(store, stop=self.stop.event)
            self.backend = FixtureBackend()
            self.gateway = ToolGateway(self.service, Policy(), self.authority, self.backend if self.test_mode else None)
            from .native_tasks import NativeTasks
            self.native_tasks = NativeTasks(self.service, self.stop, self.hotkey)
            self.service.subscribers.append(self._published)
            self.ready.set()
            self._snapshot()
            running = True
            while running:
                old = self.service.task
                if self.worker and self.worker.failure and old and old.status not in TERMINAL:
                    self.service.transition(S.INTERRUPTED, error_code=self.worker.failure)
                self.service.check_timeouts()
                if self.service.task is not old:
                    if self.service.task and self.service.task.status in TERMINAL:
                        with self._request_lock:
                            self._task_reserved = False
                    self._snapshot()
                try:
                    command, value = self.commands.get(timeout=0.1)
                except queue.Empty:
                    continue
                try:
                    previous = self.service.task
                    running = self._handle(command, value)
                except (Busy, InvalidTransition, PolicyDenied, ValueError) as exc:
                    self.signals.error.emit(str(exc))
                    self._snapshot()
                finally:
                    ended = self.service.task is None or self.service.task.status in TERMINAL
                    if ended and (command in {"record", "exercise", "hang", "voice_final"} or (previous and previous.status not in TERMINAL)):
                        with self._request_lock:
                            self._task_reserved = False
        except (sqlite3.Error, OSError, RuntimeError) as exc:
            self.last_error = type(exc).__name__
            self.stop.trip()
            self.signals.error.emit("控制器已停止：" + self.last_error + "。请检查诊断与数据目录。")
        finally:
            if self.worker:
                self.worker.close()
            if store:
                store.close()
            self.closed.set()

    def close(self) -> None:
        """Stop immediately, then ask the writer to persist cancellation and close."""
        self.stop.trip()
        self.submit("exit")
        self.join(timeout=3)
