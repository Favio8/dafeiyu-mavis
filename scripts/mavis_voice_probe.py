"""Fixed SAPI fixtures through real KWS/VAD/ASR, then real local playback IPC.

This never claims microphone evidence and never enables desktop input.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import threading
import time
import wave
import sqlite3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", type=Path, default=Path(".scratch/m3/models"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    import numpy as np
    import win32com.client
    from assistant.voice_engine import VoiceEngine, normalize_voice_command
    from assistant.voice_host import VoiceProcess
    output = root / ".scratch/m3/evidence" / str(time.time_ns())
    output.mkdir(parents=True)
    from assistant.controller import Controller
    from assistant.stop import StopController
    controller = Controller(output / "profile", StopController(), test_mode=True)
    controller.start()
    if not controller.ready.wait(5):
        raise RuntimeError("CONTROLLER_START_TIMEOUT")
    events, cases = [], []
    engine = VoiceEngine(args.models.resolve(), lambda kind, data: events.append({"kind": kind, **data}))
    voice = win32com.client.Dispatch("SAPI.SpVoice")
    voice.Voice = next(item for item in voice.GetVoices() if "804" in item.GetAttribute("Language").split(";"))
    def fixture(text, index):
        path = output / f"synthetic-{index}.wav"
        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        stream.Format.Type = 18
        stream.Open(str(path), 3, False)
        voice.AudioOutputStream = stream
        voice.Speak(text)
        stream.Close()
        with wave.open(str(path)) as source:
            assert source.getframerate() == 16000 and source.getnchannels() == 1
            return np.frombuffer(source.readframes(source.getnframes()), dtype=np.int16).astype(np.float32)/32768
    started = time.monotonic()
    for index, (word, sentence, expected) in enumerate([
        ("大肥鱼", "大肥鱼帮我打开记事本", "打开记事本"),
        ("大肥鱼", "大肥鱼输入你好我是大肥鱼", "输入：你好我是大肥鱼"),
        ("大肥鱼", "大肥鱼", ""),
        ("小助手", "小助手帮我打开记事本", "打开记事本"),
    ]):
        engine.configure(word, "标准")
        engine.arm()
        events.clear()
        audio = fixture(sentence, index)
        padded = np.concatenate((np.zeros(8000, np.float32), audio, np.zeros(40000, np.float32)))
        for pos in range(0, len(padded), 1600):
            engine.feed(padded[pos:pos+1600])
        finals = [e for e in events if e["kind"] == "final"]
        actual = normalize_voice_command(finals[0]["text"]) if finals else ""
        if finals:
            previous_id = controller.service.task.id if controller.service.task else None
            controller.accept_voice(finals[0])
            until = time.monotonic()+5
            while time.monotonic() < until:
                current = controller.service.task
                if current and current.id != previous_id and current.status == "FAILED" and not controller._task_reserved:
                    break
                time.sleep(.025)
            else:
                raise RuntimeError("ASR_TO_SHARED_TASK_TIMEOUT")
        cases.append({"word": word, "spoken_fixture": sentence, "source": "local SAPI synthesized waveform, not microphone", "expected": expected, "actual": actual, "events": list(events), "passed": actual == expected and len(finals) <= 1})
    # A guard feed must not enter KWS, even with a clearly positive waveform.
    engine.guard()
    events.clear()
    audio = fixture("小助手帮我打开记事本", "guard")
    for pos in range(0, len(audio), 1600):
        engine.feed(audio[pos:pos+1600])
    guard_passed = not events and engine.state == "PLAYBACK_GUARD" and len(engine.ring) == 0

    ipc_events = []
    worker = VoiceProcess(threading.Event(), on_message=lambda message: ipc_events.append({"kind": message.kind, "payload": message.payload}))
    def wait(predicate, timeout=15):
        deadline = time.monotonic()+timeout
        while not predicate() and time.monotonic() < deadline:
            time.sleep(.025)
        if not predicate():
            raise RuntimeError("VOICE_PROBE_TIMEOUT")
    try:
        worker.start()
        wait(worker.ready.is_set)
        worker.send("voice_config", json.dumps({"root": str(args.models.resolve()), "word": "大肥鱼", "sensitivity": "标准", "device": "", "volume": 50, "epoch": 1}))
        # Actual audible local playback, while the original listening preference is OFF.
        worker.send("voice_speak", json.dumps({"text": "大肥鱼，语音播报测试。", "epoch": 2}, ensure_ascii=False))
        def parsed():
            return [json.loads(e["payload"]) for e in ipc_events if e["kind"] == "voice_event"]
        wait(lambda: any(e.get("event") == "playback_end" for e in parsed()))
        wait(lambda: any(e.get("event") == "state" and e.get("state") == "OFF" and e.get("epoch") == 2 for e in parsed()))
        worker.send("voice_listen", json.dumps({"enabled": True, "epoch": 3}))
        wait(lambda: any(e.get("epoch") == 3 and (e.get("event") == "error" or e.get("state") == "ARMED") for e in parsed()))
        worker.send("voice_listen", json.dumps({"enabled": False, "epoch": 4}))
        wait(lambda: any(e.get("epoch") == 4 and e.get("event") == "capture" and not e["open"] for e in parsed()))
        native = parsed()
    finally:
        worker.close()
        controller.close()
    with sqlite3.connect(output / "profile/state-test.db") as db:
        tasks = [json.loads(row[0]) for row in db.execute("SELECT data FROM tasks ORDER BY created")]
    shared_path = len(tasks) == 3 and all(t["source"] == "voice" and t["action_count"] == 0 and t["error_code"] == "COMPUTER_CONTROL_DISABLED" for t in tasks)
    result = {"source": "real local model inference plus native SAPI playback/Qt device discovery; no human microphone input", "cases": cases,
        "playback_guard_positive_fixture_blocked": guard_passed, "worker_events": native,
        "shared_controller_voice_tasks": [{k: t[k] for k in ("id", "source", "original_text", "final_text", "status", "action_count", "error_code")} for t in tasks],
        "real_asr_to_shared_task_gate_passed": shared_path,
        "owned_process_exited": worker.process.poll() is not None, "elapsed_s": round(time.monotonic()-started, 3),
        "microphone_physical_release": "pending unless capture.open=true occurred; no-input cleanup is not physical release proof",
        "passed": all(case["passed"] for case in cases) and guard_passed and shared_path and worker.process.poll() is not None}
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "cases": [{k: c[k] for k in ("expected", "actual", "passed")} for c in cases], "evidence": str(output)}, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
