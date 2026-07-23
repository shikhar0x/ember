"""
core/browser_finder.py
=======================
Cross-platform discovery of Chromium-family browsers and a compatible
ChromeDriver binary.

Priority order for browsers:
    Brave → Chrome → Chromium → Edge
    (Brave first because your CDP token interception was developed against it
     and it tends to have fewer anti-automation flags than plain Chrome)

ChromeDriver resolution order:
    1. webdriver-manager auto-download (matches browser major version exactly)
    2. System PATH  (`chromedriver` / `chromedriver.exe`)
    3. Common install locations per platform

Usage:
    from core.browser_finder import find_browser, find_chromedriver, BrowserNotFoundError

    binary  = find_browser()          # raises BrowserNotFoundError if nothing found
    driver  = find_chromedriver(binary)  # raises ChromeDriverNotFoundError
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class BrowserNotFoundError(RuntimeError):
    """Raised when no supported Chromium-family browser is found."""

class ChromeDriverNotFoundError(RuntimeError):
    """Raised when no compatible ChromeDriver can be located or downloaded."""


@dataclass
class BrowserInfo:
    name: str                                        
    binary: str                                         
    major_version: int           


def _brave_candidates() -> list[Path]:
    h = Path.home()
    if sys.platform == "win32":
        lad = Path(os.environ.get("LOCALAPPDATA", h / "AppData" / "Local"))
        pad = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        pad86 = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
        return [
            lad  / "BraveSoftware/Brave-Browser/Application/brave.exe",
            pad  / "BraveSoftware/Brave-Browser/Application/brave.exe",
            pad86/ "BraveSoftware/Brave-Browser/Application/brave.exe",
        ]
    if sys.platform == "darwin":
        return [
            Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
            h / "Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        ]
           
    return [
        Path("/usr/bin/brave-browser"),
        Path("/usr/bin/brave"),
        Path("/snap/bin/brave"),
        h / "snap/brave/current/.local/share/applications",                 
        Path("/var/lib/flatpak/exports/bin/com.brave.Browser"),
        h / ".local/share/flatpak/exports/bin/com.brave.Browser",
    ]


def _chrome_candidates() -> list[Path]:
    h = Path.home()
    if sys.platform == "win32":
        lad = Path(os.environ.get("LOCALAPPDATA", h / "AppData" / "Local"))
        pad = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        pad86 = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
        return [
            lad  / "Google/Chrome/Application/chrome.exe",
            pad  / "Google/Chrome/Application/chrome.exe",
            pad86/ "Google/Chrome/Application/chrome.exe",
        ]
    if sys.platform == "darwin":
        return [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            h / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]
    return [
        Path("/usr/bin/google-chrome"),
        Path("/usr/bin/google-chrome-stable"),
        Path("/snap/bin/google-chrome"),
    ]


def _chromium_candidates() -> list[Path]:
    h = Path.home()
    if sys.platform == "win32":
        lad = Path(os.environ.get("LOCALAPPDATA", h / "AppData" / "Local"))
        return [lad / "Chromium/Application/chrome.exe"]
    if sys.platform == "darwin":
        return [
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
            h / "Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    return [
        Path("/usr/bin/chromium"),
        Path("/usr/bin/chromium-browser"),
        Path("/snap/bin/chromium"),
    ]


def _edge_candidates() -> list[Path]:
    h = Path.home()
    if sys.platform == "win32":
        pad = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        pad86 = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
        return [
            pad  / "Microsoft/Edge/Application/msedge.exe",
            pad86/ "Microsoft/Edge/Application/msedge.exe",
        ]
    if sys.platform == "darwin":
        return [
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        ]
    return [
        Path("/usr/bin/microsoft-edge"),
        Path("/usr/bin/microsoft-edge-stable"),
    ]


_WHICH_NAMES: dict[str, list[str]] = {
    "brave":    ["brave-browser", "brave"],
    "chrome":   ["google-chrome", "google-chrome-stable", "chrome"],
    "chromium": ["chromium", "chromium-browser"],
    "edge":     ["microsoft-edge", "microsoft-edge-stable", "msedge"],
}

_CANDIDATE_FACTORIES = [
    ("Brave",    _brave_candidates),
    ("Chrome",   _chrome_candidates),
    ("Chromium", _chromium_candidates),
    ("Edge",     _edge_candidates),
]


def _get_major_version(binary: str) -> int:
    """Return the major version of a Chromium-family browser, or 0 on failure."""
    if sys.platform == "win32":
        try:
            import win32api
            info = win32api.GetFileVersionInfo(binary, "\\")
            ms = info['FileVersionMS']
            return int(ms / 65536)
        except Exception:
            try:
                result = subprocess.run(
                    ["wmic", "datafile", "where", f'name="{binary.replace("\\", "\\\\")}"', "get", "Version", "/value"],
                    capture_output=True, text=True, timeout=5
                )
                match = re.search(r"Version=(\d+)\.", result.stdout)
                if match:
                    return int(match.group(1))
            except Exception:
                pass
        return 0

    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True, text=True, timeout=5
        )
        text = result.stdout.strip() or result.stderr.strip()
        match = re.search(r"(\d+)\.\d+", text)
        if match:
            return int(match.group(1))
    except Exception:
        pass

    return 0


def find_browser() -> BrowserInfo:
    """
    Return the first available Chromium-family browser found on this system.
    Priority: Brave > Chrome > Chromium > Edge.
    Raises BrowserNotFoundError if nothing is found.
    """
    for name, candidates_fn in _CANDIDATE_FACTORIES:
                                             
        for path in candidates_fn():
            if path.is_file():
                ver = _get_major_version(str(path))
                print(f"[BrowserFinder] Found {name} at {path} (v{ver})")
                return BrowserInfo(name=name, binary=str(path), major_version=ver)

                       
        key = name.lower()
        for which_name in _WHICH_NAMES.get(key, []):
            found = shutil.which(which_name)
            if found:
                ver = _get_major_version(found)
                print(f"[BrowserFinder] Found {name} in PATH at {found} (v{ver})")
                return BrowserInfo(name=name, binary=found, major_version=ver)

    raise BrowserNotFoundError(
        "No supported browser found (Brave, Chrome, Chromium, or Edge).\n"
        "Please install one of these browsers and try again."
    )


def find_chromedriver(browser: Optional[BrowserInfo] = None) -> str:
    """
    Return a path to a ChromeDriver binary compatible with *browser*.

    Resolution order:
        1. webdriver-manager auto-download (version-matched)
        2. System PATH chromedriver
        3. Common fixed install locations

    Raises ChromeDriverNotFoundError if nothing works.
    """
    major = browser.major_version if browser else 0

    try:
        _path = _try_webdriver_manager(major, browser)
        if _path:
            return _path
    except Exception as e:
        print(f"[BrowserFinder] webdriver-manager failed: {e}")

    found = shutil.which("chromedriver") or shutil.which("chromedriver.exe")
    if found:
        print(f"[BrowserFinder] Found chromedriver in PATH: {found}")
        return found

    for path in _fixed_chromedriver_locations():
        if path.is_file():
            print(f"[BrowserFinder] Found chromedriver at: {path}")
            return str(path)

    raise ChromeDriverNotFoundError(
        "ChromeDriver not found and could not be auto-downloaded.\n"
        "Install webdriver-manager:  pip install webdriver-manager\n"
        "Or download manually from:  https://chromedriver.chromium.org/downloads"
    )


def _try_webdriver_manager(major_version: int, browser: Optional[BrowserInfo]) -> Optional[str]:
    """Try to get a chromedriver via webdriver-manager. Returns path or None."""
    try:
        import os
        os.environ["WDM_LOG"] = "0"
        import logging
        logging.getLogger("WDM").setLevel(logging.CRITICAL)
        
        from webdriver_manager.chrome import ChromeDriverManager
        from webdriver_manager.core.os_manager import ChromeType
    except ImportError:
        print("[BrowserFinder] webdriver-manager not installed; skipping auto-download")
        return None

                                                                                  
    chrome_type = ChromeType.GOOGLE                                     
    if browser and browser.name == "Edge":
        try:
            from webdriver_manager.microsoft import EdgeChromiumDriverManager
            path = EdgeChromiumDriverManager().install()
            print(f"[BrowserFinder] webdriver-manager installed Edge driver: {path}")
            return path
        except Exception as e:
            print(f"[BrowserFinder] Edge driver install failed: {e}")
            return None

    driver_kwargs = {"chrome_type": chrome_type}
    if major_version > 0:
        driver_kwargs["driver_version"] = str(major_version)
        
    path = ChromeDriverManager(**driver_kwargs).install()
    print(f"[BrowserFinder] webdriver-manager installed ChromeDriver: {path}")
    return path


def _fixed_chromedriver_locations() -> list[Path]:
    if sys.platform == "win32":
        lad = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return [
            lad / "Google/Chrome/Application/chromedriver.exe",
            Path(r"C:\chromedriver\chromedriver.exe"),
        ]
    if sys.platform == "darwin":
        return [
            Path("/usr/local/bin/chromedriver"),
            Path("/opt/homebrew/bin/chromedriver"),
        ]
    return [
        Path("/usr/local/bin/chromedriver"),
        Path("/usr/bin/chromedriver"),
        Path("/snap/bin/chromedriver"),
    ]