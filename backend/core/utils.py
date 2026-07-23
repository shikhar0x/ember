import re

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


def ensure_ffmpeg() -> tuple[str, str]:
    import os
    import sys
    import platform
    import urllib.request
    import zipfile
    import shutil
    
    bin_dir = os.path.abspath(os.path.join(os.path.expanduser("~"), ".ember", "bin"))
    
    ext = ".exe" if os.name == "nt" else ""
    ffmpeg_exe = os.path.join(bin_dir, f"ffmpeg{ext}")
    ffprobe_exe = os.path.join(bin_dir, f"ffprobe{ext}")
    
    if os.path.exists(ffmpeg_exe) and os.path.exists(ffprobe_exe):
        return ffmpeg_exe, bin_dir
        
    print(f"[Ember] FFmpeg/FFprobe missing. Creating directory: {bin_dir}")
    os.makedirs(bin_dir, exist_ok=True)
    
    system = platform.system().lower()
    
    urls = {}
    if system == "windows":
        urls["ffmpeg"] = "https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v4.4.1/ffmpeg-4.4.1-win-64.zip"
        urls["ffprobe"] = "https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v4.4.1/ffprobe-4.4.1-win-64.zip"
    elif system == "darwin":
        urls["ffmpeg"] = "https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v4.4.1/ffmpeg-4.4.1-osx-64.zip"
        urls["ffprobe"] = "https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v4.4.1/ffprobe-4.4.1-osx-64.zip"
    elif system == "linux":
        urls["ffmpeg"] = "https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v4.4.1/ffmpeg-4.4.1-linux-64.zip"
        urls["ffprobe"] = "https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v4.4.1/ffprobe-4.4.1-linux-64.zip"
    else:
        print(f"[Ember] Unsupported OS for automated FFmpeg download: {system}")
        return ffmpeg_exe, bin_dir

    for name, url in urls.items():
        zip_path = os.path.join(bin_dir, f"{name}.zip")
        print(f"[Ember] Downloading {name} from {url}...")
        try:
            urllib.request.urlretrieve(url, zip_path)
            print(f"[Ember] Extracting {name}...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(bin_dir)
            os.remove(zip_path)
            
            if system != "windows":
                exec_path = os.path.join(bin_dir, name)
                if os.path.exists(exec_path):
                    os.chmod(exec_path, 0o755)
        except Exception as e:
            print(f"[Ember] Error setting up {name}: {e}")
            
    return ffmpeg_exe, bin_dir


def get_ffmpeg_details() -> tuple[str, str]:
    """Resolve FFmpeg details, automatically downloading at runtime if missing.
    Never falls back to system PATH or other system-installed instances.
    
    Returns:
        tuple: (ffmpeg_executable_path, ffmpeg_directory_path)
    """
    return ensure_ffmpeg()


def open_folder(path: "Path" | str) -> None:
    """Open a folder in the system file manager (non-blocking)."""
    import sys
    import subprocess
    from pathlib import Path
    path = Path(path)
    try:
        if sys.platform == "win32":
            subprocess.Popen(
                ["explorer", str(path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        elif sys.platform == "darwin":
            subprocess.Popen(
                ["open", str(path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                ["xdg-open", str(path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass
