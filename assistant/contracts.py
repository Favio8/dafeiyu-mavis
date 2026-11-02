"""Versioned host-owned records. Unknown measurements remain null, never guesses."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    """Return an aware UTC timestamp for display; deadlines use monotonic clocks."""
    return datetime.now(timezone.utc)


class Record(BaseModel):
    """Reject unrecognized fields, coercion and non-finite numbers at boundaries."""
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


class TaskStatus(StrEnum):
    CREATED = "CREATED"
    INTERPRETING = "INTERPRETING"
    WAITING_CLARIFICATION = "WAITING_CLARIFICATION"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    WAITING_USER = "WAITING_USER"
    VERIFYING = "VERIFYING"
    PAUSING = "PAUSING"
    PAUSED = "PAUSED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    UNVERIFIED = "UNVERIFIED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    INTERRUPTED = "INTERRUPTED"
    BLOCKED = "BLOCKED"


TERMINAL = frozenset({TaskStatus.SUCCEEDED, TaskStatus.PARTIAL, TaskStatus.FAILED,
                     TaskStatus.UNVERIFIED, TaskStatus.CANCELLED, TaskStatus.TIMED_OUT,
                     TaskStatus.INTERRUPTED, TaskStatus.BLOCKED})
WAITING = frozenset({TaskStatus.WAITING_CLARIFICATION, TaskStatus.WAITING_APPROVAL,
                    TaskStatus.WAITING_USER, TaskStatus.PAUSED})


class Budget(Record):
    """Validated task limits, snapshotted at creation."""
    active_s: int = Field(default=180, ge=30, le=600)
    wall_s: int = Field(default=900, ge=60, le=1800)
    actions: int = Field(default=20, ge=1, le=40)
    tools: int = Field(default=60, ge=5, le=120)
    llm_rounds: int = Field(default=15, ge=1, le=30)
    approval_s: int = Field(default=60, ge=15, le=120)
    observation_ms: int = Field(default=2000, ge=500, le=5000)

    @model_validator(mode="after")
    def consistent(self) -> Budget:
        if self.wall_s < self.active_s or self.tools < self.actions:
            raise ValueError("inconsistent budgets")
        return self


class ProviderSnapshot(Record):
    """Non-secret configuration only; a credential is referenced by name."""
    provider: Literal["deepseek"] = "deepseek"
    endpoint: Literal["https://api.deepseek.com"] = "https://api.deepseek.com"
    model: str = Field(default="deepseek-flash", min_length=1, max_length=120)
    credential_ref: Literal["deepseek/default"] = "deepseek/default"
    tool_call: bool | None = None
    vision: bool | None = None
    tested_at: datetime | None = None


class Goal(Record):
    """Declarative predicate identifier; never code or a model verdict."""
    id: str = Field(default="primary", min_length=1, max_length=80)
    description: str = Field(default="用户目标", max_length=500)
    predicate: Literal["fixture.counter_equals", "window", "uia", "url", "file_content"] = "window"
    required: bool = True


Text = Annotated[str, Field(min_length=1, max_length=4000, pattern=r"\S")]


class Task(Record):
    """Host task snapshot. Status is changed exclusively by TaskService."""
    schema_version: Literal[1] = 1
    id: UUID = Field(default_factory=uuid4)
    parent_task_id: UUID | None = None
    mode: Literal["live", "test"] = "live"
    source: Literal["voice", "text", "manual_record"] = "text"
    original_text: Text
    final_text: Text
    title: str = Field(default="", max_length=80)
    status: TaskStatus = TaskStatus.CREATED
    goals: tuple[Goal, ...] = Field(default_factory=lambda: (Goal(),), max_length=20)
    provider: ProviderSnapshot = Field(default_factory=ProviderSnapshot)
    budget: Budget = Field(default_factory=Budget)
    created_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    active_ms: int = Field(default=0, ge=0)
    waiting_ms: int = Field(default=0, ge=0)
    action_count: int = Field(default=0, ge=0)
    tool_call_count: int = Field(default=0, ge=0)
    llm_round_count: int = Field(default=0, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_estimate: float | None = Field(default=None, ge=0)
    verification_status: Literal["passed", "partial", "failed", "unknown", "not_run"] = "not_run"
    effects: tuple[str, ...] = ()
    error_code: str | None = None
    generation: int = Field(default=1, ge=1)


class Observation(Record):
    """Host observation, not accepted from tool-intent payloads or web content."""
    id: UUID = Field(default_factory=uuid4)
    captured_at: datetime = Field(default_factory=utc_now)
    captured_mono: float = Field(ge=0)
    context_digest: str = Field(min_length=64, max_length=64, pattern="^[0-9a-f]+$")
    hwnd: int = Field(default=0, ge=0)
    pid: int = Field(default=0, ge=0)
    app: str = Field(default="", max_length=260)
    domain: str | None = Field(default=None, max_length=253)
    integrity: Literal["medium", "high", "unknown"] = "unknown"
    own_ui: bool = False
    editable_draft: bool = False
    safe_control: bool = False
    control_id: str = Field(default="", max_length=256)
    bounds: tuple[int, int, int, int] = (0, 0, 0, 0)
    dpi: int = Field(default=96, ge=48, le=768)
    identity_digest: str = Field(default="", max_length=64)
    document_digest: str = Field(default="", max_length=64)


class Step(Record):
    """One persisted logical action; immutable parameters are represented by a digest."""
    id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    seq: int = Field(ge=1)
    tool_call_id: UUID
    attempt: int = Field(default=1, ge=1, le=3)
    tool_name: str
    args_redacted: str
    action_digest: str
    risk: Literal["R0", "R1", "R2", "RU"]
    observation_id: UUID
    status: Literal["proposed", "awaiting_approval", "running", "succeeded", "failed", "unknown", "blocked", "cancelled"] = "proposed"
    started_at: datetime | None = None
    ended_at: datetime | None = None
    elapsed_ms: int | None = Field(default=None, ge=0)
    retry_safe: bool = False


class Verification(Record):
    """Independent oracle result, tied to a goal, generation and task."""
    id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    generation: int = Field(ge=1)
    goal_id: str
    method: Literal["window", "uia", "url", "file_content", "visual", "manual", "fixture"]
    result: Literal["passed", "failed", "unknown"]
    evidence: str = Field(max_length=2000)
    strength: Literal["deterministic", "visual_assisted", "user_reported"] = "deterministic"
    timestamp: datetime = Field(default_factory=utc_now)


class Approval(Record):
    """Persistent audit record. The executable grant exists only in host memory."""
    id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    tool_call_id: UUID
    action_digest: str
    context_digest: str
    generation: int = Field(ge=1)
    status: Literal["pending", "approved", "denied", "expired", "consumed", "revoked"] = "pending"
    requested_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    decision_source: Literal["local_ui"] | None = None
    grant_id: UUID | None = None


class TaskEvent(Record):
    """Commit-before-publish event. Sequence is per task, never wall-clock order."""
    schema_version: Literal[1] = 1
    event_id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    seq: int = Field(ge=1)
    timestamp_utc: datetime = Field(default_factory=utc_now)
    type: str = Field(min_length=1, max_length=80)
    payload_redacted: str = Field(default="", max_length=16000)


class VoiceAttempt(Record):
    """Metadata only for voice diagnostics; invalid speech has no retained transcript."""
    id: UUID = Field(default_factory=uuid4)
    task_id: UUID | None = None
    trigger: Literal["wakeword", "hotkey", "button"]
    wakeword: str = Field(default="大肥鱼", min_length=2, max_length=8)
    started_at: datetime = Field(default_factory=utc_now)
    audio_duration_ms: int = Field(ge=0, le=60000)
    result: Literal["command", "no_speech", "empty", "error", "busy_ignored"]
    asr_text: Text | None = None
    asr_confidence: float | None = Field(default=None, ge=0, le=1)
    model_id: str
    model_hash: str

    @model_validator(mode="after")
    def no_ambient_transcript(self) -> VoiceAttempt:
        if self.result != "command" and self.asr_text is not None:
            raise ValueError("only valid commands may retain a transcript")
        return self


class ToolResult(Record):
    """Tool status is not a task verdict; timeouts retain unknown effect semantics."""
    task_id: UUID
    tool_call_id: UUID
    status: Literal["ok", "error", "unknown", "cancelled"]
    effect: str = Field(default="", max_length=1000)
    error_code: str | None = None
    retry_safe: bool = False
    elapsed_ms: int = Field(ge=0)
