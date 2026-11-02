from assistant.service import TaskService
from assistant.storage import Store


def test_sensitive_text_is_redacted_even_when_control_is_disabled(tmp_path):
    service = TaskService(Store(tmp_path / "state.db"))
    try:
        service.create("输入：验证码是123456")
        assert "123456" not in service.store.tasks()[0].model_dump_json()
        assert all("123456" not in e.model_dump_json() for e in service.store.events(service.task.id))
    finally:
        service.store.close()
