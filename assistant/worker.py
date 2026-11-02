"""M1 lifecycle worker. It has no model, microphone or desktop-input imports."""
import sys
import os
import threading

from .ipc import MAX_MESSAGE, Message, ProtocolError, Receiver, decode, encode


def main() -> int:
    """Read a host bootstrap over an inherited private pipe and handle closed commands."""
    first = decode(sys.stdin.buffer.readline(MAX_MESSAGE + 1))
    if first.kind != "hello" or first.role != "host" or first.seq != 1:
        return 2
    receiver = Receiver(first.session, "host", first.task_id, first.generation)
    receiver.accept(encode(first))
    seq = 0

    def reply(kind: str, payload: str = "") -> None:
        nonlocal seq
        seq += 1
        sys.stdout.buffer.write(encode(Message(session=first.session, role="worker", seq=seq,
            task_id=first.task_id, generation=first.generation, kind=kind, payload=payload)))
        sys.stdout.buffer.flush()

    reply("ready", str(os.getpid()))
    while data := sys.stdin.buffer.readline(MAX_MESSAGE + 1):
        message = receiver.accept(data)
        if message.kind == "ping":
            reply("pong", message.payload)
        elif message.kind == "stop":
            return 0
        elif message.kind == "hang" and "--test-mode" in sys.argv:
            reply("pong", "hang-entered")
            threading.Event().wait()  # Fault fixture, killed by the independent watchdog.
        elif message.kind == "crash" and "--test-mode" in sys.argv:
            return 17
        else:
            raise ProtocolError("unsupported host command")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ProtocolError, OSError):
        raise SystemExit(2)
