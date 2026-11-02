"""Durability, recovery, exhaustive terminal guards, and honest verification semantics."""
import sqlite3
import threading
from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from assistant.contracts import Budget, Goal, Task, TaskStatus as S, TERMINAL, Verification, VoiceAttempt, utc_now
from assistant.credentials import Credentials, CredentialUnavailable
from assistant.service import Busy, InvalidTransition, TaskService
from assistant.storage import Store


def executing(tmp_path, goals=None):
    service = TaskService(Store(tmp_path / "state.db"))
    service.create("测试", mode="test", goals=goals)
    service.transition(S.INTERPRETING)
    service.transition(S.EXECUTING)
    return service


@pytest.mark.parametrize("terminal", list(TERMINAL))
def test_terminal_is_sticky(tmp_path, terminal):
    service = executing(tmp_path)
    task = service.task
    service.persist(task.model_copy(update={"status": terminal}), "test.terminal")
    with pytest.raises(InvalidTransition):
        service.transition(S.EXECUTING)
    assert not service.accept_callback(task.id, task.generation, "late.success")
    assert service.task.status == terminal
    service.store.close()


@pytest.mark.parametrize("status", [S.CREATED, S.INTERPRETING, S.EXECUTING, S.WAITING_APPROVAL, S.WAITING_USER,
    S.WAITING_CLARIFICATION, S.VERIFYING, S.PAUSING, S.PAUSED])
def test_cancel_preempts_each_active_state(tmp_path, status):
    service = TaskService(Store(tmp_path / "state.db"))
    service.create("测试")
    service.persist(service.task.model_copy(update={"status": status}), "test.state")
    generation = service.task.generation
    service.cancel()
    assert service.task.status == S.CANCELLED and service.task.generation > generation
    with pytest.raises(InvalidTransition):
        service.create("必须明确复位")
    service.reset_stop()
    assert service.create("复位后新任务").id != service.store.tasks()[1].id
    service.store.close()


@pytest.mark.parametrize("result, strength, expected", [("passed", "user_reported", S.UNVERIFIED),
    ("passed", "visual_assisted", S.UNVERIFIED), ("unknown", "deterministic", S.UNVERIFIED),
    ("failed", "deterministic", S.FAILED), ("passed", "deterministic", S.SUCCEEDED)])
def test_verification_strength_and_truth(tmp_path, result, strength, expected):
    service = executing(tmp_path)
    task = service.task
    service.finish([Verification(task_id=task.id, generation=task.generation, goal_id="primary", method="fixture",
                                 result=result, strength=strength, evidence="independent fixture state")])
    assert service.task.status == expected
    service.store.close()


def test_missing_second_goal_is_partial(tmp_path):
    service = executing(tmp_path, (Goal(id="first"), Goal(id="second")))
    task = service.task
    service.finish([Verification(task_id=task.id, generation=task.generation, goal_id="first", method="fixture", result="passed", evidence="fixture")])
    assert service.task.status == S.PARTIAL
    service.store.close()


def test_verification_cannot_bind_to_another_task(tmp_path):
    service = executing(tmp_path)
    with pytest.raises(InvalidTransition):
        service.finish([Verification(task_id=uuid4(), generation=1, goal_id="primary", method="fixture", result="passed", evidence="wrong task")])
    service.store.close()


def test_pause_ack_and_fresh_resume(tmp_path):
    from assistant.gateway import FixtureBackend
    service = executing(tmp_path)
    service.pause()
    assert service.task.status == S.PAUSING
    with pytest.raises(InvalidTransition):
        service.resume(FixtureBackend().observe(service.clock))
    service.pause_acknowledged()
    service.resume(FixtureBackend().observe(service.clock))
    assert service.task.status == S.INTERPRETING
    service.store.close()


def test_timeout_uses_monotonic_clock_and_waiting_budget(tmp_path):
    now = [100.0]
    service = TaskService(Store(tmp_path / "state.db"), clock=lambda: now[0])
    service.create("等待")
    service.transition(S.INTERPRETING)
    service.transition(S.WAITING_CLARIFICATION)
    now[0] += 91
    service.check_timeouts()
    assert service.task.status == S.TIMED_OUT
    assert service.task.waiting_ms == 91000 and service.task.active_ms == 0
    service.store.close()


def test_transaction_rollback_and_unique_sequence(tmp_path):
    store = Store(tmp_path / "state.db")
    service = TaskService(store)
    task = service.create("一致性")
    with pytest.raises(sqlite3.IntegrityError):
        with store.db:
            store.db.execute("UPDATE tasks SET status='EXECUTING'")
            store.db.execute("INSERT INTO events SELECT * FROM events")
    assert store.db.execute("SELECT status FROM tasks").fetchone()[0] == "CREATED"
    assert len(store.events(task.id)) == 1
    seen = []
    service.subscribers.append(lambda event: seen.append(store.events(task.id)[-1].event_id))
    service.transition(S.INTERPRETING)
    assert seen == [store.events(task.id)[-1].event_id]
    store.close()


def test_single_writer_thread_and_active_db_index(tmp_path):
    store = Store(tmp_path / "state.db")
    service = TaskService(store)
    service.create("one")
    with pytest.raises(sqlite3.IntegrityError):
        store.commit(Task(original_text="two", final_text="two"), "task.created")
    errors = []
    def other_thread():
        try:
            store.tasks()
        except RuntimeError as exc:
            errors.append(str(exc))
    thread = threading.Thread(target=other_thread)
    thread.start()
    thread.join(3)
    assert errors == ["SQLite access must stay on its controller thread"]
    store.close()


def test_unknown_legacy_schema_is_backed_up_not_overwritten(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE legacy(value)")
        db.execute("INSERT INTO legacy VALUES('preserved')")
    with pytest.raises(ValueError, match="legacy"):
        Store(path)
    with sqlite3.connect(path.with_name("legacy.db.pre-v1.bak")) as backup:
        assert backup.execute("SELECT value FROM legacy").fetchone()[0] == "preserved"
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 0


def test_retention_keeps_active_task_and_redacts_key(tmp_path):
    service = TaskService(Store(tmp_path / "state.db"))
    task = service.create("key=sk-not-a-real-secret")
    service.cancel()
    assert "sk-not-a-real-secret" not in service.store.tasks()[0].model_dump_json()
    service.reset_stop()
    active = service.create("active")
    removed = service.store.retain((utc_now() + timedelta(days=1)).isoformat())
    assert removed == 1 and service.store.tasks()[0].id == active.id
    assert not service.store.events(task.id)
    service.store.close()


@pytest.mark.parametrize("values", [dict(active_s=-1), dict(wall_s=60, active_s=180), dict(actions=40, tools=5), dict(approval_s=0)])
def test_budget_bounds(values):
    with pytest.raises(ValidationError):
        Budget(**values)


def test_voice_no_environment_transcript():
    with pytest.raises(ValidationError):
        VoiceAttempt(trigger="wakeword", audio_duration_ms=1000, result="no_speech", asr_text="ambient", model_id="test", model_hash="unknown")


def test_vault_failure_never_writes_plaintext(tmp_path):
    class Broken:
        def set_password(self, *args):
            raise RuntimeError("secret detail must not escape")
    with pytest.raises(CredentialUnavailable, match="^VAULT_WRITE_FAILED$"):
        Credentials(Broken()).save("deepseek/default", "not-a-real-key")
    assert list(tmp_path.iterdir()) == []
