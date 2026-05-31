import base64
import json
import os
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import requests
import string
import random
import threading

REDIRECT_URI   = os.getenv('SPOTIFY_REDIRECT_URI', "http://127.0.0.1:8888/callback")
SCOPES         = os.getenv('SPOTIFY_SCOPES', "playlist-read-private playlist-read-collaborative")

TOKEN_FILE = Path(__file__).resolve().parent / "token_store.json"
TOKEN_URL = "https://accounts.spotify.com/api/token"
AUTH_URL = "https://accounts.spotify.com/authorize"

def get_auth_url() -> str:
    state = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state
    }
    return AUTH_URL + "?" + urllib.parse.urlencode(params), state

def exchange_code(code: str) -> dict:
    auth_str = f"{CLIENT_ID}:{CLIENT_SECRET}"
    b64_auth = base64.b64encode(auth_str.encode()).decode()
    
    headers = {
        "Authorization": f"Basic {b64_auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI
    }
    
    r = requests.post(TOKEN_URL, headers=headers, data=data, timeout=15)
    r.raise_for_status()
    tok_data = r.json()
    tok_data["expires_at"] = time.time() + tok_data.get("expires_in", 3600)
    _save_token(tok_data)
    return tok_data

def refresh_access_token(refresh_token: str) -> dict:
    auth_str = f"{CLIENT_ID}:{CLIENT_SECRET}"
    b64_auth = base64.b64encode(auth_str.encode()).decode()
    
    headers = {
        "Authorization": f"Basic {b64_auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    
    r = requests.post(TOKEN_URL, headers=headers, data=data, timeout=15)
    r.raise_for_status()
    tok_data = r.json()
    
                                                       
    if "refresh_token" not in tok_data:
        tok_data["refresh_token"] = refresh_token
        
    tok_data["expires_at"] = time.time() + tok_data.get("expires_in", 3600)
    _save_token(tok_data)
    return tok_data

def _save_token(data: dict):
    TOKEN_FILE.write_text(json.dumps(data, indent=2))

def _load_token() -> dict:
    if TOKEN_FILE.exists():
        try:
            return json.loads(TOKEN_FILE.read_text())
        except Exception:
            pass
    return {}

def _browser_login() -> str:
    """
    Opens the Spotify auth page in the user's browser, starts a temporary
    local HTTP server to catch the redirect, extracts the code automatically,
    exchanges it for tokens, and returns the access_token.
    """
    auth_url, expected_state = get_auth_url()
    captured = {}

    class _CallbackHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass                                        

        def do_GET(self):
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)
            captured["code"] = params.get("code", [None])[0]
            captured["state"] = params.get("state", [None])[0]

            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body style='background:#1a1a2e;color:#e0e0e0;font-family:sans-serif;"
                b"display:flex;justify-content:center;align-items:center;height:100vh;margin:0'>"
                b"<div style='text-align:center'>"
                b"<h1 style='color:#1DB954'>&#10003; Spyde: Authorized!</h1>"
                b"<p>You can close this tab and return to Spyde.</p>"
                b"</div></body></html>"
            )

    try:
        server = HTTPServer(("127.0.0.1", 8888), _CallbackHandler)
    except OSError as e:
        print(f"[Spyde] Could not start auth server on port 8888: {e}")
        return None

    server.timeout = 120                    

    print("\n[Spyde] Opening Spotify login in your browser...")
    webbrowser.open(auth_url)

                                                              
    server.handle_request()
    server.server_close()

    code = captured.get("code")
    state = captured.get("state")

    if not code:
        print("[Spyde] No authorization code received. Login cancelled or timed out.")
        return None

    if state != expected_state:
        print("[Spyde] State mismatch — possible CSRF. Login rejected.")
        return None

    print("[Spyde] Authorization code received. Exchanging for token...")
    try:
        data = exchange_code(code)
        print("[Spyde] Successfully authenticated with Spotify!")
        return data.get("access_token")
    except Exception as e:
        print(f"[Spyde] Token exchange failed: {e}")
        return None

def get_valid_token() -> str:
    data = _load_token()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    expires_at = data.get("expires_at", 0)
    
    if not access_token:
        return _browser_login()
        
                            
    if time.time() >= expires_at - 60:
        if refresh_token:
            try:
                print("[Spyde] Refreshing expired Spotify token...")
                new_data = refresh_access_token(refresh_token)
                return new_data.get("access_token")
            except Exception as e:
                print(f"[Spyde] Failed to refresh token: {e}")
                return _browser_login()
        else:
            return _browser_login()
            
    return access_token
