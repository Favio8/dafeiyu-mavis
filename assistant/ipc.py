"""Private parent/child stdio pipes: bounded JSON, no listener, pickle or dynamic code."""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
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
    kind: Literal["hello", "ready", "ping", "pong", "hang", "crash", "stop", "error", "voice_config", "voice_listen", "voice_record", "voice_end", "voice_cancel", "voice_speak", "voice_mute", "voice_event"]
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

    def __init__(self, stop: threading.Event, *, on_message=None, test_mode: bool = False):
        self.stop = stop
        self.on_message = on_message or (lambda message: None)
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

    def start(self, task_id: UUID | None = None, generation: int = 1) -> None:
        """Start a fixed module with private stdio handles and no inherited API credentials."""
        with self._guard:
            if self.process is not None or self.stop.is_set():
                raise RuntimeError("worker already started or stop latch set")
            self.task_id, self.generation, self.session = task_id or uuid4(), generation, secrets.token_hex(32)
            env = {k: v for k, v in os.environ.items() if k.upper() in {
                "SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "LOCALAPPDATA", "APPDATA", "USERPROFILE"}}
            env.update(PYTHONUTF8="1", ANONYMIZED_TELEMETRY="false")
            command = [sys.executable, "-m", self.MODULE]
            if self.test_mode:
                command.append("--test-mode")
            self.process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1], env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0, bufsize=0)
            self.reader = threading.Thread(target=self._read, name="mavis-ipc", daemon=True)
            self.reader.start()
        self.send("hello")

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
                    self.peer_pid = int(message.payload)
                    self.ready.set()
                self.on_message(message)
        except (OSError, ProtocolError, ValueError):
            self.failure = "IPC_REJECTED"
        finally:
            if not self.intentional:
                self.failure = self.failure or "WORKER_EXITED"
                self.stop.set()
                self.terminate()
            self.ended.set()

    def terminate(self) -> None:
        """Terminate only the stored child process handle, never user applications."""
        with self._guard:
            self.intentional = True
            process = self.process
            if process is None:
                return
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=0.25)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=0.25)
            if process.stdin:
                process.stdin.close()

    def close(self) -> None:
        """Reap the child and reader; called during host shutdown."""
        self.terminate()
        if self.reader and self.reader is not threading.current_thread():
            self.reader.join(timeout=1)
        if self.process and self.process.stdout:
            self.process.stdout.close()
