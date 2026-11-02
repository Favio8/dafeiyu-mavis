"""Non-secret control-center preferences; applied to future tasks only."""
from pathlib import Path
from typing import Literal
from uuid import uuid4

from .contracts import Record
from .provider import ProviderSettings
from pydantic import Field, field_validator, model_validator


class AppSettings(Record):
    provider: ProviderSettings = ProviderSettings()
    retention_days: Literal[7, 30, 90] = 30
    onboarding_done: bool = False
    skipped: tuple[Literal["model", "voice", "permissions"], ...] = ()
    close_notice_seen: bool = False
    execution_glow: bool = True
    avoid_target: bool = True
    emergency_shortcut: str = "Ctrl+Alt+F12"
    recording_shortcut: str = "Ctrl+Alt+Space"
    provider_checks: dict[str, str] = Field(default_factory=lambda: {"connection": "待验证", "tools": "待验证", "vision": "未验证"})
    provider_tested_at: str | None = None

    @field_validator("provider")
    @classmethod
    def non_secret_model_id(cls, value):
        from .privacy import redact
        if value.model.startswith("sk-") or redact(value.model) != value.model:
            raise ValueError("模型 ID 不能包含 API Key")
        return value

    @field_validator("emergency_shortcut", "recording_shortcut")
    @classmethod
    def valid_shortcut(cls, value):
        from .stop import shortcut_key
        shortcut_key(value)
        return value

    @model_validator(mode="after")
    def distinct_shortcuts(self):
        if self.emergency_shortcut == self.recording_shortcut:
            raise ValueError("急停和录音不能使用同一个快捷键")
        return self


def save_settings(path: Path, settings: AppSettings):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    temporary.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(path)


def load_settings(path: Path) -> AppSettings:
    return AppSettings.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else AppSettings()
