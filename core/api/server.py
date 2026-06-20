"""
core/api/server.py
===================
FastAPI application setup and lifecycle management.

Binds to 127.0.0.1 only — not exposed externally.
Owns ONE shared DownloadController and TaskRegistry.
Can be started in-process (background thread) or standalone.
"""

from __future__ import annotations

import threading
import uvicorn
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.download_controller import DownloadController
from core.api.task_registry import TaskRegistry
from core.api.routes import router, init_routes

                                       
logging.getLogger("uvicorn.access").setLevel(logging.CRITICAL)
logging.getLogger("uvicorn.access").propagate = False
logging.getLogger("uvicorn.error").setLevel(logging.CRITICAL)
logging.getLogger("uvicorn.error").propagate = False
logging.getLogger("uvicorn").setLevel(logging.CRITICAL)
logging.getLogger("uvicorn").propagate = False

# ── Singleton state ──────────────────────────────────────────────────────────

_app: Optional[FastAPI] = None
_controller: Optional[DownloadController] = None
_registry: Optional[TaskRegistry] = None
_server_thread: Optional[threading.Thread] = None

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8008

def _start_token_warmup_thread() -> None:
    def warmup():
        try:
            from core.spotify import _tm
            _tm._warmup_done = False
            print("[Startup] Beginning Spotify token warmup...")
            _tm.get_headers()
            # Validate: probe Spotify to catch server-side revocation
            if not _tm._probe_token():
                print("[Startup] Cached token stale — re-harvesting...")
                with _tm._lock:
                    _tm._bearer = None
                    _tm._expires_at = 0
                    _tm._client_token = ""
                    _tm._client_token_expires_at = 0.0
                _tm.get_headers()
            _tm._warmup_done = True
            print("[Startup] Spotify token warmup complete.")
        except Exception as e:
            try:
                from core.spotify import _tm
                _tm._warmup_done = False
            except Exception:
                pass
            print(f"[Startup] Spotify warmup failed: {e}")

    threading.Thread(target=warmup, daemon=True, name="spotify-warmup").start()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modern FastAPI lifecycle manager to replace on_event('shutdown')."""
    yield                 
                         
    if _controller:
        _controller.shutdown()

def _get_default_download_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("USERPROFILE", Path.home())) / "Downloads"
    else:
        base = Path.home() / "Downloads"
    path = base / "Ember"
    path.mkdir(parents=True, exist_ok=True)
    return path

def create_app(
    download_dir: Optional[Path] = None,
    controller: Optional[DownloadController] = None,
) -> FastAPI:
    """
    Create and configure the FastAPI application.
    """
    global _app, _controller, _registry

    _app = FastAPI(
        title="Spyde API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,                                  
    )

    _app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    @_app.get("/health")
    async def health():
        from core.spotify import _tm
        from fastapi import HTTPException
        if not getattr(_tm, "_warmup_done", False):
            raise HTTPException(status_code=503, detail="Warming up")
        return {"ready": True}

    _app.include_router(router)

    _controller = controller or DownloadController(
        download_dir or _get_default_download_dir()
    )
    _registry = TaskRegistry()

                                              
    init_routes(_controller, _registry)

    _start_token_warmup_thread()

    return _app

def start_background(
    controller: Optional[DownloadController] = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> threading.Thread:
    """Start the API server in a daemon thread. Returns the thread."""
    global _server_thread

    app = create_app(controller=controller)
    
    config = uvicorn.Config(
        app, host=host, port=port,
        log_level="critical",
        access_log=False,
        log_config={
            "version": 1,
            "disable_existing_loggers": True,
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stderr",
                }
            },
            "loggers": {
                "uvicorn": {"handlers": ["default"], "level": "ERROR", "propagate": False},
                "uvicorn.error": {"handlers": ["default"], "level": "ERROR", "propagate": False},
                "uvicorn.access": {"handlers": [], "level": "CRITICAL", "propagate": False},
            },
        },
    )
    server = uvicorn.Server(config)

    _server_thread = threading.Thread(target=server.run, daemon=True, name="spyde-api")
    _server_thread.start()
    return _server_thread

def get_controller() -> Optional[DownloadController]:
    return _controller

def get_registry() -> Optional[TaskRegistry]:
    return _registry

if __name__ == "__main__":
    import sys, os
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    app = create_app()
    uvicorn.run(
        app,
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        log_level="critical",
        access_log=False,
        use_colors=False
    )