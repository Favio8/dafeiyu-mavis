"""Installed-only diagnostics. No shell, model tool registration or GUI input."""
from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import json
import re
import secrets
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from uuid import uuid4


def runtime() -> dict:
    from . import __version__
    from .ipc import WorkerSupervisor
    from .stop import StopController, EmergencyHotkey
    from .native_session import NativeSession
    from .voice_tts import voices
    from PySide6.QtMultimedia import QMediaDevices
    from PySide6.QtCore import QCoreApplication
    app = QCoreApplication.instance() or QCoreApplication([])
    stop = StopController()
    pong = threading.Event()
    worker = WorkerSupervisor(stop.event, on_message=lambda m: pong.set() if m.kind == "pong" else None)
    stop.own(worker)
    native = None
    hotkey = EmergencyHotkey(stop, "Ctrl+Alt+F9")
    try:
        worker.start()
        if not worker.ready.wait(10):
            raise RuntimeError("INSTALLED_WORKER_NOT_READY")
        worker.send("ping", "installed-probe")
        if not pong.wait(5):
            raise RuntimeError("INSTALLED_WORKER_NO_REPLY")
        worker.close()
        if not hotkey.start():
            raise RuntimeError(hotkey.error)
        native = NativeSession(stop, hotkey)
        native.open(SimpleNamespace(id=uuid4(), generation=1))
        native.close()
        available = voices()
        device_count = len(QMediaDevices.audioInputs())
        return {"passed": True, "frozen": bool(getattr(sys, "frozen", False)), "version": __version__,
                "dependencies": {name: importlib.metadata.version(name) for name in ("PySide6", "sherpa-onnx", "keyring", "comtypes", "pydantic", "aiohttp")},
                "private_worker_roundtrip": True, "native_worker_ready_and_exited": native.actual_exited(),
                "voice_count": len(available), "microphone_count": device_count,
                "microphone_acceptance": "pending", "input_dispatched": False,
                "application": app.applicationName()}
    finally:
        if native:
            native.close()
        worker.close()
        hotkey.close()


def vault(args) -> dict:
    from .credentials import Credentials
    credentials = Credentials()
    if args.probe == "vault-read":
        if not args.ref or not args.ref.startswith("probe/"):
            raise ValueError("PROBE_REFERENCE_REQUIRED")
        value = credentials.read(args.ref)
        return {"passed": bool(value), "marker_digest": hashlib.sha256(value.encode()).hexdigest() if value else None}
    marker, ref = secrets.token_urlsafe(24), "probe/"+uuid4().hex
    credentials.save(ref, marker)
    try:
        result = subprocess.run([sys.executable, "--probe", "vault-read", "--ref", ref], capture_output=True, text=True, encoding="utf-8", timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        child = json.loads(result.stdout)
        passed = result.returncode == 0 and child["marker_digest"] == hashlib.sha256(marker.encode()).hexdigest()
    finally:
        credentials.delete(ref)
    removed = credentials.read(ref) is None
    return {"passed": passed and removed, "backend": type(credentials.backend).__name__,
            "cross_process_roundtrip": passed, "temporary_marker_removed": removed,
            "configured_deepseek_credential_present": bool(credentials.read("deepseek/default")),
            "real_key_modified": False}


def voice(args) -> dict:
    if args.models is None or args.output is None:
        raise ValueError("VOICE_PROBE_REQUIRES_MODELS_AND_OUTPUT")
    import numpy as np
    import pythoncom
    import win32com.client
    import wave
    from .voice_models import ModelManager
    from .voice_engine import VoiceEngine
    ModelManager(args.models).verify()
    pythoncom.CoInitialize()
    path = args.output.with_suffix(".synthetic.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError("VOICE_PROBE_OUTPUT_EXISTS")
    speaker = win32com.client.Dispatch("SAPI.SpVoice")
    selected = next((v for v in speaker.GetVoices() if "804" in v.GetAttribute("Language").lower().split(";")), None)
    if selected:
        speaker.Voice = selected
    stream = win32com.client.Dispatch("SAPI.SpFileStream")
    stream.Format.Type = 18
    stream.Open(str(path.resolve()), 3)
    speaker.AudioOutputStream = stream
    speaker.Speak("大肥鱼，打开记事本")
    stream.Close()
    pythoncom.CoUninitialize()
    with wave.open(str(path), "rb") as audio:
        rate, channels, width = audio.getframerate(), audio.getnchannels(), audio.getsampwidth()
        if width != 2 or channels != 1:
            raise ValueError("SYNTHETIC_WAVE_FORMAT_UNSUPPORTED")
        data = np.frombuffer(audio.readframes(audio.getnframes()), dtype=np.int16).astype(np.float32)/32768
    if rate != 16000:
        data = np.interp(np.arange(round(len(data)*16000/rate))*rate/16000, np.arange(len(data)), data).astype(np.float32)
    events = []
    engine = VoiceEngine(args.models, lambda kind, fields: events.append({"event": kind, **fields}))
    engine.arm()
    sequence = np.concatenate([np.zeros(8000, np.float32), data, np.zeros(32000, np.float32)])
    for start in range(0, len(sequence), 1600):
        engine.feed(sequence[start:start+1600])
    engine.finish()
    return {"passed": any(e["event"] == "final" and e.get("text") == "打开记事本" for e in events), "models_loaded": True,
            "source": "local SAPI synthetic wave, not microphone", "events": events,
            "real_voice_benchmark": "pending", "task_execution": False}


def provider(args) -> dict:
    if not args.allow_network:
        return {"passed": False, "error": "NETWORK_PROBE_NOT_AUTHORIZED"}
    from .credentials import Credentials
    from .model_diagnostics import probe
    from .provider import DeepSeekProvider, ProviderSettings
    key = Credentials().read("deepseek/default")
    if not key:
        return {"passed": False, "error": "CREDENTIAL_MISSING"}
    settings = ProviderSettings()
    client = DeepSeekProvider(settings, key)
    results = {}
    for kind in ("connection", "tools"):
        try:
            results[kind] = asyncio.run(probe(client, kind, threading.Event()))
        except (ValueError, RuntimeError, OSError) as error:
            results[kind] = {"passed": False, "code": str(error) if str(error).isupper() else type(error).__name__}
    return {"passed": all(r.get("passed", False) for r in results.values()), "model": settings.model, "checks": results, "desktop_actions": 0}


def uia(args) -> dict:
    """Independent COM read of a specific benchmark-owned editor; no input methods."""
    from .contracts import Observation
    from .windows_observer import observe_window
    from .policy import digest
    import win32gui
    import comtypes
    import comtypes.client
    target = Observation.model_validate_json(args.target)
    actual = observe_window(target.hwnd)
    if actual.identity_digest != target.identity_digest or actual.app != "notepad.exe" or actual.integrity != "medium":
        raise ValueError("ORACLE_WINDOW_CHANGED")
    if target.document_digest and digest(win32gui.GetWindowText(target.hwnd).removeprefix("*")) != target.document_digest:
        raise ValueError("ORACLE_DOCUMENT_CHANGED")
    comtypes.CoInitialize()
    try:
        types = comtypes.client.GetModule("UIAutomationCore.dll")
        automation = comtypes.client.CreateObject("{ff48dba4-60ef-4201-aa87-54103eef594e}", interface=types.IUIAutomation)
        root = automation.ElementFromHandle(target.hwnd)
        condition = automation.CreateOrCondition(automation.CreatePropertyCondition(30003, 50004), automation.CreatePropertyCondition(30003, 50030))
        elements = root.FindAll(4, condition)
        candidates = [elements.GetElement(i) for i in range(elements.Length)]
        candidates = [e for e in candidates if e.CurrentProcessId == target.pid and not e.CurrentIsOffscreen and not e.CurrentIsPassword and (e.CurrentClassName in {"RichEditD2DPT", "NotepadTextBox", "Edit"})]
        if len(candidates) != 1:
            raise ValueError("ORACLE_EDITOR_NOT_UNIQUE")
        try:
            value = candidates[0].GetCurrentPattern(10002).QueryInterface(types.IUIAutomationValuePattern).CurrentValue
            pattern_kind = "value"
        except comtypes.COMError:
            value = candidates[0].GetCurrentPattern(10014).QueryInterface(types.IUIAutomationTextPattern).DocumentRange.GetText(4097)
            pattern_kind = "text"
        if len(value) > 4096 or observe_window(target.hwnd).identity_digest != target.identity_digest:
            raise ValueError("ORACLE_READ_OUT_OF_SCOPE")
        return {"passed": True, "text": value, "pattern": pattern_kind, "method": "independent COM UIA read; no trimming", "input_dispatched": False}
    finally:
        comtypes.CoUninitialize()


def run(args) -> dict:
    started = time.monotonic()
    try:
        report = {"runtime": runtime, "vault": lambda: vault(args), "vault-read": lambda: vault(args),
                  "voice": lambda: voice(args), "provider": lambda: provider(args), "uia": lambda: uia(args)}[args.probe]()
    except Exception as error:
        # Diagnostic exceptions are not user-facing raw OS paths or vault values.
        report = {"passed": False, "error": type(error).__name__, "code": str(error) if re.fullmatch(r"[A-Z][A-Z0-9_]{1,100}", str(error)) else "PROBE_FAILED"}
    return {"probe": args.probe, "frozen": bool(getattr(sys, "frozen", False)), "elapsed_s": time.monotonic()-started, **report}
