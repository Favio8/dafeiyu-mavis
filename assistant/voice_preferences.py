"""Voice preferences only; microphone and computer authority are never persisted."""
import json
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field

from .contracts import Record


class VoicePreferences(Record):
    word: str = Field(default="大肥鱼", pattern=r"^[\u4e00-\u9fff]{2,8}$")
    sensitivity: Literal["严格", "标准", "灵敏"] = "标准"
    device: str = ""
    voice: str = ""
    volume: int = Field(default=70, ge=0, le=100)
    tts_enabled: bool = True


def save(path: Path, value: VoicePreferences):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value.model_dump(), ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
