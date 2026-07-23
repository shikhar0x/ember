"""
core/api/task_registry.py
==========================
In-memory task tracking for the local API.

Maps task_id → { future, events[], latest_payload, state, cancel_event, sub_futures[] }.
Thread-safe: all mutations go through a lock.
"""

from __future__ import annotations

import threading
import uuid
import concurrent.futures
from typing import Callable, Optional


_active_registry: Optional[TaskRegistry] = None


class TaskRegistry:
    """Thread-safe registry of download tasks and their event streams."""

    def __init__(self):
        global _active_registry
        self._tasks: dict[str, dict] = {}
        self._lock = threading.Lock()
        _active_registry = self

    def create(self, future: concurrent.futures.Future) -> str:
        """Register a new task and return its UUID."""
        task_id = uuid.uuid4().hex[:12]
        pause_event = threading.Event()
        pause_event.set()
        cancel_event = threading.Event()
        with self._lock:
            self._tasks[task_id] = {
                "future": future,
                "state": "running",
                "latest": None,
                "events": [],
                "pause_event": pause_event,
                "cancel_event": cancel_event,
                "sub_futures": [],
            }

        def _on_done(f):
            with self._lock:
                entry = self._tasks.get(task_id)
                if entry and entry["state"] in ("running", "paused"):
                    if f.cancelled():
                        entry["state"] = "cancelled"
                    elif f.exception():
                        entry["state"] = "error"
                    else:
                        entry["state"] = "complete"
        future.add_done_callback(_on_done)
        return task_id

    def register_sub_future(self, task_id: str, sub_future: concurrent.futures.Future) -> None:
        """Register a sub-future (e.g. individual playlist track download) to be cancelled with the main task."""
        with self._lock:
            entry = self._tasks.get(task_id)
            if entry:
                entry["sub_futures"].append(sub_future)

    def make_callback(self, task_id: str) -> Callable[[dict], None]:
        """Return a callback that appends payloads to this task's event stream."""
        def _cb(payload: dict):
            with self._lock:
                entry = self._tasks.get(task_id)
                if entry is None:
                    return
                cancel_ev = entry.get("cancel_event")
                pause_ev = entry.get("pause_event")

            if cancel_ev and cancel_ev.is_set():
                from core.events import TaskCancelledException
                raise TaskCancelledException("Task was cancelled")

            if pause_ev:
                pause_ev.wait()

            if cancel_ev and cancel_ev.is_set():
                from core.events import TaskCancelledException
                raise TaskCancelledException("Task was cancelled")

            with self._lock:
                entry = self._tasks.get(task_id)
                if entry is None:
                    return
                entry["events"].append(payload)
                entry["latest"] = payload
                
                t = payload.get("type")
                if t == "complete":
                    entry["state"] = "complete"
                elif t == "error":
                    entry["state"] = "error"
                elif t == "batch_end":
                    entry["state"] = "complete"

        _cb.task_id = task_id
        _cb.is_cancelled = lambda: self._tasks.get(task_id, {}).get("cancel_event", threading.Event()).is_set()
        return _cb

    def get(self, task_id: str) -> Optional[dict]:
        """Return task status snapshot (without the Future object)."""
        with self._lock:
            entry = self._tasks.get(task_id)
            if entry is None:
                return None
            return {
                "task_id": task_id,
                "state": entry["state"],
                "latest": entry["latest"],
                "events": list(entry["events"]),
            }

    def get_events_since(self, task_id: str, cursor: int = 0) -> Optional[dict]:
        """Return events from *cursor* onward (for incremental polling)."""
        with self._lock:
            entry = self._tasks.get(task_id)
            if entry is None:
                return None
            evts = entry["events"][cursor:]
            return {
                "task_id": task_id,
                "state": entry["state"],
                "cursor": cursor + len(evts),
                "events": evts,
            }

    def cancel(self, task_id: str) -> tuple[bool, str]:
        """Attempt to cancel a task and all of its sub-futures. Returns (cancelled, message)."""
        with self._lock:
            entry = self._tasks.get(task_id)
            if entry is None:
                return False, "Task not found"
            if entry["state"] in ("complete", "error", "cancelled"):
                return False, f"Task already {entry['state']}"

            entry["cancel_event"].set()

            fut: concurrent.futures.Future = entry["future"]
            fut.cancel()

            for sf in entry.get("sub_futures", []):
                sf.cancel()

            entry["state"] = "cancelled"
            return True, "Cancelled"

    def pause(self, task_id: str) -> tuple[bool, str]:
        """No-op: pause is not supported. Returns success without changing state."""
        with self._lock:
            entry = self._tasks.get(task_id)
            if entry is None:
                return False, "Task not found"
            # Ensure pause_event is always set so workers never block
            entry["pause_event"].set()
            # Do not change state; keep it as is
            return True, "Pause ignored (not supported)"

    def resume(self, task_id: str) -> tuple[bool, str]:
        """No-op: resume is not supported. Returns success without changing state."""
        with self._lock:
            entry = self._tasks.get(task_id)
            if entry is None:
                return False, "Task not found"
            # Ensure pause_event is always set
            entry["pause_event"].set()
            return True, "Resume ignored (not supported)"

    def get_pause_event(self, task_id: str) -> Optional[threading.Event]:
        """Return the pause event for a task so download workers can check it."""
        with self._lock:
            entry = self._tasks.get(task_id)
            if entry:
                return entry["pause_event"]
            return None

    def cleanup(self, max_age: int = 500) -> None:
        """Remove completed tasks (called periodically). max_age = max events to keep."""
        with self._lock:
            to_remove = [
                tid for tid, e in self._tasks.items()
                if e["state"] in ("complete", "error", "cancelled")
                and len(e["events"]) > max_age
            ]
            for tid in to_remove:
                del self._tasks[tid]
