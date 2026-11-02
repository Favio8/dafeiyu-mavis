"""Approval/TOCTOU/replay/storage safety tests; effects are isolated fixture counters."""
import sqlite3
from dataclasses import replace
from uuid import uuid4

import pytest

from assistant.actions import FixtureAction
from assistant.contracts import Goal, TaskStatus as S
from assistant.gateway import FixtureBackend, ToolGateway
from assistant.policy import Policy, PolicyDenied
from assistant.service import TaskService
from assistant.storage import Store


@pytest.fixture
def rig(tmp_path):
    now = [100.0]
    service = TaskService(Store(tmp_path / "state.db"), clock=lambda: now[0])
    authority = object()
    backend = FixtureBackend()
    gateway = ToolGateway(service, Policy(), authority, backend)
    task = service.create("审批测试", mode="test", goals=(Goal(predicate="fixture.counter_equals"),))
    service.transition(S.INTERPRETING)
    service.transition(S.EXECUTING)
    gateway.observe(backend.observe(service.clock))
    action = FixtureAction(task_id=task.id, generation=task.generation)
    yield service, gateway, backend, authority, action, now
    service.store.close()


def test_no_effect_before_local_approval_and_one_use(rig):
    service, gateway, backend, authority, action, _ = rig
    approval = gateway.propose(action)
    assert backend.value == 0 and service.task.status == S.WAITING_APPROVAL
    with pytest.raises(PolicyDenied, match="LOCAL_UI_REQUIRED"):
        gateway.decide(approval.id, allow=True, authority="local_ui")
    permit = gateway.decide(approval.id, allow=True, authority=authority)
    assert backend.value == 0
    result = gateway.dispatch(permit.id, action)
    assert result.status == "ok" and backend.value == 1
    assert service.task.status == S.EXECUTING
    with pytest.raises(PolicyDenied):
        gateway.dispatch(permit.id, action)
    service.finish([backend.verify(service.task, 1)])
    assert service.task.status == S.SUCCEEDED
    assert service.store.approvals(service.task.id)[0].status == "consumed"
    seq = [event.seq for event in service.store.events(service.task.id)]
    assert seq == list(range(1, len(seq) + 1))


@pytest.mark.parametrize("mutation", ["amount", "generation", "task", "tool_call"])
def test_modified_action_burns_grant_without_effect(rig, mutation):
    service, gateway, backend, authority, action, _ = rig
    approval = gateway.propose(action)
    permit = gateway.decide(approval.id, allow=True, authority=authority)
    changed = {"amount": {"amount": 2}, "generation": {"generation": 9}, "task": {"task_id": uuid4()},
               "tool_call": {"tool_call_id": uuid4()}}[mutation]
    with pytest.raises(PolicyDenied):
        gateway.dispatch(permit.id, action.model_copy(update=changed))
    assert backend.value == 0
    with pytest.raises(PolicyDenied):
        gateway.dispatch(permit.id, action)


@pytest.mark.parametrize("event", ["cancel", "pause", "focus", "permission", "expire", "scope"])
def test_revocation_paths(rig, event):
    service, gateway, backend, authority, action, now = rig
    approval = gateway.propose(action)
    permit = gateway.decide(approval.id, allow=True, authority=authority)
    if event == "cancel":
        service.cancel()
    elif event == "pause":
        service.pause()
    elif event == "focus":
        gateway.observe(backend.observe(service.clock).model_copy(update={"context_digest": "f" * 64}))
    elif event == "permission":
        gateway.revoke_permission()
    elif event == "expire":
        now[0] += 61
        gateway.observe(backend.observe(service.clock))
    else:
        gateway.policy.scope = replace(gateway.policy.scope, version=2)
    with pytest.raises(PolicyDenied):
        gateway.dispatch(permit.id, action)
    assert backend.value == 0


def test_denied_and_expired_approval(rig):
    service, gateway, backend, authority, action, now = rig
    approval = gateway.propose(action)
    now[0] += 60
    with pytest.raises(PolicyDenied, match="APPROVAL_EXPIRED"):
        gateway.decide(approval.id, allow=True, authority=authority)
    assert service.task.status == S.TIMED_OUT
    assert backend.value == 0


def test_refusal_is_terminal(rig):
    service, gateway, backend, authority, action, _ = rig
    approval = gateway.propose(action)
    gateway.decide(approval.id, allow=False, authority=authority)
    assert service.task.status == S.CANCELLED and backend.value == 0
    with pytest.raises(PolicyDenied):
        gateway.decide(approval.id, allow=True, authority=authority)


def test_database_locked_prevents_effect(rig):
    service, gateway, backend, authority, action, _ = rig
    approval = gateway.propose(action)
    permit = gateway.decide(approval.id, allow=True, authority=authority)
    other = sqlite3.connect(service.store.path)
    other.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(sqlite3.OperationalError):
            gateway.dispatch(permit.id, action)
        assert service.stop.is_set() and backend.value == 0 and not gateway.permits
    finally:
        other.rollback()
        other.close()


def test_disk_error_prevents_effect(rig, monkeypatch):
    service, gateway, backend, authority, action, _ = rig
    approval = gateway.propose(action)
    permit = gateway.decide(approval.id, allow=True, authority=authority)
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("database or disk is full")
    monkeypatch.setattr(service.store, "commit", fail)
    with pytest.raises(sqlite3.Error):
        gateway.dispatch(permit.id, action)
    assert service.stop.is_set() and backend.value == 0


def test_stop_between_intent_and_backend(rig):
    service, gateway, backend, authority, action, _ = rig
    approval = gateway.propose(action)
    permit = gateway.decide(approval.id, allow=True, authority=authority)
    service.subscribers.append(lambda event: service.stop.set() if event.type == "tool.started" else None)
    assert gateway.dispatch(permit.id, action).status == "cancelled"
    assert backend.value == 0 and service.task.status == S.CANCELLED
