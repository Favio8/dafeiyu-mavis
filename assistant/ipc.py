"""Private parent/child stdio pipes: bounded JSON, no listener, pickle or dynamic code."""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import ctypes
from ctypes import wintypes
import psutil
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, ValidationError

from .contracts import Record

MAX_MESSAGE = 65536


class ProtocolError(ValueError):
    """Invalid/oversized/unauthenticated/replayed IPC message."""


class Message(Record):
    """Closed protocol: worker cannot approve, change policy, or declare task success."""
    version: Literal[1] = 1
    session: str = Field(min_length=64, max_length=64, pattern="^[0-9a-f]+$")
    role: Literal["host", "worker"]
    seq: int = Field(ge=1)
    task_id: UUID
    generation: int = Field(ge=1)
    kind: Literal["hello", "ready", "ping", "pong", "hang", "crash", "stop", "error", "voice_config", "voice_listen", "voice_record", "voice_end", "voice_cancel", "voice_speak", "voice_mute", "voice_event", "native_request", "native_event", "model_probe", "model_result"]
    payload: str = Field(default="", max_length=8000)


def encode(message: Message) -> bytes:
    """Encode one newline-delimited JSON frame, refusing anything beyond the byte budget."""
    data = message.model_dump_json().encode("utf-8") + b"\n"
    if len(data) > MAX_MESSAGE:
        raise ProtocolError("message too large")
    return data


def decode(data: bytes) -> Message:
    """Validate before acting; no interpretation of payload as executable instructions."""
    if not data or len(data) > MAX_MESSAGE or not data.endswith(b"\n"):
        raise ProtocolError("missing or oversized frame")
    try:
        return Message.model_validate_json(data)
    except ValidationError as exc:
        raise ProtocolError("invalid IPC schema") from exc


class Receiver:
    """Per-direction strict sequencing and identity check."""
    def __init__(self, session: str, role: str, task_id: UUID, generation: int):
        self.session, self.role, self.task_id, self.generation = session, role, task_id, generation
        self.seq = 0

    def accept(self, data: bytes) -> Message:
        """Reject duplicates, gaps, forged identities and generation changes."""
        message = decode(data)
        if (not secrets.compare_digest(message.session, self.session) or message.role != self.role
            or message.task_id != self.task_id or message.generation != self.generation or message.seq != self.seq + 1):
            raise ProtocolError("identity or sequence mismatch")
        self.seq = message.seq
        return message


class WorkerSupervisor:
    """Own exactly one fixed worker process, reclaimable without waiting on its requests."""
    MODULE = "assistant.worker"
    HOST_KINDS = {"hello", "ping", "stop"}
    WORKER_KINDS = {"ready", "pong", "error"}

    def __init__(self, stop: threading.Event, *, on_message=None, on_failure=None, test_mode: bool = False):
        self.stop = stop
        self.on_message = on_message or (lambda message: None)
        self.on_failure = on_failure
        self.test_mode = test_mode
        self.process: subprocess.Popen | None = None
        self._guard = threading.RLock()
        self._send_lock = threading.Lock()
        self.ready = threading.Event()
        self.ended = threading.Event()
        self.intentional = False
        self.failure: str | None = None
        self.reader: threading.Thread | None = None
        self.seq = 0
        self.peer_pid: int | None = None
        self.peer_handle = None
        self._kernel = None
        self.launcher_birth = None

    def _bind_peer(self, pid):
        peer = psutil.Process(pid)
        if pid != self.process.pid and self.process.pid not in {p.pid for p in peer.parents()}:
            raise ProtocolError("worker PID is not our descendant")
        allowed = {Path(sys.executable).resolve(), Path(getattr(sys,"_base_executable",sys.executable)).resolve()}
        if Path(peer.exe()).resolve() not in allowed:
            raise ProtocolError("worker executable identity mismatch")
        if os.name == "nt":
            kernel = ctypes.WinDLL("kernel32",use_last_error=True)
            kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
            kernel.OpenProcess.restype=wintypes.HANDLE
            kernel.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)]
            kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
            kernel.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT]
            kernel.CloseHandle.argtypes=[wintypes.HANDLE]
            handle=kernel.OpenProcess(0x101001,False,pid)
            if not handle:
                raise ProtocolError("worker process handle unavailable")
            stamps=[wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(handle,*[ctypes.byref(stamp) for stamp in stamps]):
                kernel.CloseHandle(handle)
                raise ProtocolError("worker birth unavailable")
            born=((stamps[0].dwHighDateTime<<32)|stamps[0].dwLowDateTime)/10000000-11644473600
            if abs(born-peer.create_time())>.0001:
                kernel.CloseHandle(handle)
                raise ProtocolError("worker PID reused")
            self._kernel,self.peer_handle=kernel,handle
        self.peer_pid=pid

    def actual_exited(self):
        if self.peer_handle:
            return self._kernel.WaitForSingleObject(self.peer_handle,0)==0
        return self.process is None or self.process.poll() is not None

    def start(self, task_id: UUID | None = None, generation: int = 1) -> None:
        """Start a fixed module with private stdio handles and no inherited API credentials."""
        with self._guard:
            if self.process is not None or self.stop.is_set():
                raise RuntimeError("worker already started or stop latch set")
            self.task_id, self.generation, self.session = task_id or uuid4(), generation, secrets.token_hex(32)
            env = {k: v for k, v in os.environ.items() if k.upper() in {
                "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "PATH", "TEMP", "TMP", "LOCALAPPDATA", "APPDATA", "USERPROFILE"}}
            env.update(PYTHONUTF8="1", ANONYMIZED_TELEMETRY="false")
            command = [sys.executable, "-m", self.MODULE]
            if self.test_mode:
                command.append("--test-mode")
            self.process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1], env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0, bufsize=0)
            try:
                self.launcher_birth = psutil.Process(self.process.pid).create_time()
            except psutil.Error:
                self.intentional=True
                self.process.wait(timeout=.25)
                raise RuntimeError("WORKER_BOOTSTRAP_EXITED") from None
            self.reader = threading.Thread(target=self._read, name="mavis-ipc", daemon=True)
            self.reader.start()
        self.send("hello", self.bootstrap())

    def bootstrap(self):
        return ""

    def send(self, kind: str, payload: str = "") -> None:
        """Write a typed request. This can block only the controller, never the watchdog."""
        if kind not in self.HOST_KINDS and not (self.test_mode and kind in {"hang", "crash"}):
            raise ProtocolError("host command not allowed")
        with self._send_lock:
            if self.process is None or self.process.poll() is not None or self.stop.is_set():
                raise ProtocolError("worker unavailable")
            self.seq += 1
            message = Message(session=self.session, role="host", seq=self.seq, task_id=self.task_id,
                              generation=self.generation, kind=kind, payload=payload)
            self.process.stdin.write(encode(message))
            self.process.stdin.flush()

    def _read(self) -> None:
        receiver = Receiver(self.session, "worker", self.task_id, self.generation)
        try:
            while True:
                data = self.process.stdout.readline(MAX_MESSAGE + 1)
                if not data:
                    break
                message = receiver.accept(data)
                if message.kind not in self.WORKER_KINDS:
                    raise ProtocolError("worker command not allowed")
                if message.kind == "ready":
                    if self.ready.is_set() or not message.payload.isdecimal() or int(message.payload) <= 0:
                        raise ProtocolError("invalid worker readiness")
                    with self._guard:
                        if self.intentional:
                            break
                        self._bind_peer(int(message.payload))
                        self.ready.set()
                self.on_message(message)
        except (OSError, ProtocolError, ValueError, psutil.Error):
            self.failure = "IPC_REJECTED"
        finally:
            try:
                if not self.intentional:
                    self.failure = self.failure or "WORKER_EXITED"
                    self.stop.set()
                    try:
                        self.terminate()
                    finally:
                        if self.on_failure:
                            self.on_failure()
            finally:
                self.ended.set()

    def terminate(self) -> None:
        """Terminate only the stored child process handle, never user applications."""
        with self._guard:
            self.intentional = True
            process = self.process
            if process is None:
                return
            if self.peer_handle and not self.actual_exited():
                self._kernel.TerminateProcess(self.peer_handle,1)
                if self._kernel.WaitForSingleObject(self.peer_handle,250)!=0:
                    raise RuntimeError("ACTUAL_WORKER_DID_NOT_EXIT")
            elif not self.ready.is_set() and process.poll() is None:
                # No tool can run before ready. During venv bootstrap only our
                # fixed Python worker descendants exist, not user applications.
                try:
                    launcher=psutil.Process(process.pid)
                    children=launcher.children(recursive=True) if launcher.create_time()==self.launcher_birth else []
                except psutil.Error:
                    children=[]
                for child in reversed(children):
                    try:
                        if Path(child.exe()).resolve() in {Path(sys.executable).resolve(),Path(getattr(sys,"_base_executable",sys.executable)).resolve()}:
                            child.terminate()
                            child.wait(timeout=.25)
                    except psutil.NoSuchProcess:
                        pass
                    except psutil.Error:
                        raise RuntimeError("BOOTSTRAP_WORKER_DID_NOT_EXIT") from None
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=0.25)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=0.25)
            if process.stdin:
                try:
                    process.stdin.close()
                except OSError:
                    pass  # already-closed private pipe, not an input resource

    def close(self) -> None:
        """Reap the child and reader; called during host shutdown."""
        self.terminate()
        if self.reader and self.reader is not threading.current_thread():
            self.reader.join(timeout=1)
        if self.process and self.process.stdout:
            self.process.stdout.close()
        with self._guard:
            if self.peer_handle:
                self._kernel.CloseHandle(self.peer_handle)
                self.peer_handle=None
