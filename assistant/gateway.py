"""Host-owned action gate and one-use permits. M1 has no real input backend."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from .actions import FixtureAction
from .contracts import Approval, Observation, Step, TaskStatus as S, ToolResult, Verification, utc_now
from .policy import Policy, PolicyDenied, digest
from .privacy import redact
from .service import TaskService


@dataclass(frozen=True)
class Permit:
    """Memory-only capability; exact action and context, bounded lifetime, one use."""
    id: UUID
    action_digest: str
    context_digest: str
    task_id: UUID
    generation: int
    scope_version: int
    expires_mono: float
    approval_id: UUID | None


class FixtureBackend:
    """Explicit test backend: mutate only its own in-memory counter, never Windows."""
    def __init__(self):
        self.value = 0

    def observe(self, clock) -> Observation:
        """Produce a deterministic fixture observation for policy tests and UI exercises."""
        return Observation(captured_mono=clock(), context_digest=digest({"fixture_counter": self.value}), app="mavis.fixture")

    def execute(self, action, stop) -> str:
        """Perform one bounded test action after the host gate has committed intent."""
        if not isinstance(action, FixtureAction):
            raise PolicyDenied("REAL_BACKEND_NOT_CONNECTED")
        if stop.is_set():
            raise PolicyDenied("STOPPED")
        self.value += action.amount
        return f"测试计数器增加 {action.amount}；没有操作电脑"

    def verify(self, task, expected: int) -> Verification:
        """Read the fixture state independently of execute's return value."""
        return Verification(task_id=task.id, generation=task.generation, goal_id="primary", method="fixture",
                            result="passed" if self.value == expected else "failed",
                            evidence=f"counter={self.value}; expected={expected}")


class ToolGateway:
    """Validate, request local approval, commit intent, consume permit, then dispatch.

    `ui_authority` is an identity object kept in the host, never a worker field.
    It is an application boundary, not a sandbox against arbitrary local code.
    """
    def __init__(self, service: TaskService, policy: Policy, ui_authority: object,
                 backend: FixtureBackend | None = None):
        self.service, self.policy = service, policy
        self._ui_authority = ui_authority
        self.backend = backend
        self.permits: dict[UUID, Permit] = {}
        self.approvals: dict[UUID, Approval] = {}
        self.actions: dict[UUID, object] = {}
        self.steps: dict[UUID, Step] = {}
        self.deadlines: dict[UUID, float] = {}
        self.service.invalidate = self.revoke

    def revoke(self) -> tuple[Approval, ...]:
        """Invalidate all unused capabilities immediately; return audit updates to persist."""
        self.permits.clear()
        changed = []
        for key, approval in tuple(self.approvals.items()):
            if approval.status in ("pending", "approved"):
                updated = approval.model_copy(update={"status": "revoked"})
                self.approvals[key] = updated
                changed.append(updated)
        return tuple(changed)

    def observe(self, observation: Observation) -> None:
        """Accept only a host observation. Context changes pause and invalidate pending work."""
        previous = self.service.observation
        if previous and previous.context_digest != observation.context_digest:
            if self.service.task and self.service.task.status in {S.EXECUTING, S.WAITING_APPROVAL}:
                self.service.pause()
        self.service.observation = observation

    def _validate(self, action):
        service, task = self.service, self.service.task
        if not task or task.status not in {S.EXECUTING, S.WAITING_APPROVAL} or service.stop.is_set():
            raise PolicyDenied("TASK_NOT_EXECUTABLE")
        if action.task_id != task.id or action.generation != task.generation:
            raise PolicyDenied("STALE_ACTION")
        if service.observation is None:
            raise PolicyDenied("NO_OBSERVATION")
        if task.action_count >= task.budget.actions or task.tool_call_count >= task.budget.tools:
            raise PolicyDenied("ACTION_BUDGET")
        return self.policy.evaluate(action, service.observation, mode=task.mode, now=service.clock(), max_age_ms=task.budget.observation_ms)

    def propose(self, action) -> Approval | Permit:
        """Persist a proposal; R1 waits for UI, R0 obtains an exact one-use permit."""
        if self.service.task is None or self.service.task.status != S.EXECUTING:
            raise PolicyDenied("TASK_NOT_EXECUTABLE")
        if any(p.task_id == self.service.task.id for p in self.permits.values()):
            raise PolicyDenied("ONE_PENDING_ACTION")
        action, risk = self._validate(action)
        if action.tool_call_id in self.actions:
            raise PolicyDenied("REPLAYED_TOOL_CALL")
        task, observation = self.service.task, self.service.observation
        step = Step(task_id=task.id, seq=sum(s.task_id == task.id for s in self.steps.values()) + 1,
                    tool_call_id=action.tool_call_id, tool_name=action.tool,
                    args_redacted=redact(action.model_dump_json()), action_digest=digest(action), risk=risk,
                    observation_id=observation.id, status="awaiting_approval" if risk == "R1" else "proposed")
        approval = None
        if risk == "R1":
            approval = Approval(task_id=task.id, tool_call_id=action.tool_call_id, action_digest=digest(action),
                                context_digest=observation.context_digest, generation=task.generation,
                                expires_at=utc_now() + timedelta(seconds=task.budget.approval_s))
        self.service.persist(task, "tool.proposed", action.tool, step=step,
                             approvals=(approval,) if approval else (), observation=observation)
        self.actions[action.tool_call_id], self.steps[action.tool_call_id] = action, step
        if approval:
            self.approvals[approval.id] = approval
            self.deadlines[approval.id] = self.service.clock() + task.budget.approval_s
            self.service.transition(S.WAITING_APPROVAL)
            return approval
        return self._issue(action, None)

    def _issue(self, action, approval: Approval | None) -> Permit:
        task, observation = self.service.task, self.service.observation
        permit = Permit(uuid4(), digest(action), observation.context_digest, task.id, task.generation,
                        self.policy.scope.version,
                        self.deadlines[approval.id] if approval else self.service.clock() + task.budget.approval_s,
                        approval.id if approval else None)
        self.permits[permit.id] = permit
        return permit

    def decide(self, approval_id: UUID, *, allow: bool, authority: object) -> Permit | None:
        """Only the host's local UI capability may approve; voice/model messages cannot."""
        if authority is not self._ui_authority:
            raise PolicyDenied("LOCAL_UI_REQUIRED")
        approval = self.approvals.get(approval_id)
        if approval is None or approval.status != "pending":
            raise PolicyDenied("APPROVAL_NOT_PENDING")
        action = self.actions[approval.tool_call_id]
        if self.service.clock() >= self.deadlines[approval_id]:
            expired = approval.model_copy(update={"status": "expired"})
            self.approvals[approval_id] = expired
            self.service.persist(self.service.task, "approval.expired", approvals=(expired,))
            self.service.transition(S.TIMED_OUT)
            raise PolicyDenied("APPROVAL_EXPIRED")
        self._validate(action)
        if approval.context_digest != self.service.observation.context_digest:
            raise PolicyDenied("CONTEXT_CHANGED")
        if not allow:
            denied = approval.model_copy(update={"status": "denied", "decision_source": "local_ui"})
            self.approvals[approval_id] = denied
            self.service.persist(self.service.task, "approval.decided", "denied", approvals=(denied,))
            self.service.cancel()
            return None
        permit = self._issue(action, approval)
        approved = approval.model_copy(update={"status": "approved", "decision_source": "local_ui", "grant_id": permit.id})
        try:
            self.service.persist(self.service.task, "approval.decided", "approved", approvals=(approved,))
            self.approvals[approval_id] = approved
            self.service.transition(S.EXECUTING)
        except (OSError, RuntimeError):
            self.permits.pop(permit.id, None)
            raise
        return permit

    def dispatch(self, permit_id: UUID, action) -> ToolResult:
        """Consume before effect, recheck context and policy, and never retry unknown effects."""
        # Pop first: even a mismatched/expired attempt burns the capability.
        permit = self.permits.pop(permit_id, None)
        if permit is None:
            raise PolicyDenied("PERMIT_UNKNOWN_OR_CONSUMED")
        action, _risk = self._validate(action)
        task, observation = self.service.task, self.service.observation
        if task.status != S.EXECUTING or permit.action_digest != digest(action) or permit.context_digest != observation.context_digest:
            raise PolicyDenied("PERMIT_BINDING_MISMATCH")
        if permit.task_id != task.id or permit.generation != task.generation or permit.scope_version != self.policy.scope.version:
            raise PolicyDenied("PERMIT_REVOKED")
        if self.service.clock() >= permit.expires_mono:
            raise PolicyDenied("PERMIT_EXPIRED")
        if isinstance(action, FixtureAction):
            if task.mode != "test" or not isinstance(self.backend, FixtureBackend):
                raise PolicyDenied("TEST_ONLY")
        else:
            from .system_backend import RegisteredSystemBackend
            if not isinstance(self.backend, RegisteredSystemBackend) or not self.backend.permits(action):
                raise PolicyDenied("REAL_BACKEND_NOT_CONNECTED")
            self.backend.bind(observation)
        approvals = ()
        if permit.approval_id:
            approval = self.approvals[permit.approval_id].model_copy(update={"status": "consumed"})
            self.approvals[approval.id] = approval
            approvals = (approval,)
        started = self.steps[action.tool_call_id].model_copy(update={"status": "running", "started_at": utc_now()})
        counted = task.model_copy(update={"action_count": task.action_count + 1, "tool_call_count": task.tool_call_count + 1})
        self.service.persist(counted, "tool.started", action.tool, step=started, approvals=approvals)
        begin = self.service.clock()
        # No blocking network/LLM call is made on this M1 path. A watchdog can set
        # the latch independently; real M2 primitives must repeat this same guard.
        try:
            effect = self.backend.execute(action, self.service.stop)
            status, error = "ok", None
        except PolicyDenied as exc:
            effect, status, error = "", "cancelled" if self.service.stop.is_set() else "error", str(exc)
        except (OSError, RuntimeError):
            effect, status, error = "结果未知；不自动重试", "unknown", "BACKEND_RESULT_UNKNOWN"
        elapsed = max(0, int((self.service.clock() - begin) * 1000))
        result = ToolResult(task_id=task.id, tool_call_id=action.tool_call_id, status=status, effect=effect, error_code=error, elapsed_ms=elapsed)
        ended = started.model_copy(update={"status": {"ok": "succeeded", "error": "failed", "unknown": "unknown", "cancelled": "cancelled"}[status],
                                          "ended_at": utc_now(), "elapsed_ms": elapsed})
        self.steps[action.tool_call_id] = ended
        current = self.service.task
        if effect:
            current = current.model_copy(update={"effects": (*current.effects, effect)})
        self.service.persist(current, "tool.finished", result.model_dump_json(), step=ended)
        if self.service.stop.is_set():
            self.service.cancel()
        return result

    def revoke_permission(self) -> None:
        """Security revocation takes effect immediately, including on an active task."""
        from dataclasses import replace
        self.policy.scope = replace(self.policy.scope, enabled=False, version=self.policy.scope.version + 1)
        self.service.cancel()
