import re
from pathlib import Path

def sanitize_filename(name: str) -> str:
    """
    Make a string safe for Linux/macOS/Windows filenames.
    """
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def normalize_title(text: str) -> str:
    """
    Strip noise from a title before scoring.
    Removes bracketed content, feat tags, and common YouTube noise words.
    """
    text = text.lower()

                                         
    text = re.sub(r"[\(\[](?:feat|ft)\.?[^\)\]]*[\)\]]", "", text, flags=re.IGNORECASE)

                                           
    text = re.sub(r"[\(\[](official\s*(video|audio|music\s*video|lyric\s*video)?|"
                  r"lyrics?|audio|hd|hq|remaster(ed)?|live|explicit|clean|"
                  r"deluxe|bonus\s*track|album\s*version|visuali[sz]er)[\)\]]",
                  "", text, flags=re.IGNORECASE)

                                 
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def normalize_artist(artists: list) -> str:
    """
    Return only the primary artist, cleaned of featured acts.
    """
    if not artists:
        return ""
    main = artists[0]
    main = re.split(
        r"\s*(?:feat\.?|ft\.?|&|,|\band\b|\bx\b)\s*",
        main,
        flags=re.IGNORECASE
    )[0]
    return main.strip().lower()


def get_ffmpeg_details(timeout: float = 120.0, download_callback=None) -> tuple[str, str]:
    from core.ffmpeg_manager import get_ffmpeg_manager
    from core.events import emit, progress_event

    mgr = get_ffmpeg_manager()
    if not mgr.is_ready:
        emit(download_callback, progress_event(0.0, "Finishing audio engine setup..."))
        mgr.start_acquisition()  # no-op if already running
        if not mgr.wait_until_ready(timeout=timeout):
            raise RuntimeError(f"FFmpeg not ready after {timeout}s: {mgr.message or mgr.error}")

    ffmpeg_path = mgr.ffmpeg_path
    if not ffmpeg_path:
        raise RuntimeError("FFmpegManager reports ready but ffmpeg_path is unset")
    return ffmpeg_path, str(Path(ffmpeg_path).parent)


def open_folder(path: "Path" | str) -> None:
    """Open a folder in the system file manager (non-blocking)."""
    import sys
    import os
    import subprocess
    from pathlib import Path
    path = Path(path)
    
    # Extract clean environment to prevent PyInstaller's LD_LIBRARY_PATH rewriting
    # from breaking system utilities (like xdg-open/open).
    env = dict(os.environ)
    for var in ["LD_LIBRARY_PATH", "LIBPATH"]:
        orig = f"{var}_ORIG"
        if orig in env:
            env[var] = env[orig]
        else:
            env.pop(var, None)

    try:
        if sys.platform == "win32":
            already_open = False
            try:
                import win32com.client
                import win32gui
                import win32con
                
                shell = win32com.client.Dispatch("Shell.Application")
                target_norm = os.path.normpath(str(path)).lower()
                for window in shell.Windows():
                    try:
                        win_path = window.Document.Folder.Self.Path
                        if os.path.normpath(win_path).lower() == target_norm:
                            already_open = True
                            hwnd = window.HWND
                            if hwnd:
                                if win32gui.IsIconic(hwnd):
                                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                                else:
                                    win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
                                win32gui.SetForegroundWindow(hwnd)
                            break
                    except Exception:
                        continue
            except Exception:
                pass

            if not already_open:
                subprocess.Popen(
                    ["explorer", str(path)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    env=env,
                )
        elif sys.platform == "darwin":
            subprocess.Popen(
                ["open", str(path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env=env,
            )
        else:
            subprocess.Popen(
                ["xdg-open", str(path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env=env,
            )
    except Exception:
        pass
