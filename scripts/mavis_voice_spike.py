"""Download fixed official model archives and run CPU inference without a microphone."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import urllib.request
import wave
from uuid import uuid4

MODELS = {
    "kws": ("kws-models", "sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01", 32654866),
    "asr": ("asr-models", "sherpa-onnx-paraformer-zh-small-2024-03-09", 77920048),
}


def prepare(base: Path) -> dict:
    """Extract only regular files under the dedicated model directory; never execute archive content."""
    base.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for kind, (tag, name, size) in MODELS.items():
        archive = base / (name + ".tar.bz2")
        url = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/{tag}/{archive.name}"
        if not archive.exists():
            print(f"Downloading {kind}: {size} bytes", flush=True)
            with urllib.request.urlopen(url, timeout=60) as response, archive.open("xb") as target:
                shutil.copyfileobj(response, target)
        if archive.stat().st_size != size:
            raise ValueError(f"size mismatch: {archive.name}; preserved for diagnosis")
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        destination = base / name
        if not destination.exists():
            with tarfile.open(archive, "r:bz2") as tar:
                for member in tar.getmembers():
                    path = (base / member.name).resolve()
                    if not path.is_relative_to(destination.resolve()) or not (member.isdir() or member.isfile()):
                        raise ValueError("unsafe archive member")
                    if member.isdir():
                        path.mkdir(parents=True, exist_ok=True)
                    else:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        with tar.extractfile(member) as source, path.open("xb") as target:
                            shutil.copyfileobj(source, target)
        files = {str(p.relative_to(destination)): {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size}
                 for p in destination.rglob("*") if p.is_file()}
        manifest[kind] = {"source": url, "archive_sha256": checksum, "bytes": size,
                          "directory": name, "files": files, "hash_origin": "locally measured; upstream asset has no digest"}
    (base / "model-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def samples(path: Path):
    """Read a package-supplied mono 16-bit WAV; never record ambient user audio."""
    import numpy as np
    with wave.open(str(path)) as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError("mono PCM16 sample required")
        return wav.getframerate(), np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


def run(base: Path) -> dict:
    """Load real KWS and ASR models; report inference separately from wakeword quality."""
    import numpy as np
    import sherpa_onnx
    kws = base / MODELS["kws"][1]
    asr = base / MODELS["asr"][1]
    tokens = kws / "tokens.txt"
    words = ["大肥鱼", "小助手"]
    converted = sherpa_onnx.text2token(words, tokens=str(tokens), tokens_type="ppinyin")
    if len(converted) != len(words):
        raise ValueError("wakeword contains an unsupported model token")
    keywords = base / "mavis-keywords.txt"
    keywords.write_text("\n".join(" ".join(parts) + " @" + word for word, parts in zip(words, converted)) + "\n", encoding="utf-8")
    suffix = "epoch-12-avg-2-chunk-16-left-64"
    spotter = sherpa_onnx.KeywordSpotter(tokens=str(tokens), encoder=str(kws / f"encoder-{suffix}.int8.onnx"),
        decoder=str(kws / f"decoder-{suffix}.onnx"), joiner=str(kws / f"joiner-{suffix}.int8.onnx"),
        keywords_file=str(keywords), num_threads=2)
    stream = spotter.create_stream()
    stream.accept_waveform(16000, np.zeros(16000, dtype=np.float32))
    while spotter.is_ready(stream):
        spotter.decode_stream(stream)
    silence = spotter.get_result(stream)
    model = next(asr.glob("*.int8.onnx"), None) or next(asr.glob("*.onnx"))
    recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(paraformer=str(model), tokens=str(asr / "tokens.txt"), num_threads=2)
    wav = next(asr.rglob("*.wav"))
    rate, audio = samples(wav)
    stream = recognizer.create_stream()
    stream.accept_waveform(rate, audio)
    recognizer.decode_stream(stream)
    return {"engine": sherpa_onnx.__version__, "keywords": dict(zip(words, converted)),
            "silence_kws_result": silence, "asr_sample": wav.name, "sample_rate": rate,
            "asr_text": stream.result.text, "microphone": "not tested", "wakeword_recall": None}


def tts_spike(base: Path) -> dict:
    """Enumerate local SAPI voices and feed generated WAVs to KWS; never play or record audio."""
    import numpy as np
    import sherpa_onnx
    import win32com.client
    voice = win32com.client.Dispatch("SAPI.SpVoice")
    voices = list(voice.GetVoices())
    inventory = [{"name": item.GetDescription(), "language": item.GetAttribute("Language")} for item in voices]
    selected = next((item for item in voices if any(code.lower() in {"804", "404", "c04", "1004", "1404"}
                     for code in item.GetAttribute("Language").split(";"))), None)
    if selected is None:
        return {"voices": inventory, "chinese_local_tts": False, "generated_kws_cases": [], "fallback": "text only"}
    voice.Voice = selected
    kws = base / MODELS["kws"][1]
    suffix = "epoch-12-avg-2-chunk-16-left-64"
    spotter = sherpa_onnx.KeywordSpotter(tokens=str(kws / "tokens.txt"), encoder=str(kws / f"encoder-{suffix}.int8.onnx"),
        decoder=str(kws / f"decoder-{suffix}.onnx"), joiner=str(kws / f"joiner-{suffix}.int8.onnx"),
        keywords_file=str(base / "mavis-keywords.txt"), num_threads=2)
    results = []
    for keyword in ["大肥鱼", "小助手"]:
        path = base / ("synthetic-" + uuid4().hex + ".wav")
        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        stream.Format.Type = 18  # SAPI SAFT16kHz16BitMono; checked from the actual WAV below.
        stream.Open(str(path), 3, False)  # Unique absent test path, never a user's file.
        voice.AudioOutputStream = stream
        voice.Speak(keyword + "，打开记事本。")
        stream.Close()
        rate, audio = samples(path)
        if rate != 16000:
            raise ValueError("SAPI did not produce the required 16 kHz fixture")
        audio = np.concatenate((audio, np.zeros(16000, dtype=np.float32)))
        s = spotter.create_stream()
        detected = []
        for offset in range(0, len(audio), 1600):
            s.accept_waveform(rate, audio[offset:offset + 1600])
            while spotter.is_ready(s):
                spotter.decode_stream(s)
                if hit := spotter.get_result(s):
                    detected.append(hit)
                    spotter.reset_stream(s)
        results.append({"keyword": keyword, "detected": detected, "file": path.name,
                        "source": "local SAPI synthetic fixture, not microphone speech"})
    return {"voices": inventory, "chinese_local_tts": True, "voice": selected.GetDescription(), "generated_kws_cases": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--infer", action="store_true")
    parser.add_argument("--tts-smoke", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    base = root / ".scratch/m0-m1/models"
    if args.download:
        prepare(base)
    if args.infer:
        result = run(base)
        output = root / ".scratch/m0-m1/evidence/voice-spike.json"
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.tts_smoke:
        result = tts_spike(base)
        output = root / ".scratch/m0-m1/evidence/tts-kws-spike.json"
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
