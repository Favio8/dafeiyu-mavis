"""History query and export contracts, shared by UI and the SQLite writer."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
from typing import Literal

from pydantic import Field

from .contracts import Record, TaskStatus
from .privacy import redact


class HistoryQuery(Record):
    kind: Literal["task", "voice"] = "task"
    keyword: str = Field(default="", max_length=200)
    status: TaskStatus | Literal["command", "no_speech", "empty", "error", "busy_ignored"] | None = None
    source: Literal["voice", "text", "manual_record"] | None = None
    days: Literal[0, 7, 30, 90] = 7
    page: int = Field(default=0, ge=0)
    request: int = Field(default=0, ge=0)

    @classmethod
    def from_mapping(cls, value):
        return cls.model_validate_json(json.dumps(value, ensure_ascii=False))

    def cutoff(self):
        return (datetime.now(timezone.utc)-timedelta(days=self.days)).isoformat() if self.days else None


def export_redact(value):
    if isinstance(value, dict):
        return {k: export_redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [export_redact(v) for v in value]
    if isinstance(value, str):
        clean = redact(value)
        for marker, name in [("%USERPROFILE%", "USERPROFILE"), ("%APPDATA%", "APPDATA"), ("%LOCALAPPDATA%", "LOCALAPPDATA")]:
            home = os.environ.get(name)
            if home:
                clean = clean.replace(home, marker).replace(home.replace("\\", "/"), marker)
        return re.sub(r"(?i)([a-z]:[/\\]Users[/\\])[^/\\\s]+", r"\1[USER]", clean)
    return value


def write_export(path: Path, data, format: str):
    """Explicit local export. Existing files are never silently overwritten."""
    clean = export_redact(data)
    if format == "json":
        text = json.dumps(clean, ensure_ascii=False, indent=2)
    elif format == "markdown":
        text = "# Mavis 任务记录\n\n" + "\n\n".join("## " + str(item.get("title", item.get("id", "记录"))).replace("\n", " ") + "\n\n```json\n" + json.dumps(item, ensure_ascii=False, indent=2).replace("```", "` ` `") + "\n```" for item in clean)
    else:
        raise ValueError("EXPORT_FORMAT_UNSUPPORTED")
    with path.open("x", encoding="utf-8") as file:
        file.write(text)
