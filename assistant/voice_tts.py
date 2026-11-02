"""Local SAPI voices and interruptible playback. No network TTS."""
from __future__ import annotations

import threading


def voices() -> list[dict]:
    import win32com.client
    speaker = win32com.client.Dispatch("SAPI.SpVoice")
    return [{"id": item.Id, "name": item.GetDescription(), "language": item.GetAttribute("Language")} for item in speaker.GetVoices()]


class LocalSpeech:
    def __init__(self):
        self.cancelled = threading.Event()
        self.thread = None
        self.error = None

    def start(self, text: str, *, voice_id="", volume=70):
        self.stop()
        self.cancelled.clear()
        self.error = None
        self.thread = threading.Thread(target=self._run, args=(text[:300], voice_id, volume), name="mavis-local-tts", daemon=True)
        self.thread.start()

    def _run(self, text, voice_id, volume):
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        try:
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            available = list(speaker.GetVoices())
            selected = next((v for v in available if v.Id == voice_id), None)
            selected = selected or next((v for v in available if "804" in v.GetAttribute("Language").lower().split(";")), None)
            if not available:
                raise RuntimeError("LOCAL_TTS_UNAVAILABLE")
            if selected:
                speaker.Voice = selected
            speaker.Volume = max(0, min(100, volume))
            speaker.Speak(text, 1)  # asynchronous; this thread can purge it
            while not speaker.WaitUntilDone(30):
                if self.cancelled.is_set():
                    speaker.Speak("", 3)
                    break
        except (pythoncom.com_error, RuntimeError) as exc:
            self.error = type(exc).__name__
        finally:
            pythoncom.CoUninitialize()

    @property
    def active(self):
        return bool(self.thread and self.thread.is_alive())

    def stop(self):
        self.cancelled.set()
        if self.thread:
            self.thread.join(timeout=.5)
