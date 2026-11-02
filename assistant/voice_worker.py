"""Fixed private-pipe audio worker: Qt capture, local engines and half-duplex SAPI."""
from __future__ import annotations

import json
from pathlib import Path
import queue
import sys
import threading
import time

from .ipc import MAX_MESSAGE, Message, Receiver, decode, encode, ProtocolError


def main():
    from pet.qt_plugin_sanitizer import sanitize_plugin_path
    sanitize_plugin_path()
    from PySide6.QtCore import QCoreApplication, QTimer
    from PySide6.QtMultimedia import QAudioSource, QAudioFormat, QMediaDevices, QAudio
    import numpy as np
    import pythoncom
    from .voice_audio import PCMConverter
    from .voice_tts import LocalSpeech, voices
    from .voice_engine import VoiceEngine
    pythoncom.CoInitialize()
    app = QCoreApplication([])
    first = decode(sys.stdin.buffer.readline(MAX_MESSAGE+1))
    if first.kind != "hello" or first.role != "host" or first.seq != 1:
        return 2
    receiver = Receiver(first.session, "host", first.task_id, first.generation)
    receiver.accept(encode(first))
    commands = queue.Queue(maxsize=32)
    seq, epoch = 0, 0

    def reply(kind, payload=""):
        nonlocal seq
        seq += 1
        sys.stdout.buffer.write(encode(Message(session=first.session, role="worker", seq=seq, task_id=first.task_id, generation=first.generation, kind=kind, payload=payload)))
        sys.stdout.buffer.flush()

    def emit(kind, value):
        reply("voice_event", json.dumps({"event": kind, "epoch": epoch, **value}, ensure_ascii=False))

    def read():
        try:
            while data := sys.stdin.buffer.readline(MAX_MESSAGE+1):
                commands.put(receiver.accept(data), timeout=1)
        except (OSError, ProtocolError, ValueError, queue.Full):
            pass
        commands.put(None)

    threading.Thread(target=read, name="mavis-voice-pipe", daemon=True).start()
    reply("ready", str(__import__("os").getpid()))
    engine, source, io, converter = None, None, None, None
    config = {}
    desired, manual = False, False
    speech = LocalSpeech()
    cooldown = None
    media = QMediaDevices()

    def devices():
        emit("devices", {"devices": [{"id": bytes(d.id()).hex(), "name": d.description(), "default": d.isDefault()} for d in QMediaDevices.audioInputs()]})

    def close_audio():
        nonlocal source, io, converter
        if source:
            source.stop()
            source.deleteLater()
        source, io, converter = None, None, None
        if engine:
            engine.reset()

    def open_audio():
        nonlocal source, io, converter, engine
        close_audio()
        available = QMediaDevices.audioInputs()
        device_id = config.get("device", "")
        device = next((d for d in available if bytes(d.id()).hex() == device_id), None) if device_id else QMediaDevices.defaultAudioInput()
        if device is None or device.isNull():
            raise ValueError("MICROPHONE_UNAVAILABLE")
        if not engine:
            emit("state", {"state": "LOADING"})
            engine = VoiceEngine(Path(config["root"]), emit, word=config["word"], sensitivity=config["sensitivity"])
        fmt = QAudioFormat()
        fmt.setSampleRate(16000)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not device.isFormatSupported(fmt):
            fmt = device.preferredFormat()
        kind = fmt.sampleFormat().name
        converter = PCMConverter(fmt.sampleRate(), fmt.channelCount(), kind)
        source = QAudioSource(device, fmt)
        source.setBufferSize(fmt.bytesForDuration(300000))
        io = source.start()
        if source.error() != QAudio.Error.NoError or io is None:
            close_audio()
            raise ValueError("MICROPHONE_OPEN_FAILED_CHECK_WINDOWS_PRIVACY")
        emit("capture", {"open": True, "rate": fmt.sampleRate(), "channels": fmt.channelCount(), "format": kind})

    def stop_listening():
        close_audio()
        if engine:
            engine.off()
        else:
            emit("state", {"state": "OFF"})
        emit("capture", {"open": False, "buffer_samples": 0})

    def inputs_changed():
        nonlocal desired, manual
        devices()
        if source:
            stop_listening()
            desired, manual = False, False
            emit("error", {"code": "INPUT_DEVICE_CHANGED_RESELECT_AND_ENABLE"})
    media.audioInputsChanged.connect(inputs_changed)
    devices()
    try:
        emit("voices", {"voices": voices()})
    except pythoncom.com_error:
        emit("voices", {"voices": [], "error": "LOCAL_TTS_UNAVAILABLE"})

    def tick():
        nonlocal config, epoch, engine, desired, manual, cooldown
        try:
            for _ in range(4):
                try:
                    message = commands.get_nowait()
                except queue.Empty:
                    break
                if message is None or message.kind == "stop":
                    app.quit()
                    return
                value = json.loads(message.payload or "{}")
                incoming = value.pop("epoch", epoch)
                if incoming < epoch:
                    continue
                epoch = incoming
                if message.kind == "voice_config":
                    if source or speech.active:
                        raise ValueError("FINISH_RECORDING_OR_PLAYBACK_BEFORE_CONFIGURE")
                    if engine and (value["word"], value["sensitivity"]) != (config.get("word"), config.get("sensitivity")):
                        engine.configure(value["word"], value["sensitivity"])
                    config = value
                    emit("configured", {"word": config["word"], "sensitivity": config["sensitivity"]})
                elif message.kind == "voice_listen":
                    desired = bool(value["enabled"])
                    if not desired:
                        manual = False
                        stop_listening()
                        if speech.active or cooldown is not None:
                            emit("state", {"state": "PLAYBACK_GUARD"})
                    elif not speech.active and cooldown is None:
                        open_audio()
                        engine.arm()
                elif message.kind == "voice_record":
                    if speech.active or cooldown is not None:
                        raise ValueError("PLAYBACK_GUARD")
                    open_audio()
                    manual = True
                    engine.start_manual(value.get("trigger", "button"))
                elif message.kind == "voice_end":
                    if engine:
                        engine.finish()
                elif message.kind == "voice_cancel":
                    if engine:
                        if engine.state == "CAPTURING":
                            engine.cancel()
                        else:
                            engine.reset()
                elif message.kind == "voice_speak":
                    close_audio()
                    if engine:
                        engine.guard()
                    else:
                        emit("state", {"state": "PLAYBACK_GUARD"})
                    emit("capture", {"open": False, "buffer_samples": 0})
                    speech.start(value["text"], voice_id=config.get("voice", ""), volume=config.get("volume", 70))
                    cooldown = float("inf")
                elif message.kind == "voice_mute":
                    speech.stop()
                elif message.kind == "ping":
                    reply("pong")
                else:
                    raise ProtocolError("unknown voice host command")
            if source:
                if source.error() != QAudio.Error.NoError:
                    raise ValueError("MICROPHONE_DEVICE_ERROR")
                raw = bytes(io.readAll())
                if raw:
                    audio = converter.convert(raw)
                    if len(audio):
                        emit("level", {"level": min(1.0, float(np.sqrt(np.mean(audio**2))))})
                        engine.feed(audio)
            if manual and engine and engine.state == "ARMED":
                manual = False
                if not desired:
                    stop_listening()
            if cooldown is not None and not speech.active:
                if cooldown == float("inf"):
                    cooldown = time.monotonic() + .7
                    emit("playback_end", {"error": speech.error})
                elif time.monotonic() >= cooldown:
                    cooldown = None
                    if desired:
                        open_audio()
                        engine.arm()
                    else:
                        stop_listening()
        except (ValueError, RuntimeError, OSError, ProtocolError) as exc:
            desired, manual = False, False
            stop_listening()
            emit("error", {"code": str(exc)[:150]})
    timer = QTimer()
    timer.setInterval(50)
    timer.timeout.connect(tick)
    timer.start()
    try:
        return app.exec()
    finally:
        close_audio()
        speech.stop()
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ProtocolError, OSError, ValueError):
        raise SystemExit(2)
