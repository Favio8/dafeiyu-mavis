"""Interactive native voice acceptance; explicit microphone controls, fresh profile.

No recording starts automatically. The visible window guides a human test and
keeps only state/attempt metadata and committed task records, never raw audio.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", type=Path, default=Path(".scratch/m3/models"))
    parser.add_argument("--ui-probe", action="store_true", help="capture own voice page at two widths and exit without opening a microphone")
    parser.add_argument("--dark", action="store_true")
    parser.add_argument("--tts-soak-seconds", type=int, default=0, help="after a real microphone is armed, repeatedly play wake phrases for this many seconds")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from pet.qt_plugin_sanitizer import sanitize_plugin_path
    sanitize_plugin_path()
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QScrollArea
    from assistant.controller import Controller
    from assistant.stop import StopController, EmergencyHotkey
    from assistant.ui import ControlCenter
    from assistant.voice_host import VoiceHost
    from assistant.voice_models import ModelManager
    app = QApplication([])
    output = root / ".scratch/m3/acceptance" / str(time.time_ns())
    output.mkdir(parents=True)
    stop = StopController()
    hotkey = EmergencyHotkey(stop)
    hotkey.start()
    controller = Controller(output / "profile", stop, hotkey=hotkey)
    window = ControlCenter(controller, stop, hotkey, dark=args.dark)
    window.exiting = True  # closing this acceptance window ends its isolated host
    voice = VoiceHost(controller, stop, output / "profile", app)
    voice.models = ModelManager(args.models.resolve())
    voice.config["root"] = str(voice.models.root)
    voice.state["models"] = voice.models.status()
    voice.bind_window(window)
    window.install_voice(voice)
    window.nav.setCurrentRow(2)
    window.setWindowTitle("Mavis 真人语音验收 · 校准默认不执行任务")
    window.voice_panel.error.setText("先刷新设备，再开启监听。连续说“大肥鱼帮我打开记事本”；核对识别文字后再测试自定义词、仅唤醒词与 TTS。")
    timeline = []
    last = [None]
    def changed(value):
        state = {k: value.get(k) for k in ("state", "desired", "capture_open", "error", "word", "test_mode")}
        if state != last[0]:
            timeline.append({"t": time.monotonic(), **state})
            last[0] = state
    voice.changed.connect(changed)
    voice_events = []
    voice.activity.connect(lambda kind, value: voice_events.append({"event": kind, **{k: value[k] for k in ("state", "word", "open", "buffer_samples", "error", "code") if k in value}}) if kind != "level" else None)
    soak = {"requested_seconds": args.tts_soak_seconds, "started": None, "completed": False, "playbacks": 0}
    soak_timer = QTimer()
    def soak_tick():
        if voice.state["state"] != "ARMED" or not voice.state["capture_open"]:
            return
        if soak["started"] is None:
            soak["started"] = time.monotonic()
            soak["events_start"] = len(voice_events)
        if time.monotonic()-soak["started"] >= args.tts_soak_seconds:
            soak["completed"] = True
            soak_timer.stop()
            voice.listen(False)
            QTimer.singleShot(500, app.quit)
            return
        soak["playbacks"] += 1
        voice.speak(voice.config["word"] + "。这是防自唤醒测试，不执行电脑操作。")
    if args.tts_soak_seconds:
        soak_timer.setInterval(500)
        soak_timer.timeout.connect(soak_tick)
        soak_timer.start()
    checks = []
    def save_page(index=0):
        widths = (1100, 720)
        if index >= len(widths):
            app.quit()
            return
        width = widths[index]
        window.resize(width, 760 if width == 1100 else 600)
        for area in window.stack.currentWidget().findChildren(QScrollArea):
            area.verticalScrollBar().setValue(0)
        def capture():
            page = window.stack.currentWidget()
            checks.append({"requested_width": width, "actual_width": window.width(), "no_horizontal_scroll": all(a.horizontalScrollBar().maximum() == 0 for a in page.findChildren(QScrollArea))})
            window.grab().save(str(output / f"voice-{width}.png"))
            for area in page.findChildren(QScrollArea):
                area.verticalScrollBar().setValue(area.verticalScrollBar().maximum())
            QTimer.singleShot(100, lambda: bottom(index, width))
        QTimer.singleShot(150, capture)
    def bottom(index, width):
        window.grab().save(str(output / f"voice-{width}-bottom.png"))
        save_page(index+1)
    controller.start()
    window.show()
    if args.ui_probe:
        QTimer.singleShot(400, save_page)
    else:
        QTimer.singleShot(0, voice.refresh)
    def close():
        voice.close()
        controller.close()
        hotkey.close()
        window.exiting = True
        window.close()
    app.aboutToQuit.connect(close)
    result = app.exec()
    close()
    exited = voice.process is None or voice.process.process.poll() is not None
    opened = any(e.get("capture_open") for e in timeline)
    report = {"platform": app.platformName(), "mode": "own-window UI capture; no audio" if args.ui_probe else "human-operated acceptance; inspect actual events before marking passed", "events": timeline, "voice_events": voice_events, "layout": checks,
        "voice_worker_exited": exited, "real_microphone_opened": opened,
        "microphone_release": "real capture opened; owning process exited, reclaiming OS handles" if opened and exited else "pending: no real microphone opened",
        "tts_soak": {**soak, "wake_events": sum(e["event"] == "wake" for e in voice_events[soak.get("events_start", 0):]), "final_events": sum(e["event"] == "final" for e in voice_events[soak.get("events_start", 0):])}, "raw_audio_saved": False}
    (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("evidence=" + str(output))
    return result if all(c["no_horizontal_scroll"] and c["actual_width"] == c["requested_width"] for c in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
