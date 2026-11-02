"""Read-only presentation state; no permissions, command queue or OS input."""
from __future__ import annotations

import threading


class ControlActivity:
    """A live execution phase starts only after a committed gateway tool.started.

    Kept outside queued Qt snapshots so a delayed paint cannot replay old activity.
    The UI can only read this value; its visibility never authorizes an action.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._key = None
        self._active = False

    def publish(self, task, event_type: str) -> None:
        """Called by the single writer immediately after its durable commit."""
        with self._lock:
            key = (task.id, task.generation) if task else None
            if key != self._key:
                self._key, self._active = key, False
            if not task or task.mode != "live" or task.status != "EXECUTING":
                self._active = False
            elif event_type == "tool.started":
                self._active = True

    @property
    def active(self) -> bool:
        """Return a copy; consumers cannot change controller state."""
        with self._lock:
            return self._active
