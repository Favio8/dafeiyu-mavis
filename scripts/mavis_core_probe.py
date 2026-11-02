"""Measured core/stop probe. Only isolated test records and owned worker processes."""
from __future__ import annotations

import ctypes
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import threading
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from assistant.actions import FixtureAction
from assistant.contracts import Goal, TaskStatus as S
from assistant.gateway import FixtureBackend, ToolGateway
from assistant.ipc import WorkerSupervisor
from assistant.policy import Policy
from assistant.service import TaskService
from assistant.stop import StopController
from assistant.storage import Store


def main() -> int:
    """Write reproducible measured samples; never report them as GUI operation success rates."""
    import psutil
    process = psutil.Process()
    rss_before = process.memory_info().rss
    path = ROOT / ".scratch/m0-m1/probes" / uuid4().hex / "state-test.db"
    service = TaskService(Store(path))
    timings = []
    for number in range(100):
        started = time.perf_counter()
        authority, backend = object(), FixtureBackend()
        gateway = ToolGateway(service, Policy(), authority, backend)
        task = service.create("核心性能测试", mode="test", goals=(Goal(predicate="fixture.counter_equals"),))
        service.transition(S.INTERPRETING)
        service.transition(S.EXECUTING)
        gateway.observe(backend.observe(service.clock))
        action = FixtureAction(task_id=task.id, generation=task.generation)
        approval = gateway.propose(action)
        permit = gateway.decide(approval.id, allow=True, authority=authority)
        gateway.dispatch(permit.id, action)
        service.finish([backend.verify(service.task, 1)])
        assert service.task.status == S.SUCCEEDED
        timings.append((time.perf_counter() - started) * 1000)
    service.store.close()
    stop_samples = []
    for _ in range(20):
        stop = StopController()
        entered = threading.Event()
        worker = WorkerSupervisor(stop.event, test_mode=True, on_message=lambda m: entered.set() if m.payload == "hang-entered" else None)
        stop.own(worker)
        try:
            worker.start()
            if not worker.ready.wait(10):
                raise RuntimeError("worker did not become ready")
            worker.send("hang")
            if not entered.wait(10):
                raise RuntimeError("fault fixture was not acknowledged")
            actual_worker = psutil.Process(worker.peer_pid)
            stop.trip()
            actual_worker.wait(timeout=1)
            stop_samples.append({"elapsed_ms": stop.last_stop_ms, "child_exited": not actual_worker.is_running(),
                                 "launcher_exited": worker.process.poll() is not None})
        finally:
            worker.close()
    report = {"platform": platform.platform(), "python": platform.python_version(), "machine": platform.machine(),
        "cpu_logical": psutil.cpu_count(), "memory_gib": round(psutil.virtual_memory().total / 1024**3, 2),
        "elevated": bool(ctypes.windll.shell32.IsUserAnAdmin()) if os.name == "nt" else None,
        "versions": {name: metadata.version(name) for name in ["PySide6", "sherpa-onnx", "keyring", "pydantic", "pyinstaller"]},
        "core_samples_ms": timings, "core_p95_ms": statistics.quantiles(timings, n=100, method="inclusive")[94],
        "rss_before_mib": rss_before / 1024**2, "rss_after_mib": process.memory_info().rss / 1024**2,
        "stop_samples": stop_samples, "stop_max_ms": max(item["elapsed_ms"] for item in stop_samples),
        "claims": "100 in-memory fixture tasks; 20 hung private workers; no real input/physical hotkey/network/API benchmark"}
    output = ROOT / ".scratch/m0-m1/evidence/core-probe.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in {"core_samples_ms", "stop_samples"}}, ensure_ascii=False, indent=2))
    return 0 if all(item["child_exited"] and item["elapsed_ms"] < 1000 for item in stop_samples) else 1


if __name__ == "__main__":
    raise SystemExit(main())
