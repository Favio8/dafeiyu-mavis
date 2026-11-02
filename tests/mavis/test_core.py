"""M1 safety requirements at the public controller boundary (no real input)."""
import pytest
from pydantic import ValidationError

from assistant.contracts import Task, TaskStatus, Verification
from assistant.service import TaskService, Busy, InvalidTransition
from assistant.storage import Store


def test_strict_contracts_and_unknown_metrics():
    task = Task(original_text="测试", final_text="测试")
    assert task.input_tokens is None and task.cost_estimate is None
    assert Task.model_validate_json(task.model_dump_json()) == task
    with pytest.raises(ValidationError):
        Task(original_text="x", final_text="x", api_key="forbidden")
    with pytest.raises(ValidationError):
        Task(original_text="", final_text="")


def test_single_task_terminal_and_late_callbacks(tmp_path):
    service = TaskService(Store(tmp_path / "state.db"))
    task = service.create("测试", mode="test")
    with pytest.raises(Busy):
        service.create("第二条")
    service.cancel()
    assert service.task.status == TaskStatus.CANCELLED
    assert not service.accept_callback(task.id, task.generation, "tool.finished")
    with pytest.raises(InvalidTransition):
        service.transition(TaskStatus.EXECUTING)


def test_tool_ok_is_not_goal_success(tmp_path):
    service = TaskService(Store(tmp_path / "state.db"))
    service.create("测试", mode="test")
    service.transition(TaskStatus.INTERPRETING)
    service.transition(TaskStatus.EXECUTING)
    with pytest.raises(InvalidTransition):
        service.transition(TaskStatus.SUCCEEDED)
    service.finish([])
    assert service.task.status == TaskStatus.UNVERIFIED


def test_crash_recovery_revokes_tasks(tmp_path):
    path = tmp_path / "state.db"
    first = TaskService(Store(path))
    first.create("未结束", mode="test")
    first.store.close()
    second = TaskService(Store(path))
    assert second.store.tasks()[0].status == TaskStatus.INTERRUPTED
    assert second.task is None
