"""
core/ffmpeg_manager.py
=======================
Dedicated singleton manager for proactive FFmpeg acquisition at startup.

State machine: IDLE → DOWNLOADING → EXTRACTING → READY (or → FAILED)
- Progressive download with progress callback (exposed via status API)
- Fallback mirrors: ffbinaries.com → GitHub releases
- Integrity validation: ffmpeg -version post-extraction, retry up to 2 times
- Thread-safe with threading.Event to block download workers until READY
"""

from __future__ import annotations

import os
import sys
import json
import time
import zipfile
import urllib.request
import urllib.error
import subprocess
import threading
import platform
from pathlib import Path
from dataclasses import dataclass, field
from typing import Callable, Optional, Literal

FFmpegState = Literal["IDLE", "DOWNLOADING", "EXTRACTING", "READY", "FAILED"]


@dataclass
class FFmpegProgress:
    state: FFmpegState = "IDLE"
    progress: float = 0.0  # 0.0–1.0
    message: str = ""
    retry_count: int = 0
    error: Optional[str] = None
    ffmpeg_path: Optional[str] = None


class FFmpegManager:
    """
    Thread-safe singleton manager for proactive FFmpeg acquisition.
    Blocks download workers until the READY state is reached via a threading.Event.
    """

    _instance = None
    _lock = threading.Lock()
    _state_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._progress = FFmpegProgress(state="IDLE", progress=0.0, message="Initializing...")
        self._ready_event = threading.Event()
        self._state_lock = threading.Lock()
        self._bin_dir = Path.home() / ".ember" / "bin"
        self._initialized = True

    # ------------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------------

    @property
    def state(self) -> FFmpegState:
        with self._state_lock:
            return self._progress.state

    @property
    def progress(self) -> float:
        with self._state_lock:
            return self._progress.progress

    @property
    def message(self) -> str:
        with self._state_lock:
            return self._progress.message

    @property
    def ffmpeg_path(self) -> Optional[str]:
        with self._state_lock:
            return self._progress.ffmpeg_path

    @property
    def error(self) -> Optional[str]:
        with self._state_lock:
            return self._progress.error

    @property
    def is_ready(self) -> bool:
        return self._ready_event.is_set()

    @property
    def is_failed(self) -> bool:
        with self._state_lock:
            return self._progress.state == "FAILED"

    def get_status(self) -> dict:
        """Return a serializable snapshot for the /status API endpoint."""
        with self._state_lock:
            return {
                "ffmpeg": self._progress.state.lower(),
                "ffmpeg_progress": round(self._progress.progress * 100, 1),
                "ffmpeg_message": self._progress.message,
                "ffmpeg_retry_count": self._progress.retry_count,
                "ffmpeg_error": self._progress.error,
            }

    def wait_until_ready(self, timeout: Optional[float] = None) -> bool:
        """Block until FFmpeg is READY. Returns True if ready, False on timeout."""
        return self._ready_event.wait(timeout=timeout)

    def start_acquisition(self, progress_callback: Optional[Callable[[FFmpegProgress], None]] = None) -> None:
        """
        Start the FFmpeg acquisition process in a background thread.
        Updates _progress and sets _ready_event when done.
        """
        if self._ready_event.is_set():
            return

        thread = threading.Thread(
            target=self._acquisition_worker,
            args=(progress_callback,),
            daemon=True,
            name="ffmpeg-acquisition",
        )
        thread.start()

    # ------------------------------------------------------------------------
    # Core Acquisition Logic
    # ------------------------------------------------------------------------

    def _acquisition_worker(self, progress_callback: Optional[Callable[[FFmpegProgress], None]] = None) -> None:
        """Background worker: download, extract, validate, retry."""
        # Check if already installed
        if self._check_existing_ffmpeg():
            self._set_state("READY", 1.0, "FFmpeg ready", ffmpeg_path=str(self._bin_dir / self._ffmpeg_name()))
            self._ready_event.set()
            if progress_callback:
                progress_callback(self._progress)
            return

        max_retries = 2
        retry_count = 0
        last_error = None

        while retry_count <= max_retries:
            self._set_state(
                "DOWNLOADING",
                0.0,
                f"Downloading FFmpeg... (attempt {retry_count + 1}/{max_retries + 1})",
                retry_count=retry_count,
                error=None,
            )
            if progress_callback:
                progress_callback(self._progress)

            # Try primary mirror (ffbinaries.com)
            success, error = self._download_and_extract_ffbinaries(progress_callback)
            if success:
                # Validate the installed binary
                if self._validate_ffmpeg():
                    self._set_state("READY", 1.0, "FFmpeg ready", ffmpeg_path=str(self._bin_dir / self._ffmpeg_name()))
                    self._ready_event.set()
                    if progress_callback:
                        progress_callback(self._progress)
                    return

                # Validation failed — retry
                last_error = "FFmpeg validation failed after extraction"
                self._cleanup_bin_dir()
                retry_count += 1
                continue

            # Primary mirror failed — try fallback (GitHub releases)
            last_error = error
            self._set_state(
                "DOWNLOADING",
                0.5,
                f"Primary mirror failed, trying fallback... (attempt {retry_count + 1}/{max_retries + 1})",
                retry_count=retry_count,
                error=error,
            )
            if progress_callback:
                progress_callback(self._progress)

            success, error = self._download_and_extract_github_fallback(progress_callback)
            if success:
                if self._validate_ffmpeg():
                    self._set_state("READY", 1.0, "FFmpeg ready", ffmpeg_path=str(self._bin_dir / self._ffmpeg_name()))
                    self._ready_event.set()
                    if progress_callback:
                        progress_callback(self._progress)
                    return
                last_error = "FFmpeg validation failed after fallback extraction"
                self._cleanup_bin_dir()
                retry_count += 1
                continue

            last_error = error
            retry_count += 1

        # All attempts exhausted
        self._set_state(
            "FAILED",
            1.0,
            "FFmpeg acquisition failed. Please download manually.",
            retry_count=retry_count,
            error=last_error or "Unknown error",
        )
        if progress_callback:
            progress_callback(self._progress)

    # ------------------------------------------------------------------------
    # Download & Extraction Methods
    # ------------------------------------------------------------------------

    def _download_and_extract_ffbinaries(self, progress_callback: Optional[Callable[[FFmpegProgress], None]]) -> tuple[bool, Optional[str]]:
        """Download FFmpeg from ffbinaries.com. Returns (success, error)."""
        system = platform.system().lower()
        arch = "64" if sys.maxsize > 2**32 else "32"
        os_map = {
            "windows": f"win-{arch}",
            "darwin": "osx-64",
            "linux": f"linux-{arch}",
        }
        os_key = os_map.get(system)
        if not os_key:
            return False, f"Unsupported OS: {system}"

        base_url = f"https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v4.4.1"
        files = [
            ("ffmpeg", f"ffmpeg-4.4.1-{os_key}.zip"),
            ("ffprobe", f"ffprobe-4.4.1-{os_key}.zip"),
        ]

        self._bin_dir.mkdir(parents=True, exist_ok=True)
        total = len(files)
        completed = 0

        for name, filename in files:
            url = f"{base_url}/{filename}"
            zip_path = self._bin_dir / f"{name}.zip"

            try:
                self._set_state(
                    "DOWNLOADING",
                    completed / total,
                    f"Downloading {name}... ({completed + 1}/{total})",
                )
                if progress_callback:
                    progress_callback(self._progress)

                urllib.request.urlretrieve(url, zip_path)
                completed += 1

                self._set_state("EXTRACTING", completed / total, f"Extracting {name}...")
                if progress_callback:
                    progress_callback(self._progress)

                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    zip_ref.extractall(self._bin_dir)

                # Make executable on Unix-like systems
                if system != "windows":
                    exe_path = self._bin_dir / name
                    if exe_path.exists():
                        exe_path.chmod(0o755)

                zip_path.unlink()

            except Exception as e:
                # Clean up partial downloads
                if zip_path.exists():
                    zip_path.unlink()
                return False, f"Failed to download/extract {name}: {e}"

        return True, None

    def _download_and_extract_github_fallback(self, progress_callback: Optional[Callable[[FFmpegProgress], None]]) -> tuple[bool, Optional[str]]:
        """Fallback: download prebuilt FFmpeg from yt-dlp/FFmpeg-Builds releases."""
        system = platform.system().lower()
        arch = platform.machine().lower()

        # Map to GitHub release naming
        if system == "windows":
            release_name = "ffmpeg-master-latest-win64-gpl.zip"
        elif system == "darwin":
            if "arm" in arch or "aarch" in arch:
                release_name = "ffmpeg-master-latest-macos-arm64-gpl.zip"
            else:
                release_name = "ffmpeg-master-latest-macos-x86_64-gpl.zip"
        elif system == "linux":
            if "aarch" in arch or "arm64" in arch:
                release_name = "ffmpeg-master-latest-linux-arm64-gpl.zip"
            else:
                release_name = "ffmpeg-master-latest-linux-x86_64-gpl.zip"
        else:
            return False, f"Unsupported OS for fallback: {system}"

        url = f"https://github.com/yt-dlp/FFmpeg-Builds/releases/latest/download/{release_name}"
        zip_path = self._bin_dir / "ffmpeg_fallback.zip"

        self._set_state("DOWNLOADING", 0.6, "Downloading fallback FFmpeg...")
        if progress_callback:
            progress_callback(self._progress)

        try:
            urllib.request.urlretrieve(url, zip_path)
        except Exception as e:
            return False, f"Fallback download failed: {e}"

        self._set_state("EXTRACTING", 0.8, "Extracting fallback FFmpeg...")
        if progress_callback:
            progress_callback(self._progress)

        try:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                # The GitHub release has a nested directory structure (ffmpeg-master-.../)
                # We need to extract the actual binaries from inside
                for member in zip_ref.namelist():
                    if member.endswith("/"):
                        continue
                    if "/bin/" in member and (member.endswith("ffmpeg") or member.endswith("ffmpeg.exe") or member.endswith("ffprobe") or member.endswith("ffprobe.exe")):
                        # Extract to bin_dir directly, preserving only the filename
                        target_name = Path(member).name
                        target_path = self._bin_dir / target_name
                        with zip_ref.open(member) as src, open(target_path, "wb") as dst:
                            dst.write(src.read())
                        if system != "windows":
                            target_path.chmod(0o755)

            zip_path.unlink()

        except Exception as e:
            zip_path.unlink()
            return False, f"Fallback extraction failed: {e}"

        # Rename files to standard names if needed
        # The fallback might produce names like "ffmpeg-master-..." — rename to "ffmpeg"
        for f in self._bin_dir.iterdir():
            if f.is_file() and "ffmpeg" in f.name.lower() and f.name != self._ffmpeg_name():
                target = self._bin_dir / self._ffmpeg_name()
                if target.exists():
                    target.unlink()
                f.rename(target)

        # Also handle ffprobe
        for f in self._bin_dir.iterdir():
            if f.is_file() and "ffprobe" in f.name.lower() and f.name != self._ffprobe_name():
                target = self._bin_dir / self._ffprobe_name()
                if target.exists():
                    target.unlink()
                f.rename(target)

        return True, None

    # ------------------------------------------------------------------------
    # Validation & Helpers
    # ------------------------------------------------------------------------

    def _ffmpeg_name(self) -> str:
        return "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"

    def _ffprobe_name(self) -> str:
        return "ffprobe.exe" if sys.platform == "win32" else "ffprobe"

    def _check_existing_ffmpeg(self) -> bool:
        """Check if FFmpeg is already installed and valid."""
        ffmpeg_path = self._bin_dir / self._ffmpeg_name()
        if not ffmpeg_path.exists():
            return False
        return self._validate_ffmpeg()

    def _validate_ffmpeg(self) -> bool:
        """Run `ffmpeg -version` to validate integrity. Returns True if valid."""
        ffmpeg_path = self._bin_dir / self._ffmpeg_name()
        if not ffmpeg_path.exists():
            return False

        try:
            result = subprocess.run(
                [str(ffmpeg_path), "-version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0 and "ffmpeg version" in result.stdout.lower()
        except Exception:
            return False

    def _cleanup_bin_dir(self) -> None:
        """Remove all files in the bin directory to prepare for a fresh attempt."""
        for f in self._bin_dir.iterdir():
            if f.is_file():
                try:
                    f.unlink()
                except Exception:
                    pass

    def _set_state(
        self,
        state: FFmpegState,
        progress: float,
        message: str,
        retry_count: int = 0,
        error: Optional[str] = None,
        ffmpeg_path: Optional[str] = None,
    ) -> None:
        with self._state_lock:
            self._progress.state = state
            self._progress.progress = progress
            self._progress.message = message
            self._progress.retry_count = retry_count
            self._progress.error = error
            self._progress.ffmpeg_path = ffmpeg_path


# Singleton instance
_ffmpeg_manager = FFmpegManager()


def get_ffmpeg_manager() -> FFmpegManager:
    """Get the global FFmpegManager singleton."""
    return _ffmpeg_manager
