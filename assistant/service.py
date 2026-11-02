"""Single task state machine. No worker, tool or UI owns a competing task state."""
from __future__ import annotations

import sqlite3
import threading
import time
import json
from collections.abc import Callable
from uuid import UUID

from .contracts import Goal, Observation, Task, TaskStatus as S, TERMINAL, WAITING, Verification, utc_now, ProviderSnapshot
from .privacy import redact
from .storage import Store


class Busy(RuntimeError):
    """The desktop already has an active task; tasks are never silently queued."""


class InvalidTransition(ValueError):
    """An illegal or stale state request was rejected without mutating history."""


_NEXT = {
    S.CREATED: {S.INTERPRETING},
    S.INTERPRETING: {S.EXECUTING, S.WAITING_CLARIFICATION, S.BLOCKED, S.FAILED},
    S.EXECUTING: {S.VERIFYING, S.WAITING_APPROVAL, S.WAITING_CLARIFICATION, S.WAITING_USER, S.FAILED, S.BLOCKED},
    S.WAITING_CLARIFICATION: {S.INTERPRETING},
    S.WAITING_APPROVAL: {S.EXECUTING},
    S.WAITING_USER: {S.INTERPRETING},
    S.VERIFYING: {S.SUCCEEDED, S.PARTIAL, S.FAILED, S.UNVERIFIED},
    S.PAUSING: {S.PAUSED},
    S.PAUSED: {S.INTERPRETING},
    S.CANCEL_REQUESTED: {S.CANCELLED},
}


class TaskService:
    """Controller-thread authority; cancellation latch is safe from other threads.

    All persistence failures set the latch before propagating. Subscribers receive
    committed events only, and a failed subscriber cannot undo a committed state.
    """
    def __init__(self, store: Store, *, clock: Callable[[], float] = time.monotonic,
                 stop: threading.Event | None = None):
        self.store, self.clock = store, clock
        self.stop = stop if stop is not None else threading.Event()
        self.store.recover()
        self.task: Task | None = None
        self.observation: Observation | None = None
        self.subscribers: list[Callable] = []
        self.invalidate: Callable[[], tuple] = lambda: ()
        self._created = self._last = self.clock()
        self._wait_since = self._last
        self._generation = 0
        self.pause_requested = threading.Event()
        self.provider = ProviderSnapshot()
        self.configuration = {}

    def persist(self, task: Task, kind: str, payload: str = "", **records):
        """Commit a transition and publish it. Storage errors revoke execution immediately."""
        try:
            event = self.store.commit(task, kind, payload, **records)
        except (sqlite3.Error, OSError):
            self.stop.set()
            self.invalidate()
            raise
        self.task = task
        for subscriber in tuple(self.subscribers):
            try:
                subscriber(event)
            except (RuntimeError, ValueError):
                # UI observer failure cannot change the durable task outcome.
                continue
        return event

    def create(self, text: str, *, source: str = "text", mode: str = "live", goals: tuple[Goal, ...] | None = None, original_text: str | None = None, parent_task_id=None) -> Task:
        """Start one task from a final command; reject empty text or an occupied desktop."""
        if self.task is not None and self.task.status not in TERMINAL:
            raise Busy("已有活动任务，请先停止或等待结束")
        if self.stop.is_set():
            raise InvalidTransition("急停已锁定，请明确复位后创建新任务")
        self._generation += 1
        self.pause_requested.clear()
        created = self.clock()
        clean = redact(text.strip())
        task = Task(original_text=redact(original_text.strip()) if original_text is not None else clean, final_text=clean, title=clean[:80], source=source, mode=mode,
                    generation=self._generation, provider=self.provider, parent_task_id=parent_task_id, goals=goals if goals is not None else (Goal(),))
        self.persist(task, "task.created", clean)
        if self.configuration:
            self.persist(task, "task.configuration", json.dumps(self.configuration, ensure_ascii=False))
        self._created = self._last = self._wait_since = created
        self.observation = None
        return task

    def _updated(self, state: S, **changes) -> Task:
        assert self.task is not None
        now = self.clock()
        elapsed = max(0, int((now - self._last) * 1000))
        field = "waiting_ms" if self.task.status in WAITING else "active_ms"
        changes[field] = getattr(self.task, field) + elapsed
        changes["status"] = state
        if state == S.INTERPRETING and self.task.started_at is None:
            changes["started_at"] = utc_now()
        if state in TERMINAL:
            changes.update(finished_at=utc_now(), duration_ms=max(0, int((now - self._created) * 1000)))
        return self.task.model_copy(update=changes)

    def transition(self, state: S, *, _verified: bool = False, **changes) -> Task:
        """Apply a legal transition. Success is available only through independent verification."""
        task = self.task
        if task is None or task.status in TERMINAL:
            raise InvalidTransition("task is absent or terminal")
        if state in {S.SUCCEEDED, S.PARTIAL, S.UNVERIFIED} and not _verified:
            raise InvalidTransition("independent goal verification is required")
        allowed = set(_NEXT.get(task.status, ()))
        if task.status != S.CANCEL_REQUESTED:
            allowed |= {S.CANCEL_REQUESTED, S.INTERRUPTED, S.TIMED_OUT}
        if task.status not in {S.PAUSED, S.PAUSING, S.CANCEL_REQUESTED}:
            allowed.add(S.PAUSING)
        if state not in allowed:
            raise InvalidTransition(f"{task.status} -> {state}")
        if self.stop.is_set() and state not in {S.CANCEL_REQUESTED, S.CANCELLED, S.INTERRUPTED, S.TIMED_OUT}:
            raise InvalidTransition("stop has priority")
        approvals = ()
        if state in TERMINAL or state in {S.PAUSING, S.CANCEL_REQUESTED}:
            approvals = self.invalidate()
            changes["generation"] = task.generation + 1
            self._generation = changes["generation"]
            self.observation = None
        updated = self._updated(state, **changes)
        transition_time = self.clock()
        self.persist(updated, "task.finished" if state in TERMINAL else "task.state_changed", state.value, approvals=approvals)
        self._last = transition_time
        if state in WAITING:
            self._wait_since = self._last
        return updated

    def cancel(self) -> None:
        """Revoke permits before cancellation is persisted; old callbacks cannot resume."""
        self.stop.set()
        if self.task and self.task.status not in TERMINAL:
            if self.task.status != S.CANCEL_REQUESTED:
                self.transition(S.CANCEL_REQUESTED)
            self.transition(S.CANCELLED)

    def reset_stop(self) -> None:
        """Explicit UI reset after all execution has stopped; never resumes the old task."""
        if self.task and self.task.status not in TERMINAL:
            raise Busy("cannot reset an active task")
        self.stop.clear()

    def pause(self) -> None:
        """Mark pausing, revoke outstanding permits, then await an atomic-operation acknowledgement."""
        self.transition(S.PAUSING)

    def pause_acknowledged(self) -> None:
        """Only call after the input backend has stopped and released its owned keys."""
        self.transition(S.PAUSED)

    def resume(self, fresh: Observation) -> None:
        """Require fresh observation and replan; old actions, coordinates and approvals stay invalid."""
        if self.task is None or self.task.status != S.PAUSED:
            raise InvalidTransition("not paused")
        age = self.clock() - fresh.captured_mono
        if not 0 <= age <= self.task.budget.observation_ms / 1000:
            raise InvalidTransition("fresh observation required")
        self.transition(S.INTERPRETING)
        self.observation = fresh

    def accept_callback(self, task_id: UUID, generation: int, kind: str) -> bool:
        """Check identity and terminality. Late results are audit-only, never instructions."""
        if self.task is None or task_id != self.task.id:
            abandoned = self.store.task(task_id)
            if abandoned and abandoned.status in TERMINAL:
                self.store.commit(abandoned, "callback.ignored", kind)
            return False
        valid = self.task.generation == generation and self.task.status not in TERMINAL and not self.stop.is_set()
        if not valid:
            self.persist(self.task, "callback.ignored", kind)
        return valid

    def finish(self, results: list[Verification]) -> None:
        """Set outcome from host oracle results, never from tool-ok or model prose."""
        if self.task is None or self.task.status not in {S.EXECUTING, S.VERIFYING}:
            raise InvalidTransition("not ready to verify")
        task = self.task
        goal_ids = {goal.id for goal in task.goals}
        if len({r.goal_id for r in results}) != len(results) or any(
            r.task_id != task.id or r.generation != task.generation or r.goal_id not in goal_ids
            or (r.method == "fixture" and task.mode != "test") for r in results
        ):
            raise InvalidTransition("verification binding mismatch")
        if task.status != S.VERIFYING:
            self.transition(S.VERIFYING)
        self.persist(self.task, "verification.finished", "后置检查", verifications=tuple(results))
        required = {goal.id for goal in task.goals if goal.required}
        passed = {r.goal_id for r in results if r.result == "passed" and r.evidence
                  and r.strength == "deterministic" and r.method != "manual"}
        failed = {r.goal_id for r in results if r.result == "failed"}
        if required and required <= passed:
            state, verdict = S.SUCCEEDED, "passed"
        elif required & passed:
            state, verdict = S.PARTIAL, "partial"
        elif required & failed:
            state, verdict = S.FAILED, "failed"
        else:
            state, verdict = S.UNVERIFIED, "unknown"
        self.transition(state, _verified=True, verification_status=verdict)

    def check_timeouts(self) -> None:
        """Enforce wall, active and waiting budgets from a controller tick."""
        task = self.task
        if task is None or task.status in TERMINAL:
            return
        if self.stop.is_set():
            self.cancel()
            return
        now = self.clock()
        active = task.active_ms / 1000 + (now - self._last if task.status not in WAITING else 0)
        wait_limit = {S.WAITING_APPROVAL: task.budget.approval_s, S.WAITING_CLARIFICATION: 90,
                      S.WAITING_USER: 180, S.PAUSED: 300}.get(task.status)
        if now - self._created >= task.budget.wall_s or active >= task.budget.active_s or (
            wait_limit is not None and now - self._wait_since >= wait_limit
        ):
            self.transition(S.TIMED_OUT, error_code="TASK_BUDGET")
