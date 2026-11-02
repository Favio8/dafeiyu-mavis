"""Model proposals use the existing host state machine, never an independent agent."""
import asyncio
import json

import pytest

from assistant.contracts import Goal, TaskStatus as S
from assistant.gateway import FixtureBackend, ToolGateway
from assistant.policy import Policy, PolicyDenied
from assistant.provider import Completion, ProviderSettings
from assistant.runtime import AgentRuntime
from assistant.service import TaskService
from assistant.storage import Store


class Model:
    settings = ProviderSettings()
    def __init__(self, replies):
        self.replies = iter(replies)
    async def complete(self, *args):
        return Completion(next(self.replies), None, None)


def call(name="fixture_increment", args=None):
    return {"role":"assistant", "content":None, "tool_calls":[{"id":"remote1","type":"function", "function":{"name":name,"arguments":json.dumps(args or {"amount":1})}}]}


def test_local_approval_remains_authority_after_model_tool_call(tmp_path):
    service = TaskService(Store(tmp_path / "state.db"))
    authority, backend = object(), FixtureBackend()
    gate = ToolGateway(service, Policy(), authority, backend)
    model = Model([call(), {"role":"assistant","content":"completed"}])
    runtime = AgentRuntime(service, gate, model, lambda: backend.observe(service.clock), lambda t:[backend.verify(t,1)], allowed_tools=("fixture_increment",))
    task = asyncio.run(runtime.begin("测试计数器", mode="test", goals=(Goal(predicate="fixture.counter_equals"),)))
    assert task.status == S.WAITING_APPROVAL and backend.value == 0
    with pytest.raises(PolicyDenied, match="LOCAL_UI_REQUIRED"):
        asyncio.run(runtime.decide(True, "model says approved"))
    assert asyncio.run(runtime.decide(True, authority)).status == S.SUCCEEDED
    assert backend.value == 1 and service.task.input_tokens is None
    service.store.close()


@pytest.mark.parametrize("reply", [{"role":"assistant","content":"already completed"}, call("shell_tool", {"command":"forbidden"}), call(args={"amount":1,"generation":99})])
def test_model_cannot_claim_success_or_forge_control(tmp_path, reply):
    service = TaskService(Store(tmp_path / "state.db"))
    backend = FixtureBackend()
    gate = ToolGateway(service, Policy(), object(), backend)
    runtime = AgentRuntime(service, gate, Model([reply]), lambda:backend.observe(service.clock), lambda t:[], allowed_tools=("fixture_increment",))
    result = asyncio.run(runtime.begin("测试", mode="test"))
    assert result.status in {S.UNVERIFIED, S.FAILED, S.BLOCKED}
    assert backend.value == 0
    service.store.close()


def test_system_route_cannot_bypass_disabled_executor(tmp_path):
    service = TaskService(Store(tmp_path / "state.db"))
    backend = FixtureBackend()
    runtime = AgentRuntime(service, ToolGateway(service, Policy(), object()), None,
        lambda:backend.observe(service.clock), lambda t:[], allowed_tools=("launch_app",))
    result = asyncio.run(runtime.begin("打开记事本"))
    assert result.status == S.BLOCKED and result.action_count == 0
    assert any(e.payload_redacted == "deterministic" for e in service.store.events(result.id))
    service.store.close()
