"""
core/events.py
===============
Structured event payload constructors for backend → frontend communication.

Every backend callback emits ONE dict payload with a ``type`` field.
This makes the backend protocol frontend-agnostic: the same payloads
can drive a CTk GUI, a Tauri frontend, a CLI, or a local API.

Payload types:
    progress  — download/processing progress update
    status    — transient UI hint (e.g. button text change)
    complete  — final success/failure result
    error     — non-recoverable error
    batch     — per-track completion in a playlist batch
    batch_end — playlist batch finished
"""

from __future__ import annotations

from typing import Optional


# ── Constructors ──────────────────────────────────────────────────────────────

def progress_event(progress: float, message: str) -> dict:
    """Emit a progress update (0.0–1.0)."""
    return {
        "type": "progress",
        "progress": progress,
        "message": message,
    }


def status_event(message: str) -> dict:
    """Emit a transient status hint (e.g. button text)."""
    return {
        "type": "status",
        "message": message,
    }


def complete_event(success: bool, message: str) -> dict:
    """Emit a final success/failure result."""
    return {
        "type": "complete",
        "success": success,
        "message": message,
    }


def error_event(message: str) -> dict:
    """Emit a non-recoverable error."""
    return {
        "type": "error",
        "success": False,
        "message": message,
    }


def batch_event(
    completed: int,
    total: int,
    succeeded: int,
    failed: int,
) -> dict:
    """Emit per-track progress within a playlist batch."""
    return {
        "type": "batch",
        "completed": completed,
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "progress": completed / total if total else 0.0,
        "message": f"Progress: {completed}/{total}",
    }


def batch_end_event(succeeded: int, failed: int) -> dict:
    """Emit final batch summary."""
    msg = f"{succeeded}/{succeeded + failed} succeeded"
    if failed:
        msg += f", {failed} failed"
    return {
        "type": "batch_end",
        "success": failed == 0,
        "succeeded": succeeded,
        "failed": failed,
        "message": msg,
    }


# ── Dispatcher ────────────────────────────────────────────────────────────────

def emit(callback, payload: dict) -> None:
    """Safely deliver a payload to *callback*, swallowing exceptions."""
    if callback is None:
        return
    try:
        callback(payload)
    except Exception as e:
        print(f"[events] callback error: {e}")
