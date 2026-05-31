"""
core/api/task_registry.py
==========================
In-memory task tracking for the local API.

Maps task_id → { future, events[], latest_payload, state }.
Thread-safe: all mutations go through a lock.
"""

from __future__ import annotations

import threading
import uuid
import concurrent.futures
from typing import Callable, Optional


class TaskRegistry:
    """Thread-safe registry of download tasks and their event streams."""

    def __init__(self):
        self._tasks: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create(self, future: concurrent.futures.Future) -> str:
        """Register a new task and return its UUID."""
        task_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._tasks[task_id] = {
                "future": future,
                "state": "running",
                "latest": None,
                "events": [],
            }

                                                       
        def _on_done(f):
            with self._lock:
                entry = self._tasks.get(task_id)
                if entry and entry["state"] == "running":
                    if f.cancelled():
                        entry["state"] = "cancelled"
                    elif f.exception():
                        entry["state"] = "error"
                    else:
                        entry["state"] = "complete"
        future.add_done_callback(_on_done)
        return task_id

    def make_callback(self, task_id: str) -> Callable[[dict], None]:
        """Return a callback that appends payloads to this task's event stream."""
        def _cb(payload: dict):
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
        """Attempt to cancel a task. Returns (cancelled, message)."""
        with self._lock:
            entry = self._tasks.get(task_id)
            if entry is None:
                return False, "Task not found"
            if entry["state"] != "running":
                return False, f"Task already {entry['state']}"
            fut: concurrent.futures.Future = entry["future"]
            ok = fut.cancel()
            if ok:
                entry["state"] = "cancelled"
                return True, "Cancelled"
            return False, "Task already executing — cannot cancel"

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
