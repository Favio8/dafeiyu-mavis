"""SQLite single-writer store. Every snapshot and its event commit atomically."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from uuid import UUID

from .contracts import Approval, Observation, Step, Task, TaskEvent, TaskStatus, Verification, VoiceAttempt, TERMINAL, utc_now
from .privacy import redact


class Store:
    """Open a schema-v1 database on the calling controller thread.

    Raises sqlite3 errors on any persistence failure. Callers must fail closed.
    A unique partial index also prevents two hosts creating concurrent tasks.
    """
    def __init__(self, path: Path):
        self.path = path
        self.owner = threading.get_ident()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=0.15)
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            self.db.close()
            raise ValueError("unsupported database version; original database preserved")
        if version == 0:
            # A pre-schema database may contain user records: back it up, never overwrite it.
            if self.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                backup = path.with_name(path.name + ".pre-v1.bak")
                if backup.exists():
                    self.db.close()
                    raise FileExistsError("migration backup already exists")
                with sqlite3.connect(backup) as target:
                    self.db.backup(target)
                self.db.close()
                raise ValueError("unrecognized legacy schema; backup made, migration refused")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        if version == 0:
            self.db.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE tasks(id TEXT PRIMARY KEY, status TEXT NOT NULL, active INTEGER NOT NULL,
                    created TEXT NOT NULL, finished TEXT, mode TEXT NOT NULL, data TEXT NOT NULL);
                CREATE UNIQUE INDEX one_active ON tasks(active) WHERE active=1;
                CREATE INDEX task_history ON tasks(mode, created DESC);
                CREATE TABLE events(event_id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    seq INTEGER NOT NULL CHECK(seq>0), data TEXT NOT NULL, UNIQUE(task_id,seq));
                CREATE TABLE steps(id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    seq INTEGER NOT NULL, tool_call_id TEXT NOT NULL, data TEXT NOT NULL,
                    UNIQUE(task_id,seq), UNIQUE(task_id,tool_call_id));
                CREATE TABLE approvals(id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    status TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE observations(id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE, data TEXT NOT NULL);
                CREATE TABLE verifications(id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE, data TEXT NOT NULL);
                CREATE TABLE voice_attempts(id TEXT PRIMARY KEY, task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL, data TEXT NOT NULL);
                PRAGMA user_version=1;
                COMMIT;
            """)

    def _owner(self) -> None:
        if threading.get_ident() != self.owner:
            raise RuntimeError("SQLite access must stay on its controller thread")

    @staticmethod
    def _json(record) -> str:
        # Redact before JSON encoding so escaping cannot corrupt a structured record.
        def clean(value):
            if isinstance(value, str):
                return redact(value)
            if isinstance(value, dict):
                return {key: clean(item) for key, item in value.items()}
            if isinstance(value, list):
                return [clean(item) for item in value]
            return value
        import json
        return json.dumps(clean(record.model_dump(mode="json")), ensure_ascii=False, allow_nan=False)

    def commit(self, task: Task, kind: str, payload: str = "", *, step: Step | None = None,
               approvals: tuple[Approval, ...] = (), observation: Observation | None = None,
               verifications: tuple[Verification, ...] = ()) -> TaskEvent:
        """Persist an entire state transition before returning its publishable event."""
        self._owner()
        if any(record.task_id != task.id for record in (*approvals, *verifications, *((step,) if step else ()))):
            raise ValueError("record belongs to another task")
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self.db.execute("""INSERT INTO tasks VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,active=excluded.active,finished=excluded.finished,data=excluded.data""",
                (str(task.id), task.status.value, int(task.status not in TERMINAL), task.created_at.isoformat(),
                 task.finished_at.isoformat() if task.finished_at else None, task.mode, self._json(task)))
            seq = self.db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM events WHERE task_id=?", (str(task.id),)).fetchone()[0]
            event = TaskEvent(task_id=task.id, seq=seq, type=kind, payload_redacted=redact(payload))
            self.db.execute("INSERT INTO events VALUES(?,?,?,?)", (str(event.event_id), str(task.id), seq, self._json(event)))
            if step:
                self.db.execute("""INSERT INTO steps VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data""",
                                (str(step.id), str(task.id), step.seq, str(step.tool_call_id), self._json(step)))
            for approval in approvals:
                self.db.execute("""INSERT INTO approvals VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,data=excluded.data""", (str(approval.id), str(task.id), approval.status, self._json(approval)))
            if observation:
                self.db.execute("INSERT OR IGNORE INTO observations VALUES(?,?,?)", (str(observation.id), str(task.id), self._json(observation)))
            for result in verifications:
                self.db.execute("INSERT INTO verifications VALUES(?,?,?)", (str(result.id), str(task.id), self._json(result)))
            if task.status in TERMINAL or task.status == TaskStatus.PAUSING:
                for row in self.db.execute("SELECT data FROM steps WHERE task_id=?", (str(task.id),)).fetchall():
                    pending = Step.model_validate_json(row[0])
                    if pending.status in {"proposed", "awaiting_approval", "running"}:
                        pending = pending.model_copy(update={"status": "unknown" if pending.status == "running" else "cancelled", "ended_at": utc_now()})
                        self.db.execute("UPDATE steps SET data=? WHERE id=?", (self._json(pending), str(pending.id)))
        return event

    def task(self, task_id: UUID) -> Task | None:
        """Look up a specific task for auditing late callbacks without reviving it."""
        self._owner()
        row = self.db.execute("SELECT data FROM tasks WHERE id=?", (str(task_id),)).fetchone()
        return Task.model_validate_json(row[0]) if row else None

    def tasks(self, limit: int = 50, mode: str | None = None) -> list[Task]:
        """Return at most 100 recent records; test/live histories can be separated."""
        self._owner()
        if not 1 <= limit <= 100:
            raise ValueError("invalid page size")
        rows = self.db.execute("SELECT data FROM tasks WHERE (? IS NULL OR mode=?) ORDER BY created DESC LIMIT ?", (mode, mode, limit))
        return [Task.model_validate_json(row[0]) for row in rows]

    def events(self, task_id: UUID) -> list[TaskEvent]:
        """Return committed events in sequence order."""
        self._owner()
        return [TaskEvent.model_validate_json(row[0]) for row in self.db.execute(
            "SELECT data FROM events WHERE task_id=? ORDER BY seq", (str(task_id),))]

    def approvals(self, task_id: UUID) -> list[Approval]:
        """Return approval history, without an executable permission capability."""
        self._owner()
        return [Approval.model_validate_json(row[0]) for row in self.db.execute(
            "SELECT data FROM approvals WHERE task_id=?", (str(task_id),))]

    def recover(self) -> int:
        """Interrupt all abandoned tasks and revoke approvals; never replay actions."""
        self._owner()
        abandoned = [Task.model_validate_json(row[0]) for row in self.db.execute("SELECT data FROM tasks WHERE active=1")]
        for task in abandoned:
            approvals = tuple(a.model_copy(update={"status": "revoked"}) for a in self.approvals(task.id)
                              if a.status in ("pending", "approved"))
            self.commit(task.model_copy(update={"status": TaskStatus.INTERRUPTED,
                "generation": task.generation + 1, "finished_at": utc_now(), "error_code": "HOST_RESTART"}),
                "task.finished", "启动时发现未结束任务，未重放动作", approvals=approvals)
        return len(abandoned)

    def retain(self, before: str) -> int:
        """Delete only finished local task records before an ISO UTC cutoff."""
        self._owner()
        with self.db:
            return self.db.execute("DELETE FROM tasks WHERE active=0 AND finished<?", (before,)).rowcount

    def voice_attempt(self, attempt: VoiceAttempt) -> None:
        """Persist valid metadata; never accept an audio blob."""
        self._owner()
        with self.db:
            self.db.execute("INSERT INTO voice_attempts VALUES(?,?,?)", (str(attempt.id), str(attempt.task_id) if attempt.task_id else None, self._json(attempt)))

    def voice_attempts(self) -> list[VoiceAttempt]:
        self._owner()
        return [VoiceAttempt.model_validate_json(row[0]) for row in self.db.execute("SELECT data FROM voice_attempts ORDER BY rowid DESC LIMIT 50")]

    def close(self) -> None:
        """Close the writer connection on its owning thread."""
        self._owner()
        self.db.close()
