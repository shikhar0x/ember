from __future__ import annotations

import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
import requests
import logging

from core.browser_finder import (
    BrowserInfo,
    BrowserNotFoundError,
    ChromeDriverNotFoundError,
    find_browser,
    find_chromedriver,
)

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

logging.getLogger("websocket").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)

class TokenManager:
    import os
    _config_dir = Path.home() / ".ember"
    _config_dir.mkdir(parents=True, exist_ok=True)
    CACHE_FILE = str(_config_dir / "tokens.json")

    def __init__(self, session=None):
        if session:
            self._session = session
        else:
            self._session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100)
            self._session.mount("https://", adapter)
            self._session.mount("http://", adapter)

        self._bearer = None
        self._expires_at = 0
        self._client_token: str = ""
        self._client_token_expires_at: float = 0.0
        self._lock = threading.Lock()
        self._next_cmd_id = 100
        self._user_profile: dict | None = None
        self._warmup_message: str = "Connecting to Spotify..."
        self._needs_login: bool = False
        self._warmup_done: bool = False
        self._profile_loading: bool = False
        self._browser_info: BrowserInfo | None = None
        self._driver_path: str | None = None

        try:
            with open(self.CACHE_FILE, "r") as f:
                data = json.load(f)
                self._bearer = data.get("bearer")
                self._expires_at = data.get("expires_at", 0)
                self._client_token = data.get("client_token", "")
                self._client_token_expires_at = data.get("client_token_expires_at", 0.0)
                self._user_profile = data.get("user_profile")
                if self._bearer and time.time() < self._expires_at and self._user_profile:
                    name = (self._user_profile or {}).get("display_name", "user")
                    print(f"[TokenManager] Loaded cached token for {name}")
                    self._warmup_done = True
                else:
                    self._bearer = None
                    self._user_profile = None
        except Exception:
            pass

    def _get_browser_and_driver(self) -> tuple[BrowserInfo, str]:
        if self._browser_info is None or self._driver_path is None:
            try:
                self._browser_info = find_browser()
            except BrowserNotFoundError as e:
                raise RuntimeError(str(e)) from e
            try:
                self._driver_path = find_chromedriver(self._browser_info)
            except ChromeDriverNotFoundError as e:
                raise RuntimeError(str(e)) from e
        return self._browser_info, self._driver_path

    def fetch_client_token(self) -> str:
        """Fetch a short-lived client-token from Spotify's client-token endpoint."""
        try:
            r = self._session.post(
                "https://clienttoken.spotify.com/v1/client-token",
                json={
                    "client_data": {
                        "client_version": "1.2.92.73.g916d0757",
                        "client_id": "d8a5ed958d274c2e8ee717e6a4b0971d",
                        "js_sdk_data": {
                            "device_brand": "unknown",
                            "device_model": "unknown",
                            "os": "linux" if sys.platform.startswith("linux") else ("macos" if sys.platform == "darwin" else "windows"),
                            "os_version": "unknown" if sys.platform != "win32" else "NT 10.0",
                            "device_id": "",
                            "device_type": "computer",
                        },
                    }
                },
                headers={
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                granted = data.get("granted_token", {})
                token = granted.get("token") or data.get("client_token", "")
                ttl = granted.get("expires_after_seconds", 3600)
                if token:
                    self._client_token = token
                    self._client_token_expires_at = time.time() + ttl - 60
                    print("[TokenManager] client-token fetched.")
                    return token
        except Exception as e:
            print(f"[TokenManager] client-token fetch failed: {e}")
        return ""

    @staticmethod
    def clear_stale_browser_locks(user_data_dir: str, browser_name: str) -> None:
        """Remove stale Chromium profile lock files left by crashed browser sessions."""
        import os
        if sys.platform == "win32":
            lockfile = os.path.join(user_data_dir, "lockfile")
            if not os.path.exists(lockfile):
                return
            import subprocess
            process_names = {
                "brave": "brave.exe",
                "chrome": "chrome.exe",
                "edge": "msedge.exe",
            }
            exe_name = None
            for key, val in process_names.items():
                if key in browser_name:
                    exe_name = val
                    break
            if not exe_name:
                return
            try:
                result = subprocess.run(
                    ["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/NH"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if exe_name.lower() not in result.stdout.lower():
                    os.remove(lockfile)
                    print(f"[TokenManager] Removed stale lock file: {lockfile}")
            except Exception as e:
                print(f"[TokenManager] Could not check for stale locks: {e}")
        else:
            import os
            lock_files = ["SingletonLock", "SingletonSocket", "SingletonCookie"]
            singleton_lock = os.path.join(user_data_dir, "SingletonLock")
            if not os.path.islink(singleton_lock) and not os.path.exists(singleton_lock):
                return
            stale = False
            try:
                link_target = os.readlink(singleton_lock)
                pid_str = link_target.rsplit("-", 1)[-1]
                pid = int(pid_str)
                try:
                    os.kill(pid, 0)
                except OSError:
                    stale = True
            except (ValueError, OSError):
                stale = True
            if stale:
                for lock_name in lock_files:
                    lock_path = os.path.join(user_data_dir, lock_name)
                    try:
                        if os.path.islink(lock_path) or os.path.exists(lock_path):
                            os.remove(lock_path)
                            print(f"[TokenManager] Removed stale lock: {lock_name}")
                    except OSError as e:
                        print(f"[TokenManager] Could not remove {lock_name}: {e}")

    def fetch_token(self) -> None:
        import os
        import sys
        import time
        import json
        import subprocess
        import urllib.request
        import urllib.error
        import shutil
        import tempfile
        import websocket

        browser_info = find_browser()
        print(f"[TokenManager] Harvesting token via {browser_info.name} (v{browser_info.major_version}) ...")

        bname = browser_info.name.lower()

        if sys.platform == "win32":
            print("[TokenManager] Windows detected — using real profile for headful login if needed")

        def get_browser_cookie_paths(browser_name: str) -> list[str]:
            home = os.path.expanduser("~")
            name_lower = browser_name.lower()
            paths = []
            if sys.platform == "win32":
                local = os.path.expandvars(r"%LOCALAPPDATA%")
                if "brave" in name_lower:
                    paths = [
                        os.path.join(local, r"BraveSoftware\Brave-Browser\User Data\Default\Network\Cookies"),
                        os.path.join(local, r"BraveSoftware\Brave-Browser\User Data\Default\Cookies"),
                    ]
                elif "chrome" in name_lower:
                    paths = [
                        os.path.join(local, r"Google\Chrome\User Data\Default\Network\Cookies"),
                        os.path.join(local, r"Google\Chrome\User Data\Default\Cookies"),
                    ]
                elif "edge" in name_lower:
                    paths = [
                        os.path.join(local, r"Microsoft\Edge\User Data\Default\Network\Cookies"),
                        os.path.join(local, r"Microsoft\Edge\User Data\Default\Cookies"),
                    ]
            elif sys.platform == "darwin":
                if "brave" in name_lower:
                    paths = [os.path.expanduser("~/Library/Application Support/BraveSoftware/Brave-Browser/Default/Cookies")]
                elif "chrome" in name_lower:
                    paths = [os.path.expanduser("~/Library/Application Support/Google/Chrome/Default/Cookies")]
            else:
                if "brave" in name_lower:
                    paths = [
                        os.path.expanduser("~/.config/BraveSoftware/Brave-Browser/Default/Network/Cookies"),
                        os.path.expanduser("~/.config/BraveSoftware/Brave-Browser/Default/Cookies"),
                        os.path.expanduser("~/snap/brave/current/.config/BraveSoftware/Brave-Browser/Default/Network/Cookies"),
                        os.path.expanduser("~/snap/brave/current/.config/BraveSoftware/Brave-Browser/Default/Cookies"),
                        os.path.expanduser("~/.var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser/Default/Network/Cookies"),
                        os.path.expanduser("~/.var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser/Default/Cookies"),
                    ]
                elif "chrome" in name_lower:
                    paths = [
                        os.path.expanduser("~/.config/google-chrome/Default/Network/Cookies"),
                        os.path.expanduser("~/.config/google-chrome/Default/Cookies"),
                    ]
            return [p for p in paths if os.path.exists(p)]

        temp_profile_dir = tempfile.mkdtemp(prefix="ember_browser_profile_")
        dest_network_dir = os.path.join(temp_profile_dir, "Default", "Network")
        dest_default_dir = os.path.join(temp_profile_dir, "Default")
        os.makedirs(dest_network_dir, exist_ok=True)

        src_cookies = None
        for p in get_browser_cookie_paths(bname):
            if os.path.exists(p):
                src_cookies = p
                break
        if src_cookies:
            try:
                shutil.copy2(src_cookies, os.path.join(dest_network_dir, "Cookies"))
                shutil.copy2(src_cookies, os.path.join(dest_default_dir, "Cookies"))
            except Exception as e:
                print(f"[TokenManager] Warning: Could not copy session cookies: {e}")

            try:
                from pathlib import Path as _Path
                p_parts = _Path(src_cookies).parts
                if "Default" in p_parts:
                    idx = p_parts.index("Default")
                    src_user_data_dir = str(_Path(*p_parts[:idx]))
                    src_local_state = os.path.join(src_user_data_dir, "Local State")
                    if os.path.exists(src_local_state):
                        shutil.copy2(src_local_state, os.path.join(temp_profile_dir, "Local State"))
                    src_prefs = os.path.join(src_user_data_dir, "Default", "Preferences")
                    if os.path.exists(src_prefs):
                        shutil.copy2(src_prefs, os.path.join(dest_default_dir, "Preferences"))
            except Exception:
                pass

        PORT_HEADLESS = 9222
        PORT_HEADFUL = 9223

        def get_page_ws_url(port):
            try:
                req = urllib.request.Request(f"http://localhost:{port}/json")
                with urllib.request.urlopen(req, timeout=2) as response:
                    targets = json.loads(response.read().decode())
                    for target in targets:
                        if target.get("type") == "page":
                            ws_url = target.get("webSocketDebuggerUrl")
                            if ws_url:
                                return ws_url
            except Exception:
                pass
            return None

        def close_existing_browser(port):
            ws_url = get_page_ws_url(port)
            if ws_url:
                try:
                    ws_temp = websocket.create_connection(ws_url, timeout=2.0)
                    ws_temp.send(json.dumps({"id": 999, "method": "Browser.close"}))
                    ws_temp.close()
                    time.sleep(1.0)
                except Exception:
                    pass

        def launch_browser(headless: bool, port: int, url: str = "about:blank", use_real_profile: bool = False) -> subprocess.Popen:
            close_existing_browser(port)
            
            profile_dir = temp_profile_dir
            if use_real_profile and sys.platform == "win32":
                if "brave" in bname:
                    profile_dir = os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data")
                elif "chrome" in bname:
                    profile_dir = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
                elif "edge" in bname:
                    profile_dir = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data")

            cmd = [
                browser_info.binary,
                f"--remote-debugging-port={port}",
                "--remote-allow-origins=*",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-search-engine-choice-screen",
                f"--user-data-dir={profile_dir}",
                "--profile-directory=Default",
            ]
            if headless:
                cmd.append("--headless=new")
            if sys.platform.startswith("linux"):
                cmd.extend(["--ozone-platform=x11", "--disable-gpu"])
            cmd.append(url)

            kwargs = {}
            if sys.platform != "win32":
                kwargs["preexec_fn"] = os.setsid

            return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)

        def terminate_process_group(proc):
            if not proc:
                return
            try:
                if sys.platform != "win32":
                    import signal
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    proc.wait(timeout=3)
                else:
                    proc.terminate()
            except Exception:
                try:
                    proc.terminate()
                except:
                    pass

        def send_cdp_wait(ws, method, params=None, timeout=3.0):
            try:
                ws.settimeout(0.001)
                drain_start = time.time()
                for _ in range(80):
                    if time.time() - drain_start > 0.08:
                        break
                    ws.recv()
            except Exception:
                pass

            cmd_id = self._next_cmd_id
            self._next_cmd_id += 1
            try:
                ws.send(json.dumps({
                    "id": cmd_id,
                    "method": method,
                    "params": params or {}
                }))
                start_time = time.time()
                while time.time() - start_time < timeout:
                    try:
                        ws.settimeout(0.4)
                        raw = ws.recv()
                        res = json.loads(raw)
                        if res.get("id") == cmd_id:
                            return res.get("result", {})
                    except websocket.WebSocketTimeoutException:
                        continue
            except Exception as e:
                print(f"[CDP send error] {e}")
            return {}

        def evaluate_js(ws, expression, timeout=2.5):
            res = send_cdp_wait(ws, "Runtime.evaluate", {
                "expression": expression,
                "returnByValue": True
            }, timeout=timeout)
            obj = res.get("result", {})
            return obj.get("value")

        proc = None
        ws = None
        bearer = None

        try:
            print("[TokenManager] Attempting silent harvest in headless mode...")
            self._warmup_message = "Connecting to Spotify..."
            self._needs_login = False
            proc = launch_browser(headless=True, port=PORT_HEADLESS, url="https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b")
            ws_url = None
            start = time.time()
            while time.time() - start < 7:
                ws_url = get_page_ws_url(PORT_HEADLESS)
                if ws_url:
                    break
                time.sleep(0.4)
            if ws_url:
                ws = websocket.create_connection(ws_url, timeout=4.0)
                ws.send(json.dumps({"id": 1, "method": "Network.enable", "params": {}}))
                ws.send(json.dumps({"id": 2, "method": "Page.enable", "params": {}}))
                ws.send(json.dumps({"id": 3, "method": "Page.reload", "params": {}}))

                listen_start = time.time()
                while time.time() - listen_start < 7 and not bearer:
                    try:
                        ws.settimeout(0.35)
                        msg = json.loads(ws.recv())
                        method = msg.get("method")
                        if method == "Network.webSocketCreated":
                            url = msg.get("params", {}).get("url", "")
                            if "access_token=" in url:
                                token = url.split("access_token=")[1].split("&")[0]
                                if token:
                                    bearer = f"Bearer {token}"
                                    break
                        elif method in ("Network.requestWillBeSentExtraInfo", "Network.requestWillBeSent"):
                            headers = msg.get("params", {}).get("headers", {}) or msg.get("params", {}).get("request", {}).get("headers", {})
                            auth = headers.get("authorization") or headers.get("Authorization")
                            if auth and "Bearer" in auth:
                                bearer = auth
                                break
                    except websocket.WebSocketTimeoutException:
                        continue
        except Exception as e:
            print(f"[TokenManager] Headless harvest error: {e}")

        if not bearer:
            if ws:
                try: ws.close()
                except: pass
                ws = None
            if proc:
                terminate_process_group(proc)
                proc = None

        if not bearer:
            try:
                print("[TokenManager] Silent harvest failed. Launching visible browser for login...")
                self._needs_login = True
                self._warmup_message = "Please log in to Spotify in the browser window..."
                
                proc = launch_browser(
                    headless=False, 
                    port=PORT_HEADFUL, 
                    url="https://accounts.spotify.com/login", 
                    use_real_profile=True
                )
                
                ws_url = None
                start = time.time()
                while time.time() - start < 9:
                    ws_url = get_page_ws_url(PORT_HEADFUL)
                    if ws_url:
                        break
                    time.sleep(0.4)
                if not ws_url:
                    raise RuntimeError("Failed to connect to visible browser debugging port.")

                ws = websocket.create_connection(ws_url, timeout=4.0)
                ws.send(json.dumps({"id": 1, "method": "Network.enable", "params": {}}))
                ws.send(json.dumps({"id": 2, "method": "Page.enable", "params": {}}))

                redirected_to_track = False
                last_url_check = 0.0
                login_start = time.time()
                while time.time() - login_start < 300 and not bearer:
                    try:
                        ws.settimeout(0.05)
                        msg = json.loads(ws.recv())
                        method = msg.get("method")
                        params = msg.get("params", {})

                        if method == "Network.webSocketCreated":
                            url = params.get("url", "")
                            if "access_token=" in url:
                                token = url.split("access_token=")[1].split("&")[0]
                                if token:
                                    bearer = f"Bearer {token}"
                                    break

                        headers = params.get("headers", {})
                        if not headers and "request" in params:
                            headers = params.get("request", {}).get("headers", {})
                        if not headers and "response" in params:
                            headers = params.get("response", {}).get("headers", {})

                        if method == "Network.responseReceivedExtraInfo":
                            headers = params.get("headers", {})

                        auth = headers.get("authorization") or headers.get("Authorization")
                        if auth and "Bearer" in auth:
                            bearer = auth
                            break

                    except websocket.WebSocketTimeoutException:
                        pass
                    except Exception:
                        break

                    now = time.time()
                    if now - last_url_check >= 0.9:
                        last_url_check = now
                        current_url = ""
                        try:
                            req = urllib.request.Request(f"http://localhost:{PORT_HEADFUL}/json")
                            with urllib.request.urlopen(req, timeout=0.6) as response:
                                targets = json.loads(response.read().decode())
                                for target in targets:
                                    if target.get("type") == "page":
                                        current_url = target.get("url", "")
                                        break
                        except Exception:
                            continue

                        if current_url and "open.spotify.com" in current_url and "/track/" not in current_url:
                            if not redirected_to_track:
                                ws.send(json.dumps({
                                    "id": 100,
                                    "method": "Page.navigate",
                                    "params": {"url": "https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b"}
                                }))
                                redirected_to_track = True
                                time.sleep(5.0)
                        elif "/track/" in current_url:
                            redirected_to_track = True
            except Exception as e:
                print(f"[TokenManager] Headful harvest error: {e}")

        if bearer:
            self._warmup_message = "Fetching your profile..."
            profile_fetched = False

            try:
                headers = {
                    "authorization": bearer,
                    "app-platform": "WebPlayer",
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "accept": "application/json",
                }
                if self._client_token:
                    headers["client-token"] = self._client_token

                r = self._session.get(
                    "https://api.spotify.com/v1/me",
                    headers=headers,
                    timeout=8
                )
                if r.status_code == 200:
                    profile_data = r.json()
                    display_name = profile_data.get("display_name") or "User"
                    avatar_url = None
                    images = profile_data.get("images", [])
                    if images:
                        avatar_url = images[0].get("url")
                    self._user_profile = {
                        "display_name": display_name,
                        "avatar_url": avatar_url,
                        "uri": profile_data.get("uri", "")
                    }
                    print(f"[TokenManager] Profile fetched from API: {display_name}")
                    profile_fetched = True
            except Exception as e:
                print(f"[TokenManager] Profile API attempt failed: {e}")

            if not profile_fetched and ws:
                import threading
                
                self._user_profile = {"display_name": "User", "avatar_url": None, "uri": ""}
                self._profile_loading = True
                
                bg_ws = ws
                bg_proc = proc
                bg_dir = temp_profile_dir
                
                ws = None
                proc = None
                temp_profile_dir = ""
                
                def background_scrape():
                    import time
                    import json
                    import shutil
                    profile = None
                    try:
                        bg_ws.send(json.dumps({
                            "id": 200,
                            "method": "Page.navigate",
                            "params": {"url": "https://open.spotify.com/"}
                        }))
                        time.sleep(2.0)

                        for _ in range(20):
                            if evaluate_js(bg_ws, "document.readyState") == "complete":
                                break
                            time.sleep(0.5)

                        for _ in range(20):
                            if evaluate_js(bg_ws, "!!document.querySelector('#main')"):
                                break
                            time.sleep(0.5)

                        widget_found = False
                        for _ in range(20):
                            res = evaluate_js(bg_ws, "!!document.querySelector('[data-testid=\"user-widget-link\"] img, [data-testid=\"user-widget-avatar\"] img, header img, [data-testid=\"user-widget-link\"]')")
                            if res:
                                widget_found = True
                                break
                            time.sleep(0.5)

                        if widget_found:
                            profile = evaluate_js(bg_ws, """
                                (function() {
                                    let img = document.querySelector('[data-testid="user-widget-link"] img, [data-testid="user-widget-avatar"] img, header img');
                                    if (img && img.getAttribute('alt')) {
                                        return {
                                            display_name: img.getAttribute('alt'),
                                            avatar_url: img.getAttribute('src') || null,
                                            uri: ''
                                        };
                                    }
                                    let header = document.querySelector('header');
                                    if (header) {
                                        let imgs = Array.from(header.querySelectorAll('img'));
                                        for (let i of imgs) {
                                            if (i.getAttribute('alt') && i.getAttribute('src')) {
                                                return {
                                                    display_name: i.getAttribute('alt'),
                                                    avatar_url: i.getAttribute('src'),
                                                    uri: ''
                                                };
                                            }
                                        }
                                    }
                                    let widget = document.querySelector('[data-testid="user-widget-link"], [data-testid="user-widget-avatar"]');
                                    if (widget) {
                                        return {
                                            display_name: widget.getAttribute('aria-label') || widget.getAttribute('title') || 'User',
                                            avatar_url: null,
                                            uri: ''
                                        };
                                    }
                                    return null;
                                })()
                            """)
                            if profile:
                                self._user_profile = profile
                                print(f"[TokenManager] Profile scraped in background: {self._user_profile.get('display_name')}")
                                
                                try:
                                    with open(self.CACHE_FILE, "w") as f:
                                        json.dump(
                                            {
                                                "bearer": self._bearer,
                                                "expires_at": self._expires_at,
                                                "client_token": self._client_token,
                                                "client_token_expires_at": self._client_token_expires_at,
                                                "user_profile": self._user_profile,
                                            },
                                            f,
                                            indent=2,
                                        )
                                except Exception:
                                    pass
                    except Exception as e:
                        print(f"[TokenManager] Background UI scrape error: {e}")
                    finally:
                        self._profile_loading = False
                        try: bg_ws.close()
                        except: pass
                        if bg_proc:
                            terminate_process_group(bg_proc)
                        try:
                            shutil.rmtree(bg_dir, ignore_errors=True)
                        except Exception:
                            pass
                
                t = threading.Thread(target=background_scrape, daemon=True)
                t.start()

        if ws:
            try: ws.close()
            except: pass
        if proc:
            terminate_process_group(proc)
        try:
            shutil.rmtree(temp_profile_dir, ignore_errors=True)
        except Exception:
            pass

        if not bearer:
            raise RuntimeError(
                f"[TokenManager] Failed to harvest token from {browser_info.name}. "
                "Make sure you are logged in to Spotify in that browser."
            )

        self._warmup_message = "Almost ready..."
        self._bearer = bearer
        self._expires_at = time.time() + 3300
        self._client_token = ""
        self._client_token_expires_at = 0.0

        self.fetch_client_token()

        with open(self.CACHE_FILE, "w") as f:
            json.dump(
                {
                    "bearer": self._bearer,
                    "expires_at": self._expires_at,
                    "client_token": self._client_token,
                    "client_token_expires_at": self._client_token_expires_at,
                    "user_profile": self._user_profile,
                },
                f,
                indent=2,
            )

        name = (self._user_profile or {}).get("display_name", "user")
        print(f"[TokenManager] Ready. Welcome, {name}!")
        self._warmup_done = True
        self._needs_login = False

    def get_headers(self) -> dict:
        if not self._bearer:
            with self._lock:
                if not self._bearer:
                    self.fetch_token()
        if not self._client_token or time.time() >= self._client_token_expires_at:
            with self._lock:
                if not self._client_token or time.time() >= self._client_token_expires_at:
                    self.fetch_client_token()

        headers = {
            "authorization": self._bearer,
            "app-platform": "WebPlayer",
            "User-Agent": "Mozilla/5.0",
            "content-type": "application/json",
        }
        if self._client_token:
            headers["client-token"] = self._client_token
        return headers

    def probe_token(self) -> bool:
        if not self._bearer:
            return False
        try:
            r = self._session.post(
                "https://api-partner.spotify.com/pathfinder/v1/query",
                headers={
                    "authorization": self._bearer,
                    "app-platform": "WebPlayer",
                    "User-Agent": "Mozilla/5.0",
                    "content-type": "application/json",
                },
                json={
                    "variables": {"uri": "spotify:track:0VjIjW4GlUZAMYd2vXMi3b"},
                    "operationName": "getTrack",
                    "extensions": {
                        "persistedQuery": {
                            "version": 1,
                            "sha256Hash": SHA256,
                        }
                    },
                },
                timeout=10,
            )
            return r.status_code != 401
        except Exception:
            return True

    _probe_token = probe_token

    class _ErrorResponse:
        status_code = 0
        content = b""
        def __init__(self, reason="Request failed"):
            self._reason = reason
        def json(self):
            return {"error": True, "reason": self._reason}

    def request(self, method: str, url: str, **kwargs):
        if "headers" not in kwargs:
            kwargs["headers"] = self.get_headers()
        for attempt in range(2):
            try:
                r = self._session.request(method, url, timeout=10, **kwargs)
                if r.status_code == 401 and attempt == 0:
                    used_bearer = kwargs["headers"].get("authorization")
                    with self._lock:
                        if self._bearer == used_bearer:
                            print("[TokenManager] Token rejected — re-harvesting...")
                            self._bearer = None
                            self._expires_at = 0
                    kwargs["headers"] = self.get_headers()
                    continue
                return r
            except Exception as e:
                if attempt == 0:
                    print(f"[TokenManager] Request failed (attempt {attempt + 1}): {e}")
                    continue
                print(f"[TokenManager] Request failed permanently: {e}")
                return self._ErrorResponse(str(e))
        return self._ErrorResponse("All retries exhausted")

    def raw_request(self, method: str, url: str, headers: dict, **kwargs):
        try:
            r = self._session.request(method, url, headers=headers, timeout=10, **kwargs)
            if r.status_code == 401:
                return self.request(method, url, **kwargs)
            return r
        except Exception as e:
            return self._ErrorResponse(str(e))


SHA256 = "612585ae06ba435ad26369870deaae23b5c8800a256cd8a57e08eddc25a37294"
PLAYLIST_SHA256 = "a65e12194ed5fc443a1cdebed5fabe33ca5b07b987185d63c72483867ad13cb4"
PLAYLIST_LIMIT = 50

def get_track(track_id: str, tm: TokenManager) -> dict:
    payload = {
        "variables": {"uri": f"spotify:track:{track_id}"},
        "operationName": "getTrack",
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": SHA256,
            }
        },
    }
    try:
        r = tm.request(
            "POST",
            "https://api-partner.spotify.com/pathfinder/v1/query",
            json=payload,
        )
        data = r.json()["data"]["trackUnion"]
        album = data["albumOfTrack"]
        return {
            "title": data["name"],
            "artists": (
                [a["profile"]["name"] for a in data["firstArtist"]["items"]]
                + [a["profile"]["name"] for a in data.get("otherArtists", {}).get("items", [])]
            ),
            "album": album["name"],
            "album_id": album["id"],
            "artist_id": next((a.get("uri", "").split(":")[-1] for a in data.get("firstArtist", {}).get("items", []) if a.get("uri")), None),
            "year": album["date"]["year"],
            "duration_s": data["duration"]["totalMilliseconds"] // 1000,
            "track_number": data["trackNumber"],
            "cover_url": next(
                (
                    s["url"]
                    for s in sorted(
                        album.get("coverArt", {}).get("sources", []),
                        key=lambda s: s.get("height", 0),
                        reverse=True,
                    )
                ),
                None,
            ),
            "spotify_url": f"https://open.spotify.com/track/{track_id}",
            "track_id": track_id,
            "isrc": None,
        }
    except Exception as e:
        return {"error": True, "reason": str(e), "track_id": track_id}

def get_isrc(track_id: str, tm: TokenManager) -> str | None:
    BASE62 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    try:
        n = 0
        for char in track_id:
            n = n * 62 + BASE62.index(char)
        gid = hex(n)[2:].zfill(32)
    except ValueError:
        print(f"[ISRC Error] Malformed track_id: {track_id!r}")
        return None

    try:
        r = tm.request(
            "GET",
            f"https://spclient.wg.spotify.com/metadata/4/track/{gid}?market=from_token",
        )
        if r.status_code != 200:
            return None
        matches = re.findall(rb"[A-Z]{2}[A-Z0-9]{3}\d{7}", r.content)
        for m in matches:
            isrc = m.decode()
            if len(isrc) == 12 and isrc[:2].isalpha():
                return isrc
    except Exception:
        pass
    return None

def get_track_with_isrc(track_id: str, tm: TokenManager) -> dict:
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_track = executor.submit(get_track, track_id, tm)
        future_isrc = executor.submit(get_isrc, track_id, tm)
        try:
            track = future_track.result()
        except Exception as e:
            return {"error": True, "reason": str(e), "track_id": track_id}
        if track.get("error"):
            return track
        try:
            isrc = future_isrc.result()
        except Exception:
            isrc = None
    track["isrc"] = isrc
    return track

def get_tracks_parallel(track_ids, tm, max_workers=5):
    fetch_fn = partial(get_track_with_isrc, tm=tm)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(fetch_fn, track_ids))
    return results

def get_playlist_generator(playlist_id: str, tm: TokenManager, limit: int = PLAYLIST_LIMIT):
    offset = 0
    playlist_name = None
    playlist_owner = None
    playlist_cover = None
    total = None
    while True:
        payload = {
            "variables": {
                "uri": f"spotify:playlist:{playlist_id}",
                "offset": offset,
                "limit": limit,
                "enableWatchFeedEntrypoint": False,
                "includeEpisodeContentRatingsV2": False,
            },
            "operationName": "fetchPlaylist",
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": PLAYLIST_SHA256,
                },
            },
        }
        try:
            r = tm.request(
                "POST",
                "https://api-partner.spotify.com/pathfinder/v1/query",
                json=payload,
            )
            data = r.json()
        except Exception as e:
            print(f"[get_playlist] Request failed at offset {offset}: {e}")
            break

        pl = (
            data.get("data", {}).get("playlistV2")
            or data.get("data", {}).get("playlist")
        )
        if not pl:
            print(f"[get_playlist] Unexpected schema: {list(data.get('data', {}).keys())}")
            break

        if offset == 0:
            playlist_name = (
                pl.get("name")
                or pl.get("attributes", {}).get("name")
            )
            owner_data = (
                pl.get("ownerV2", {}).get("data", {})
                or pl.get("owner", {})
            )
            playlist_owner = (
                owner_data.get("name")
                or owner_data.get("displayName")
            )
            images = (
                pl.get("images", {}).get("items")
                or pl.get("coverArt", {}).get("sources")
                or []
            )
            if images:
                best = max(
                    images,
                    key=lambda x: x.get("maxWidth") or x.get("width") or x.get("height") or 0,
                )
                sources = best.get("sources") or []
                playlist_cover = (
                    best.get("url")
                    or (sources[0].get("url") if sources else None)
                )

        content = pl.get("content") or pl.get("tracks") or {}
        items = content.get("items") or content.get("edges") or []

        if total is None:
            total = content.get("totalCount") or content.get("total")

        if not items:
            break

        chunk_tracks = []
        for item in items:
            track_data = (
                item.get("itemV2", {}).get("data")
                or item.get("track")
                or item.get("node", {}).get("data")
                or {}
            )
            if not track_data or track_data.get("__typename") == "Episode":
                continue
            try:
                album = (
                    track_data.get("albumOfTrack")
                    or track_data.get("album")
                    or {}
                )
                first = [
                    a["profile"]["name"]
                    for a in track_data.get("firstArtist", {}).get("items", [])
                ]
                others = [
                    a["profile"]["name"]
                    for a in track_data.get("otherArtists", {}).get("items", [])
                ]
                if not first:
                    first = [
                        a.get("profile", {}).get("name") or a.get("name", "")
                        for a in (
                            track_data.get("artists", {}).get("items")
                            or track_data.get("artists")
                            or []
                        )
                    ]
                artists = [a for a in (first + others) if a]
                if not artists:
                    artists = ["Unknown Artist"]

                cover_sources = (
                    album.get("coverArt", {}).get("sources")
                    or album.get("images")
                    or []
                )
                cover_url = None
                if cover_sources:
                    best_img = max(
                        cover_sources,
                        key=lambda s: s.get("height") or s.get("width") or 0,
                    )
                    cover_url = best_img.get("url")

                raw_id = track_data.get("uri") or ""
                track_id = (
                    track_data.get("id")
                    or track_data.get("trackV2", {}).get("data", {}).get("id")
                )
                if not track_id and "spotify:track:" in raw_id:
                    track_id = raw_id.split(":")[-1]

                date = album.get("date") or {}
                iso = (date.get("isoString") or "")[:4]
                raw_year = date.get("year")
                year = iso or (str(raw_year) if raw_year else None)

                duration_ms = 0
                for k in ("duration", "trackDuration", "duration_ms", "length"):
                    val = track_data.get(k)
                    if isinstance(val, int):
                        duration_ms = val
                        break
                    elif isinstance(val, dict):
                        ms = val.get("totalMilliseconds")
                        if isinstance(ms, int):
                            duration_ms = ms
                            break

                chunk_tracks.append({
                    "title": track_data.get("name", "Unknown"),
                    "artists": artists,
                    "album": album.get("name"),
                    "album_id": album.get("id"),
                    "artist_id": next((a.get("uri", "").split(":")[-1] for a in track_data.get("firstArtist", {}).get("items", []) if a.get("uri")), None),
                    "year": year,
                    "duration_s": duration_ms // 1000,
                    "track_number": track_data.get("trackNumber"),
                    "cover_url": cover_url,
                    "spotify_url": f"https://open.spotify.com/track/{track_id}" if track_id else None,
                    "track_id": track_id,
                    "isrc": None,
                })
            except Exception as e:
                print(f"[get_playlist] Skipped track due to parse error: {e}")
                continue

        meta = {
            "name": playlist_name,
            "owner": playlist_owner,
            "cover_url": playlist_cover,
            "total": total,
        }

        yield meta, chunk_tracks
        offset += len(items)
        if total is not None and offset >= total:
            break
        if len(items) < limit:
            break

def get_playlist(playlist_id: str, tm: TokenManager, limit: int = PLAYLIST_LIMIT) -> dict:
    all_tracks = []
    meta = {}
    for m, chunk in get_playlist_generator(playlist_id, tm, limit):
        if not meta:
            meta = m
        all_tracks.extend(chunk)

    print(f"[get_playlist] Fetched {len(all_tracks)} tracks for '{meta.get('name')}'")
    return {
        "name": meta.get("name"),
        "owner": meta.get("owner"),
        "cover_url": meta.get("cover_url"),
        "tracks": all_tracks,
    }