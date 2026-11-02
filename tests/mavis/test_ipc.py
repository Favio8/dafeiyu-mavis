"""Real private-pipe worker tests; injected Windows messages never type into user apps."""
import ctypes
import threading
import time
from uuid import uuid4

import pytest
import psutil

from assistant.ipc import MAX_MESSAGE, Message, ProtocolError, Receiver, WorkerSupervisor, decode, encode
from assistant.stop import EmergencyHotkey, StopController


def test_ipc_auth_sequence_and_schema():
    message = Message(session="a" * 64, role="worker", seq=1, task_id=uuid4(), generation=1, kind="pong")
    receiver = Receiver(message.session, message.role, message.task_id, 1)
    assert receiver.accept(encode(message)) == message
    for bad in [encode(message), encode(message.model_copy(update={"seq": 3})), encode(message.model_copy(update={"seq": 2, "session": "b" * 64})),
                b"x" * (MAX_MESSAGE + 1), b'{"kind":"approve"}\n', b'\x80pickle\n']:
        with pytest.raises(ProtocolError):
            receiver.accept(bad)


def test_real_private_worker_roundtrip():
    stop = StopController()
    pong = threading.Event()
    worker = WorkerSupervisor(stop.event, on_message=lambda m: pong.set() if m.payload == "probe" else None)
    stop.own(worker)
    try:
        worker.start()
        assert worker.ready.wait(10)
        worker.send("ping", "probe")
        assert pong.wait(10)
        with pytest.raises(ProtocolError):
            worker.send("approve")
    finally:
        worker.close()
    assert worker.process.poll() is not None


@pytest.mark.parametrize("attempt", range(20))
def test_watchdog_kills_hung_worker_without_waiting_for_reply(attempt):
    stop = StopController()
    entered = threading.Event()
    worker = WorkerSupervisor(stop.event, test_mode=True, on_message=lambda m: entered.set() if m.payload == "hang-entered" else None)
    stop.own(worker)
    try:
        worker.start()
        assert worker.ready.wait(10)
        worker.send("hang")
        assert entered.wait(10)
        actual_worker = psutil.Process(worker.peer_pid)
        stop.trip()
        actual_worker.wait(timeout=1)
        assert stop.event.is_set() and worker.process.poll() is not None
        assert stop.last_stop_ms < 1000
    finally:
        worker.close()


def test_worker_crash_sets_latch():
    stop = StopController()
    worker = WorkerSupervisor(stop.event, test_mode=True)
    try:
        worker.start()
        assert worker.ready.wait(10)
        worker.send("crash")
        assert worker.ended.wait(10)
        assert stop.event.is_set() and worker.failure == "WORKER_EXITED"
    finally:
        worker.close()


@pytest.mark.skipif(__import__("os").name != "nt", reason="Windows hotkey API")
def test_os_hotkey_registration_conflict_and_message_dispatch():
    stop = StopController()
    first = EmergencyHotkey(stop)
    second = EmergencyHotkey(StopController())
    try:
        assert first.start(), first.error
        assert not second.start() and second.error.startswith("HOTKEY_UNAVAILABLE")
        assert ctypes.windll.user32.PostThreadMessageW(first.thread_id, 0x0312, first.HOTKEY_ID, 0)
        assert stop.event.wait(10)
    finally:
        second.close()
        first.close()
    assert not first.registered and not first.thread.is_alive()
