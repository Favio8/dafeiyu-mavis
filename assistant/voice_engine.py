"""One continuous 16 kHz local KWS/VAD/ASR stream, independent of task authority."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

import numpy as np

from .voice_models import ModelManager, MANIFEST

SENSITIVITY = {"严格": .45, "标准": .25, "灵敏": .15}


def keyword_tokens(word: str, tokens: Path) -> str:
    if not re.fullmatch(r"[\u4e00-\u9fff]{2,8}", word):
        raise ValueError("唤醒词须为 2–8 个汉字")
    import sherpa_onnx
    converted = sherpa_onnx.text2token([word], tokens=str(tokens), tokens_type="ppinyin")
    vocabulary = {line.split()[0] for line in tokens.read_text(encoding="utf-8").splitlines() if line.strip()}
    if len(converted) != 1 or not converted[0] or any(part not in vocabulary for part in converted[0]):
        raise ValueError("当前模型无法表达这个唤醒词")
    return " ".join(converted[0]) + " @" + word


def strip_wake_prefix(text: str, word: str) -> str:
    """Only a leading wake boundary, after timestamp-based audio trimming.

    Mandarin ASR may render the same wake phonemes as 大飞鱼. Compare the
    leading phrase phonetically, never remove occurrences in command content.
    """
    from pypinyin import lazy_pinyin
    clean = text.strip(" \t，。！？、,.!?")
    leading = clean[:len(word)]
    if lazy_pinyin(leading) == lazy_pinyin(word):
        clean = clean[len(word):].lstrip(" \t，。！？、,.!?")
    return clean


def normalize_voice_command(text: str) -> str:
    """Map a few spoken forms to the same M2 command surface, not new tools."""
    clean = text.strip(" \t，。！？、,.!?")
    if re.fullmatch(r"(?:请|帮我|请帮我)?(?:打开|启动)(?:一下)?记事本", clean):
        return "打开记事本"
    match = re.fullmatch(r"(?:请|帮我|请帮我)?(?:在记事本)?输入[：:,， ]*(.+)", clean)
    return "输入：" + match[1] if match else clean


class VoiceEngine:
    RATE = 16000

    def __init__(self, root: Path, emit, *, word="大肥鱼", sensitivity="标准"):
        import sherpa_onnx
        self.manager = ModelManager(root)
        self.manager.verify()
        self.emit = emit
        kws, asr, vad = (self.manager.directory(k) for k in ("kws", "asr", "vad"))
        self.tokens = kws / "tokens.txt"
        self._kws_paths = {"tokens": str(self.tokens), "encoder": str(kws / "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx"), "decoder": str(kws / "decoder-epoch-12-avg-2-chunk-16-left-64.onnx"), "joiner": str(kws / "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx"), "num_threads": 2}
        self.asr = sherpa_onnx.OfflineRecognizer.from_paraformer(paraformer=str(asr / "model.int8.onnx"), tokens=str(asr / "tokens.txt"), num_threads=2)
        config = sherpa_onnx.VadModelConfig()
        config.silero_vad.model = str(vad / "silero_vad.onnx")
        config.silero_vad.min_silence_duration = .5
        config.sample_rate = self.RATE
        self.vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=16)
        self.configure(word, sensitivity)
        self.state = "OFF"
        self.total = 0
        self.reset()

    def configure(self, word, sensitivity):
        import sherpa_onnx
        keyword = keyword_tokens(word, self.tokens)
        # Pinned 1.12.26 requires an existing keyword file at construction.
        path = self.manager.root / ("keyword-" + hashlib.sha256(keyword.encode()).hexdigest()[:16] + ".txt")
        if not path.exists():
            path.write_text(keyword + "\n", encoding="utf-8")
        spotter = sherpa_onnx.KeywordSpotter(**self._kws_paths, keywords_file=str(path), keywords_threshold=SENSITIVITY[sensitivity])
        stream = spotter.create_stream()
        self.word, self.keyword, self.sensitivity = word, keyword, sensitivity
        self.spotter, self.kws_stream = spotter, stream

    def reset(self):
        self.ring = np.empty(0, dtype=np.float32)
        self.capture = []
        self.pending = np.empty(0, dtype=np.float32)
        self.vad.reset()
        self.seen_speech = False
        self.last_speech = self.total
        self.origin = self.total
        self.kws_stream = self.spotter.create_stream(self.keyword)
        self.capture_start = self.total
        self.manual = False

    def set_state(self, state):
        self.state = state
        self.emit("state", {"state": state})

    def arm(self):
        self.reset()
        self.set_state("ARMED")

    def off(self):
        self.reset()
        self.set_state("OFF")

    def guard(self):
        self.reset()
        self.set_state("PLAYBACK_GUARD")

    def start_manual(self, trigger="button"):
        self.reset()
        self.manual = True
        self.trigger = trigger
        self.set_state("CAPTURING")

    def cancel(self):
        self.emit("attempt", self._metadata("empty"))
        self.arm()

    def _metadata(self, result):
        return {"result": result, "trigger": getattr(self, "trigger", "wakeword"), "wakeword": self.word,
                "audio_duration_ms": min(60000, max(0, int((self.total - self.capture_start) * 1000 / self.RATE))),
                "model_id": MANIFEST["models"]["asr"]["id"], "model_hash": MANIFEST["models"]["asr"]["files"]["model.int8.onnx"]["sha256"], "asr_confidence": None}

    def feed(self, samples):
        if self.state not in {"ARMED", "CAPTURING"}:
            return
        samples = np.asarray(samples, dtype=np.float32).reshape(-1)
        self.total += len(samples)
        self.ring = np.concatenate((self.ring, samples))[-2*self.RATE:]
        if self.state == "ARMED":
            self.kws_stream.accept_waveform(self.RATE, samples)
            while self.spotter.is_ready(self.kws_stream):
                self.spotter.decode_stream(self.kws_stream)
                if self.spotter.get_result(self.kws_stream):
                    stamps = self.spotter.timestamps(self.kws_stream)
                    start = self.origin + int(stamps[0]*self.RATE) - 1600 if stamps else self.total - len(self.ring)
                    self.capture_start = max(self.total - len(self.ring), start)
                    self.capture = [self.ring[max(0, self.capture_start-(self.total-len(self.ring))):].copy()]
                    self.trigger = "wakeword"
                    self.pending = np.empty(0, dtype=np.float32)
                    self.vad.reset()
                    self.seen_speech = False
                    self.emit("wake", {"word": self.word, "audio_time_s": self.total/self.RATE})
                    self.set_state("CAPTURING")
                    self._vad(self.capture[0])
                    return
        else:
            self.capture.append(samples.copy())
            self._vad(samples)
            elapsed = (self.total-self.capture_start)/self.RATE
            if elapsed >= 12 or (not self.seen_speech and elapsed >= 5) or (self.seen_speech and elapsed > 1.2 and self.total-self.last_speech >= int(.6*self.RATE)):
                self.finish()

    def _vad(self, samples):
        self.pending = np.concatenate((self.pending, samples))
        while len(self.pending) >= 512:
            self.vad.accept_waveform(self.pending[:512])
            self.pending = self.pending[512:]
            if self.vad.is_speech_detected():
                self.seen_speech = True
                self.last_speech = self.total
            while not self.vad.empty():
                self.vad.pop()

    def finish(self):
        if self.state != "CAPTURING":
            return
        audio = np.concatenate(self.capture) if self.capture else np.empty(0, dtype=np.float32)
        if not self.seen_speech or len(audio) < 3200:
            self.emit("attempt", self._metadata("no_speech"))
            self.arm()
            return
        self.set_state("TRANSCRIBING")
        stream = self.asr.create_stream()
        stream.accept_waveform(self.RATE, audio)
        self.asr.decode_stream(stream)
        raw = stream.result.text.strip()
        command = raw if self.manual else strip_wake_prefix(raw, self.word)
        if command.strip(" ，。！？、,.!?"):
            self.emit("final", {**self._metadata("command"), "raw_text": raw, "text": command})
        else:
            self.emit("attempt", self._metadata("empty"))
        self.arm()
