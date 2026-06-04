import customtkinter as ctk
import threading
import dataclasses
import base64
import json
import time as _time
from pathlib import Path
from PIL import Image
from io import BytesIO
import requests
import re
import concurrent.futures
import os
import sys

from core.parser import InputParser, _thumb_cache
from core.models import Track
from core.download_controller import DownloadController
from core.http import get_bytes
from core.utils import sanitize_filename as core_sanitize

            
_API_BASE = "http://127.0.0.1:8008"

# Controls concurrent image downloads to prevent GIL contention
thumb_semaphore = threading.Semaphore(5)

class TrackItem(ctk.CTkFrame):
    def __init__(self, parent, track: Track, controller, toggle_callback):
        super().__init__(parent, fg_color="transparent")
        self.track = track
        self.controller = controller
        self.toggle_cb = toggle_callback
        self.selected = ctk.BooleanVar(value=True)
        self.scroll_canvas = parent._parent_canvas

                                                                              
        self.chk_outer = ctk.CTkFrame(
            self, width=22, height=22, corner_radius=6, border_width=2, 
            border_color="#E11D2E", fg_color="transparent", cursor="hand2"
        )
        self.chk_outer.pack_propagate(False)
        self.chk_outer.pack(side="left", padx=(10, 5))
        
        self.chk_inner = ctk.CTkFrame(
            self.chk_outer, width=12, height=12, corner_radius=4, 
            fg_color="#E11D2E", cursor="hand2"
        )
        self.chk_inner.place(relx=0.5, rely=0.5, anchor="center")
        
        self.chk_outer.bind("<Button-1>", self.toggle_custom)
        self.chk_inner.bind("<Button-1>", self.toggle_custom)

        self.thumb_lbl = ctk.CTkLabel(self, text="🎵", width=64, height=36, fg_color="#1A1C23", corner_radius=8)
        self.thumb_lbl.pack(side="left", padx=5)
        self._photo = None
        
                                                         
        self._last_thumb_url = None
        if track.cover_url:
            self._last_thumb_url = track.cover_url
            self.controller._thumb_pool.submit(self.load_thumb)

        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.pack(side="left", fill="x", expand=True, padx=5)

        title = track.title or 'Unknown'
        if len(title) > 40: title = title[:37] + "..."

        self.lbl_title = ctk.CTkLabel(info_frame, text=title, font=("Inter", 14, "bold"), anchor="w", text_color="#FFFFFF")
        self.lbl_title.pack(fill="x")

        artist = ', '.join(dict.fromkeys(track.artists)) if track.artists else 'Unknown'

        album = track.album or ''
        duration = ""

        if track.duration:
            m = int(track.duration) // 60
            s = int(track.duration) % 60
            duration = f"{m}:{s:02d}"

        line = artist

        if album:
            line += f" • {album}"

        if duration:
            line += f" • {duration}"

        self.lbl_artist = ctk.CTkLabel(info_frame, text=line, font=("Inter", 12), text_color="#A0A4A8", anchor="w")
        self.lbl_artist.pack(fill="x")


                                                                                             
        # Defer touchpad scrolling bind to ensure canvas is ready
        self.after(100, self._bind_scrolling)

    def _bind_scrolling(self):
        try:
            canvas = self.scroll_canvas
            
            def _scroll_linux_up(e): canvas.yview_scroll(-1, "units")
            def _scroll_linux_down(e): canvas.yview_scroll(1, "units")
            def _scroll_other(e):
                                                      
                d = e.delta
                if d == 0: return
                                                                              
                steps = -1 * int(d / 120) if abs(d) >= 120 else -1 * int(d / abs(d))
                canvas.yview_scroll(steps, "units")
            
            def _recursive_bind(widget):
                widget.bind("<Button-4>", _scroll_linux_up, add="+")
                widget.bind("<Button-5>", _scroll_linux_down, add="+")
                widget.bind("<MouseWheel>", _scroll_other, add="+")
                for child in widget.winfo_children():
                    _recursive_bind(child)
                    
            _recursive_bind(self)
        except Exception as e:
            print(f"Could not bind scrolling: {e}")

    def load_thumb(self):
        url = self.track.cover_url
        if not url: return
        self._load_thumb_url(url)

    def _load_thumb_url(self, url):
        """Download and render a thumbnail from `url` into this row's thumb_lbl."""
        with thumb_semaphore:
            try:
                headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36...'}
                response = requests.get(url, headers=headers, timeout=20)
                
                if response.status_code == 200:
                                                                            
                    self.track._cached_bytes = response.content
                    pil_img = Image.open(BytesIO(response.content)).convert("RGBA")
                    pil_img = pil_img.resize((48, 48), Image.LANCZOS)

                    # Generate rounded corner mask
                    radius = 8
                    mask = Image.new("L", (48, 48), 0)
                    from PIL import ImageDraw
                    draw = ImageDraw.Draw(mask)
                    draw.rounded_rectangle([(0, 0), (48, 48)], radius=radius, fill=255)

                    rounded_img = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
                    rounded_img.paste(pil_img, mask=mask)

                    def _apply(pil=rounded_img):
                        self._thumb_ctk = ctk.CTkImage(light_image=pil, dark_image=pil, size=(48, 48))
                        self.thumb_lbl.configure(image=self._thumb_ctk, text="", fg_color="transparent")
                    self.after(0, _apply)
            except Exception as e:
                print(f"[Thumb Error] {e}")
                self.after(0, lambda: self.thumb_lbl.configure(text="❌"))

    def _apply_cached_thumb(self, data):
        """Render a thumbnail from cached bytes without a network call."""
        try:
            pil_img = Image.open(BytesIO(data)).convert("RGBA")
            pil_img = pil_img.resize((48, 48), Image.LANCZOS)

            radius = 8
            mask = Image.new("L", (48, 48), 0)
            from PIL import ImageDraw
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle([(0, 0), (48, 48)], radius=radius, fill=255)

            rounded_img = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
            rounded_img.paste(pil_img, mask=mask)

            def _apply(pil=rounded_img):
                self._thumb_ctk = ctk.CTkImage(light_image=pil, dark_image=pil, size=(48, 48))
                self.thumb_lbl.configure(image=self._thumb_ctk, text="", fg_color="transparent")
            self.after(0, _apply)
        except Exception as e:
            print(f"[Thumb Cache Error] {e}")

    def _clear_thumbnail(self):
        """Reset thumbnail state during refresh to prevent phantom images."""
        self.thumb_lbl.configure(image=None, text="🎵")
        self._photo = None

    def update_metadata(self):
        """Called after background enrichment: refreshes the thumbnail and subtitle label."""
        new_url = self.track.cover_url

                                                       
        if new_url and new_url != self._last_thumb_url:
            self._last_thumb_url = new_url
            self._clear_thumbnail()
            self.controller._thumb_pool.submit(self._load_thumb_url, new_url)

                                                       
        def _refresh_subtitle():
            artist = ', '.join(dict.fromkeys(self.track.artists)) if self.track.artists else 'Unknown'
            album = self.track.album or ''
            duration = ""

            if self.track.duration:
                m = int(self.track.duration) // 60
                s = int(self.track.duration) % 60
                duration = f"{m}:{s:02d}"

            line = artist

            if album:
                line += f" • {album}"

            if duration:
                line += f" • {duration}"

            self.lbl_artist.configure(text=line)
        self.after(0, _refresh_subtitle)

    def on_toggle(self):
        if self.toggle_cb: self.toggle_cb()

    def toggle_custom(self, event=None):
        self.set_selected(not self.selected.get())

    def set_selected(self, state: bool):
        """Single source of truth for checkbox state + visuals."""
        self.selected.set(state)
        if state:
            self.chk_outer.configure(border_color="#E11D2E")
            self.chk_inner.place(relx=0.5, rely=0.5, anchor="center")
        else:
            self.chk_outer.configure(border_color="#2A2D35")
            self.chk_inner.place_forget()
        self.on_toggle()

               
def get_default_download_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("USERPROFILE", Path.home())) / "Downloads"
    else:
        base = Path.home() / "Downloads"
    path = base / "Ember"
    path.mkdir(parents=True, exist_ok=True)
    return path

DOWNLOAD_DIR = get_default_download_dir()

       
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class Ember(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Ember")
        self.geometry("900x650")
        self.resizable(True, True)
        self.minsize(800, 600)
        self.configure(fg_color="#0B0C10")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

                        
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.frames = {}
        self.video_data = {}
        self._enrichment_session_id = 0

                                                                          
        self.download_controller = DownloadController(
            download_dir=Path(__file__).resolve().parent / "downloads",
            max_workers=3,
        )
                                                          
        # Central thread pool for async UI image loading
        self._thumb_pool = concurrent.futures.ThreadPoolExecutor(max_workers=5)

                                                            
        from core.api.server import start_background
        start_background(controller=self.download_controller)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        for F in (HomeFrame, DetailsFrame):
            frame_name = F.__name__
            frame = F(parent=self.container, controller=self)
            self.frames[frame_name] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame("HomeFrame")

                                 
        # Lock UI during mandatory startup authorization checks
        self._lock_input()
        threading.Thread(target=self._startup_warmup, daemon=True).start()

    def _on_close(self):
        """Clean shutdown: stop executors before destroying window."""
        self.download_controller.shutdown()
        self._thumb_pool.shutdown(wait=False, cancel_futures=True)
        self.destroy()

    def _lock_input(self):
        home = self.frames.get("HomeFrame")
        if home:
            home.url_entry.configure(state="disabled")
            home.status.configure(text="Booting system...", text_color="#888888")
            home.start_loader()

    def _unlock_input(self):
        home = self.frames.get("HomeFrame")
        if home:
            home.stop_loader()
            home.url_entry.configure(state="normal")
            home.status.configure(text="Ready", text_color="#00FF00")

    def _startup_warmup(self):
        """Zero-latency startup sequence."""
        try:
            from core.spotify_client import get_track, get_isrc
            from core.token_manager import _tm
            import time
            
            home = self.frames["HomeFrame"]
            
                    
            self.after(0, lambda: home.status.configure(text="Initializing core..."))
            time.sleep(0.5)
            
                    
            self.after(0, lambda: home.status.configure(text="Syncing Spotify..."))
            start = time.time()
            if not getattr(_tm, "_warmup_done", False):
                _tm.get_headers()
                _tm._warmup_done = True
            elapsed = time.time() - start
            if elapsed < 0.6:
                time.sleep(0.6 - elapsed)
            
                    
            self.after(0, lambda: home.status.configure(text="Warming metadata engine..."))
            start = time.time()
            get_track("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT")
            elapsed = time.time() - start
            if elapsed < 0.6:
                time.sleep(0.6 - elapsed)
            
                    
            self.after(0, lambda: home.status.configure(text="Optimizing pipeline..."))
            start = time.time()
            get_isrc("4cOdK2wGLETKBW3PvgPWqT", _tm)
            elapsed = time.time() - start
            if elapsed < 0.5:
                time.sleep(0.5 - elapsed)
            
        except Exception as e:
            print(f"[Startup] Warmup failed: {e}")
            
        finally:
            self.after(0, self._unlock_input)

    def show_frame(self, frame_name):
        frame = self.frames[frame_name]
        frame.tkraise()
        if frame_name == "DetailsFrame" and self.video_data:
            frame.update_details(self.video_data)

    def fetch_video_data(self, url):
        # Increment session ID to safely orphan any lingering background threads
        self._enrichment_session_id += 1                               
        threading.Thread(target=self._fetch, args=(url,), daemon=True).start()

    def _fetch(self, input_str):
                                          
        states = [
            "Waking engine...",
            "Mapping source...",
            "Extracting structure...",
            "Preparing interface..."
        ]
        self._fetch_state_idx = 0
        self._fetch_active = True

        def _cycle_status():
            if not self._fetch_active:
                return
            home = self.frames.get("HomeFrame")
            if home:
                home.status.configure(text=states[self._fetch_state_idx % len(states)])
                self._fetch_state_idx += 1
            self.after(500, _cycle_status)

        self.after(0, _cycle_status)

        try:
            print(f"[Ember] Parsing input: {input_str}")
            tracks = InputParser.parse(input_str)
            
            if not tracks:
                raise Exception("Could not parse input into any tracks.")
            
                                                                   
            from core.enrich import enrich_tracks, apply_enrichment_updates
            priority = [t for t in tracks if not getattr(t, '_enriched', True)][:5]
            if priority:
                updates, _ = enrich_tracks(priority)
                if updates:
                    apply_enrichment_updates(updates)

            self._build_unified_data(tracks, input_str)
            
            self._fetch_active = False
            self.after(0, lambda: self.frames["HomeFrame"].stop_loader())
            self.after(0, lambda: self.show_frame("DetailsFrame"))
            self.after(0, lambda: self.frames["HomeFrame"].reset_ui())

                                                                 
            if any(not getattr(t, '_enriched', True) for t in tracks):
                current_session = self._enrichment_session_id
                threading.Thread(target=self._start_enrichment, args=(tracks, current_session), daemon=True).start()
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[Ember] _fetch error: {e}")
            self._fetch_active = False
            self.after(0, lambda: self.frames["HomeFrame"].stop_loader())
            self.after(0, lambda e=e: self.frames["HomeFrame"].show_error(f"Error: {str(e)}"))

    def _start_enrichment(self, tracks, session_id):
        """Background thread: batch-enrich all tracks via parallel backend, then update UI once."""
        if session_id != self._enrichment_session_id:
            return
        details_frame = self.frames.get("DetailsFrame")
        
        unenriched = [t for t in tracks if not getattr(t, '_enriched', True)]
        if not unenriched:
            return
        
                                  
        if details_frame:
            self.after(0, lambda: details_frame.status_label.configure(
                text="Enhancing metadata...", text_color="#777"
            ))
        
        from core.enrich import enrich_tracks, apply_enrichment_updates
        
        checker = lambda: session_id == self._enrichment_session_id
        
                                              
        track_map = {}
        if details_frame:
            track_map = {id(item.track): item for item in getattr(details_frame, 'track_items', [])}
        
        def apply_and_refresh(updates):
            """Apply data mutations and UI refresh on main thread."""
            if session_id != self._enrichment_session_id:
                return
            modified = apply_enrichment_updates(updates)
            for target in modified:
                item = track_map.get(id(target))
                if item:
                    item.update_metadata()
        
                                                                      
        priority = unenriched[:5]
        rest = unenriched[5:]
        
                                                   
        if priority:
            if session_id != self._enrichment_session_id:
                return
            print(f"[Ember] Priority enriching {len(priority)} tracks...")
            updates, error = enrich_tracks(priority, session_checker=checker)
            if error:
                print(f"[Ember] Enrichment error: {error.get('reason')}")
            if session_id != self._enrichment_session_id:
                return
            if updates:
                self.after(0, lambda u=updates: apply_and_refresh(u))
        
                                                    
        if rest:
            if session_id != self._enrichment_session_id:
                return
            print(f"[Ember] Enriching remaining {len(rest)} tracks...")
            updates, error = enrich_tracks(rest, session_checker=checker)
            if error:
                print(f"[Ember] Enrichment error: {error.get('reason')}")
            if session_id != self._enrichment_session_id:
                return
            if updates:
                self.after(0, lambda u=updates: apply_and_refresh(u))
        
                                                                 
        if session_id == self._enrichment_session_id and details_frame:
            self.after(0, lambda: details_frame.status_label.configure(text=""))

    def _build_unified_data(self, tracks, raw_input):
        is_playlist = len(tracks) > 1
        
        # Establish a fallback cover from the first available track
        primary_cover = None
        for t in tracks:
            if t.cover_url:
                primary_cover = t.cover_url
                break

        if is_playlist:
            # --- FIX: Prioritize Mosaic Cover & Playlist Metadata ---
            t0 = tracks[0]
            
            # Prefer parent metadata (e.g. Playlist/Album Name) if provided by parser
            pl_title = getattr(t0, 'parent_name', t0.album or "Spotify Playlist")
            pl_owner = getattr(t0, 'parent_owner', "Spotify Collection")
            
            # Fall back to primary_cover if the parent collection lacks dedicated artwork
            pl_cover_url = getattr(t0, 'parent_cover', primary_cover)
            cover_bytes = get_bytes(pl_cover_url, timeout=3) if pl_cover_url else None

            self.video_data = {
                'title': pl_title,
                'uploader': f"{pl_owner} • {len(tracks)} Tracks",
                'album': pl_title,
                'is_playlist': True,
                '_tracks': tracks,
                'thumbnail_bytes': cover_bytes,
                'is_spotify': any(t.source == "spotify" for t in tracks),
                'is_local': any(t.source == "local" for t in tracks),
                'media_type': getattr(tracks[0], 'media_type', 'audio_video'),
                'carousel': {'frames': None, 'caption': '', 'download_urls': [], 'media_types': []},
            }
        else:
            t = tracks[0]
            thumb_url = t.cover_url or primary_cover
            is_local = t.source == "local"

            thumb_bytes = None
            carousel = {'frames': None, 'caption': '', 'download_urls': [], 'media_types': []}

            if is_local:
                try:
                    from mutagen.id3 import ID3
                    audio = ID3(raw_input)
                    for tag in audio.values():
                        if tag.FrameID == "APIC":
                            thumb_bytes = tag.data
                            break
                except Exception:
                    pass
            else:
                # Map extracted URL structures to their corresponding _thumb_cache keys
                cache_key = None
                sc = re.search(r'/p/([A-Za-z0-9_-]+)', raw_input)
                if sc: cache_key = sc.group(1)
                if not cache_key:
                    story_m = re.search(r'/stories/[^/]+/(\d+)', raw_input)
                    if story_m: cache_key = f"story_{story_m.group(1)}"
                if not cache_key:
                    tweet_m = re.search(r'/status/(\d+)', raw_input)
                    if tweet_m: cache_key = f"tweet_{tweet_m.group(1)}"
                if not cache_key:
                    reddit_m = re.search(r'/comments/([a-z0-9]+)', raw_input)
                    if reddit_m: cache_key = f"reddit_{reddit_m.group(1)}"
                if not cache_key and _thumb_cache:
                    cache_key = next(iter(_thumb_cache), None)

                if cache_key and cache_key in _thumb_cache:
                    cached = _thumb_cache.pop(cache_key)
                    frames = cached['frames']
                    thumb_bytes = frames[0] if frames else None
                    carousel = {
                        'frames': frames,
                        'caption': cached.get('caption', ''),
                        'download_urls': cached.get('download_urls', []),
                        'media_types': cached.get('media_types', []),
                    }
                else:
                    thumb_bytes = get_bytes(thumb_url)

            self.video_data = {
                'title': t.title,
                'uploader': ', '.join(dict.fromkeys(t.artists)) if t.artists else "Unknown Artist",
                'album': t.album,
                'duration_str': f"{int(t.duration) // 60}:{int(t.duration) % 60:02d}" if t.duration else None,
                'thumbnail_bytes': thumb_bytes,
                'url': None if t.source == "local" else (getattr(t, 'spotify_url', None) or raw_input),
                'original_ext': 'mp3',
                'is_spotify': t.source == "spotify",
                'is_local': t.source == "local",
                'is_playlist': False,
                '_track_obj': t,
                'media_type': getattr(t, 'media_type', 'audio_video'),
                'carousel': carousel,
            }

    def load_image(self, url):
        if not url: return None
        try:
            return self.load_image_from_bytes(get_bytes(url))
        except: return None
        
    def load_image_from_bytes(self, data):
        if not data: return None
        try:
            pil_image = Image.open(BytesIO(data)).convert("RGBA")
            
            # Dynamically scale image while maintaining original aspect ratio
            max_w, max_h = 480, 270
            ratio = min(max_w / pil_image.width, max_h / pil_image.height)
            new_w = int(pil_image.width * ratio)
            new_h = int(pil_image.height * ratio)
            pil_image = pil_image.resize((new_w, new_h), Image.LANCZOS)
            
            # Generate and apply a rounded rectangular mask to the resized image
            radius = 15
            mask = Image.new("L", (new_w, new_h), 0)
            from PIL import ImageDraw
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle([(0, 0), (new_w, new_h)], radius=radius, fill=255)
            rounded_img = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 0))
            rounded_img.paste(pil_image, mask=mask)
            
            return ctk.CTkImage(light_image=rounded_img, dark_image=rounded_img, size=(new_w, new_h))
        except Exception as e:
            print(f"[DEBUG] load_image_from_bytes failed: {e}")
            return None



class HomeFrame(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        
        self.center_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.center_frame.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            self.center_frame, 
            text="Ember", 
            font=("Inter", 64, "bold"),
            text_color="#FFFFFF"
        ).pack(pady=(0, 6))

        ctk.CTkLabel(
            self.center_frame,
            text="Yours, forever.",
            font=("Inter", 16),
            text_color="#A0A4A8"
        ).pack(pady=(0, 50))

        self.url_entry = ctk.CTkEntry(
            self.center_frame,
            width=540,
            height=60,
            placeholder_text="Paste Link Here...",
            font=("Inter", 16),
            border_width=2,
            border_color="#1F2833",
            fg_color="#15171E",
            text_color="#FFFFFF",
            placeholder_text_color="#555555",
            corner_radius=18
        )
        self.url_entry.pack(pady=15)
        
                                                 
        self.url_entry.bind("<Return>", self.start_fetch_event)
        self.url_entry.bind("<KP_Enter>", self.start_fetch_event)

        ctk.CTkLabel(
            self.center_frame,
            text="Press Enter to inspect",
            font=("Inter", 13),
            text_color="#555555"
        ).pack(pady=(8, 30))

        self.status = ctk.CTkLabel(self.center_frame, text="", text_color="#FF5555")
        self.status.pack()

                                                     
        self.loader = ctk.CTkLabel(
            self.center_frame,
            text="",
            font=("Inter", 26),
            text_color="#E11D2E"
        )
        self.loader.pack(pady=(10, 0))
        self.loader.pack_forget()
        self._loading = False

    def start_fetch_event(self, event=None):
        self.start_fetch()

    def start_fetch(self):
        url = self.url_entry.get().strip()
        if not url: return
        self.status.configure(text="Input received...", text_color="#888")
        self.start_loader()
        self.after(100, lambda: self.status.configure(text="Initializing engine...", text_color="#CCCCCC"))
        self.controller.fetch_video_data(url)

    def start_loader(self):
        self._loading = True
        self.loader.pack()
        self._spinner_states = ["●∙∙∙", "∙●∙∙", "∙∙●∙", "∙∙∙●", "∙∙●∙", "∙●∙∙"]
        self._spinner_index = 0
        self._animate_loader()

    def _animate_loader(self):
        if not getattr(self, '_loading', False):
            return
        self.loader.configure(text=self._spinner_states[self._spinner_index])
        self._spinner_index = (self._spinner_index + 1) % len(self._spinner_states)
        self.after(120, self._animate_loader)

    def stop_loader(self):
        self._loading = False
        self.loader.pack_forget()

    def show_error(self, msg):
        self.stop_loader()
        self.status.configure(text=msg, text_color="#FF5555")
        self.reset_ui()

    def reset_ui(self):
        if any(k in self.status.cget("text") for k in ["Inspecting", "Scanning", "Initializing", "Parsing", "Extracting", "Preparing"]):
            self.status.configure(text="")

class DetailsFrame(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.track_items = []
        self.is_playlist = False
        self.data = None

                
        self.nav = ctk.CTkFrame(self, height=50, fg_color="transparent")
        self.nav.pack(fill="x", padx=30, pady=(15, 5))
        
        ctk.CTkButton(
            self.nav, text="← Back", width=80, height=32,
            fg_color="transparent", border_width=1, text_color="white",
            corner_radius=8,
            command=lambda: controller.show_frame("HomeFrame")
        ).pack(side="left")

                     
        self.main_content = ctk.CTkFrame(self, fg_color="transparent")
        self.main_content.pack(fill="both", expand=True, padx=25, pady=(10, 20))
        self.main_content.grid_columnconfigure(0, weight=2)
        self.main_content.grid_columnconfigure(1, weight=3)
        self.main_content.grid_rowconfigure(0, weight=1)

                              
        self.left_col = ctk.CTkFrame(self.main_content, fg_color="#15171E", corner_radius=16)
        self.left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 15))

                          
        self.thumb_label = ctk.CTkLabel(self.left_col, text="", corner_radius=10)
        self.thumb_label.pack(pady=10)

                                                  
        self.playlist_cover = ctk.CTkLabel(self.left_col, text="", corner_radius=10)

                                               
        self.playlist_controls = ctk.CTkFrame(self.left_col, fg_color="transparent")
        ctk.CTkButton(
            self.playlist_controls, text="Select All", width=90, height=28,
            font=("Inter", 12), corner_radius=14,
            fg_color="#1F2833", hover_color="#2A3746", text_color="#FFFFFF",
            command=self.select_all
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            self.playlist_controls, text="Deselect All", width=90, height=28,
            font=("Inter", 12), corner_radius=14,
            fg_color="#1F2833", hover_color="#2A3746", text_color="#FFFFFF",
            command=self.select_none
        ).pack(side="left", padx=4)

                                                   
        self.playlist_scroll = ctk.CTkScrollableFrame(
            self.left_col, label_text="", fg_color="transparent"
        )

                                                                                            
        self.save_cover_btn = ctk.CTkButton(
            self.left_col, text="💾 Save Cover", width=100, height=24,
            font=("Inter", 12), fg_color="transparent", hover_color="#1F2833",
            text_color="#A0A4A8", cursor="hand2", corner_radius=12,
            command=self.save_thumbnail
        )

                                
        self.right_col = ctk.CTkFrame(self.main_content, fg_color="#15171E", corner_radius=16)
                                                                                       
        self.right_col_inner = ctk.CTkFrame(self.right_col, fg_color="transparent")
        self.right_col_inner.pack(fill="both", expand=True, padx=25, pady=25)
        self.right_col.grid(row=0, column=1, sticky="nsew", padx=(15, 0))

               
        self.title_frame = ctk.CTkFrame(self.right_col_inner, fg_color="transparent")
        self.title_frame.pack(anchor="w", fill="x", pady=(0, 2))
        
        self.title_label = ctk.CTkLabel(
            self.title_frame, text="", 
            font=("Inter", 24, "bold"), wraplength=420, justify="left",
            anchor="w", text_color="#FFFFFF"
        )
        self.title_label.pack(side="left", fill="x", expand=True)

                                                                        
        self.meta_label = ctk.CTkLabel(
            self.right_col_inner, text="",
            font=("Inter", 14), text_color="#A0A4A8",
            anchor="w", justify="left", wraplength=420
        )
        self.meta_label.pack(anchor="w", fill="x", pady=(0, 6))

                   
        self.separator = ctk.CTkFrame(self.right_col_inner, height=1, fg_color="#2A2D35")
        self.separator.pack(fill="x", pady=(4, 16))

                                                                          
        self.meta_textbox = ctk.CTkTextbox(
            self.right_col_inner,
            font=("Inter", 14),
            text_color="#A0A4A8",
            fg_color="#1A1C23",
            border_width=1,
            border_color="#2A2D35",
            corner_radius=12,
            wrap="word",
            height=100,
            scrollbar_button_color="#2A2D35",
            scrollbar_button_hover_color="#3B404A",
        )
                                                                   

                                             
        self.format_label = ctk.CTkLabel(self.right_col_inner, text="Format", font=("Inter", 13, "bold"), text_color="#A0A4A8")
        self.format_label.pack(anchor="w")
        self.format_seg = ctk.CTkSegmentedButton(
            self.right_col_inner, values=["Audio (MP3)", "Video (MP4)"],
            command=self.update_quality_options,
            selected_color="#0A84FF", selected_hover_color="#0062CC",
            font=("Inter", 13), corner_radius=12
        )
        self.format_seg.set("Audio (MP3)")
        self.format_seg.pack(anchor="w", pady=(4, 14), fill="x")

                                              
        self.quality_label = ctk.CTkLabel(self.right_col_inner, text="Quality", font=("Inter", 13, "bold"), text_color="#A0A4A8")
        self.quality_label.pack(anchor="w")
        self.quality_combo = ctk.CTkComboBox(
            self.right_col_inner, values=["Best Available", "320 kbps", "192 kbps"],
            state="readonly", font=("Inter", 13), corner_radius=12,
            button_color="#1F2833", button_hover_color="#2A3746",
            border_color="#1F2833", dropdown_fg_color="#1A1C23", dropdown_hover_color="#2A3746"
        )
        self.quality_combo.pack(anchor="w", pady=(4, 18), fill="x")

                                                             
        self.audio_fmt_label = ctk.CTkLabel(
            self.right_col_inner, text="Audio Format",
            font=("Inter", 13, "bold"), text_color="#A0A4A8"
        )
        self.audio_fmt_combo = ctk.CTkComboBox(
            self.right_col_inner,
            width=200,
            values=[
                "MP3",
                "FLAC (Lossless)",
                "M4A",
                "OGG",
                "OPUS",
                "WAV (Lossless)",
            ],
            state="readonly", font=("Inter", 13), corner_radius=12,
            button_color="#1F2833", button_hover_color="#2A3746",
            border_color="#1F2833", dropdown_fg_color="#1A1C23", dropdown_hover_color="#2A3746"
        )
        self.audio_fmt_combo.set("MP3")
                                                     

                  
        self.progress_bar = ctk.CTkProgressBar(self.right_col_inner, progress_color="#E11D2E", height=4, corner_radius=2)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", pady=(0, 6))

        self.status_label = ctk.CTkLabel(self.right_col_inner, text="", text_color="#A0A4A8", font=("Inter", 12))
        self.status_label.pack(anchor="e")

                         
        self.download_btn = ctk.CTkButton(
            self.right_col_inner, text="Download", 
            height=48, font=("Inter", 16, "bold"),
            fg_color="#E11D2E", hover_color="#B91C1C", text_color="#FFFFFF",
            corner_radius=24,
            command=self.start_download
        )
        self.download_btn.pack(fill="x", pady=(12, 0))

    def _reset_layout(self):
        """Unpack all dynamic widgets to prepare for fresh layout."""
        for w in [
            self.thumb_label, self.playlist_cover, self.playlist_controls,
            self.playlist_scroll, self.save_cover_btn, self.meta_textbox,
            self.separator,
            self.format_label, self.format_seg, self.quality_label, self.quality_combo,
            self.audio_fmt_label, self.audio_fmt_combo
        ]:
            w.pack_forget()

                                                              
        if hasattr(self, '_carousel_frame') and self._carousel_frame.winfo_exists():
            self._carousel_frame.destroy()
        self._carousel_images = []

    def update_details(self, data):
        self.data = data
        self.is_playlist = data.get('is_playlist', False)
        is_spotify = data.get('is_spotify', False)
        is_local = data.get('is_local', False)
        media_type = data.get('media_type', 'audio_video')

                                   
        self._reset_layout()

                                                       
        thumb_bytes = data.get('thumbnail_bytes')
        self._thumb_image = self.controller.load_image_from_bytes(thumb_bytes) if thumb_bytes else None

                                  
        self.refresh_labels()

        # --- Left column layout ---
        if self.is_playlist:
            self.thumb_label.pack_forget()
            
            if self._thumb_image:
                self.playlist_cover.configure(image=self._thumb_image, text="")
            else:
                self.playlist_cover.configure(text="No Cover", height=180)
            self.playlist_cover.pack(pady=(10, 4))
            if self._thumb_image:
                self.save_cover_btn.pack(pady=(0, 6))
            
            self.playlist_controls.pack(pady=(4, 8))
            self.playlist_scroll.pack(fill="both", expand=True, pady=(0, 10))
            
            for child in self.playlist_scroll.winfo_children():
                child.destroy()
            self.track_items = []
            
            tracks = data.get('_tracks', [])
            for track in tracks:
                item = TrackItem(self.playlist_scroll, track, self.controller, self.on_selection_change)
                item.pack(fill="x", pady=2)
                self.track_items.append(item)
            
            self.on_selection_change()

        else:
            self.playlist_scroll.pack_forget()
            self.playlist_controls.pack_forget()
            self.playlist_cover.pack_forget()
            
            self.thumb_label.pack(pady=10)
            
            if self._thumb_image:
                self.thumb_label.configure(image=self._thumb_image, text="", fg_color="transparent")
                self.save_cover_btn.pack(pady=(0, 6))
            else:
                self.thumb_label.configure(text="🎵", font=("Calibri", 60), fg_color="#333", width=160, height=160)

        # --- Right column: context-aware controls ---
        self.separator.pack(fill="x", pady=(4, 16))
        self.progress_bar.set(0)
        self.status_label.configure(text="")

        if is_local:
                                               
            self.download_btn.configure(state="disabled", text="Local File (No Download)")
            
        elif is_spotify:
                                                 
            self.audio_fmt_label.pack(anchor="w")
            self.audio_fmt_combo.pack(anchor="w", pady=(4, 18))
            self.download_btn.configure(
                state="normal",
                text=f"Download {len(data.get('_tracks', []))} Tracks" if self.is_playlist else "Download",
                command=self.start_download
            )

        elif media_type in ("image", "mixed"):
                                                      
            carousel = data.get('carousel', {})
            carousel_frames = carousel.get('frames') or []
            n_items = len(carousel_frames)
            if media_type == "mixed":
                btn_text = f"Download All Media ({n_items})" if n_items > 1 else "Download Media"
            else:
                btn_text = f"Download {n_items} Images" if n_items > 1 else "Download Image"

            self.download_btn.configure(
                state="normal", text=btn_text,
                command=self.start_image_download
            )
            if carousel_frames:
                self.thumb_label.pack_forget()
                self.progress_bar.pack_forget()
                self.after(0, lambda: self._build_carousel(
                    carousel_frames, carousel.get('media_types', [])
                ))
            else:
                self.thumb_label.pack(pady=10)
                self.progress_bar.pack_forget()

        else:
                                                                    
            self.format_label.pack(anchor="w")
            self.format_seg.pack(anchor="w", pady=(4, 14), fill="x")
            self.quality_label.pack(anchor="w")
            self.quality_combo.pack(anchor="w", pady=(4, 18), fill="x")
            self.download_btn.configure(
                state="normal", text="Download",
                command=self.start_download
            )

    def start_image_download(self):
        """Delegate image/media download via API."""
        self.download_btn.configure(state="disabled", text="Downloading...")
        self.progress_bar.set(0.0)

                            
        body = {
            "title": self.data.get("title", "image"),
            "url": self.data.get("url"),
            "spotify_url": self.data.get("spotify_url"),
            "carousel": self.data.get("carousel", {}),
        }
        thumb = self.data.get("thumbnail_bytes")
        if thumb:
            body["thumbnail_bytes_b64"] = base64.b64encode(thumb).decode()
                                                                   
        carousel = body.get("carousel", {})
        if carousel.get("frames"):
            body["carousel"] = {
                k: v for k, v in carousel.items() if k != "frames"
            }

        def _on_event(payload):
            t = payload["type"]
            msg = payload.get("message", "")
            if t == "status":
                self.after(0, lambda m=msg: self.download_btn.configure(text=m))
            elif t in ("complete", "error"):
                ok = payload.get("success", False)
                color = "#2ECC71" if ok else "#E74C3C"
                self.after(0, lambda m=msg, c=color: self.download_btn.configure(
                    text=m, text_color=c
                ))
                self.after(3000, lambda: self.download_btn.configure(
                    state="normal", text="Download Media", text_color=["gray10", "#DCE4EE"]
                ))

                                                                              
                                                                                 
        if carousel.get("frames"):
            self.controller.download_controller.download_media(
                self.data, callback=_on_event
            )
            return

        self._api_submit("POST", "/download/media", body, _on_event)

    def on_selection_change(self):
        count = sum(1 for item in self.track_items if item.selected.get())
        self.download_btn.configure(text=f"Download {count} Tracks")

    def select_all(self):
        for item in self.track_items:
            item.set_selected(True)
        self.on_selection_change()

    def select_none(self):
        for item in self.track_items:
            item.set_selected(False)
        self.on_selection_change()

    def refresh_labels(self):
        self.title_label.configure(text=self.data['title'])

        artist = self.data.get('uploader', '')
        album = self.data.get('album') or ''
        dur = self.data.get('duration_str')
    
        line = artist
    
        if album:
            line += f"  •  {album}"
    
        if dur and dur != '0:00' and self.data.get('media_type') != 'image':
            line += f"  •  {dur}"
    
        if self.data.get('is_local'):
            line += "  •  Local File"
    
        self.meta_label.configure(text=line)
    
                                        
        caption = (self.data.get('carousel') or {}).get('caption', '')
        self.meta_textbox.pack_forget()
        if caption:
            self.meta_textbox.configure(state="normal")
            self.meta_textbox.delete("1.0", "end")
            self.meta_textbox.insert("1.0", caption)
            self.meta_textbox.configure(state="disabled")
            self.meta_textbox.pack(anchor="w", fill="x", pady=(0, 12), padx=(0, 4))

    def _build_carousel(self, frames_bytes, media_types=None):
                                          
        if hasattr(self, '_carousel_frame') and self._carousel_frame.winfo_exists():
            self._carousel_frame.destroy()

        if not media_types:
            media_types = ["photo"] * len(frames_bytes)

        self._carousel_images = []
        self._carousel_media_types = media_types
        
        for i, b in enumerate(frames_bytes):
            try:
                from PIL import Image as PImage, ImageDraw as PIDraw, ImageFont
                from io import BytesIO as BIO
                
                pil = PImage.open(BIO(b)).convert("RGBA")

                                                            
                max_w, max_h = 420, 520
                ratio = min(max_w / pil.width, max_h / pil.height)
                new_w = int(pil.width * ratio)
                new_h = int(pil.height * ratio)
                pil = pil.resize((new_w, new_h), PImage.LANCZOS)

                                                     
                if i < len(media_types) and media_types[i] == "video":
                    overlay = PImage.new("RGBA", (new_w, new_h), (0, 0, 0, 0))
                    draw = PIDraw.Draw(overlay)
                                                  
                    cx, cy, r = new_w // 2, new_h // 2, 30
                    draw.ellipse(
                        [cx - r, cy - r, cx + r, cy + r],
                        fill=(0, 0, 0, 160)
                    )
                                   
                    tri_x = cx - 8
                    draw.polygon(
                        [(tri_x, cy - 15), (tri_x, cy + 15), (tri_x + 24, cy)],
                        fill=(255, 255, 255, 220)
                    )
                    pil = PImage.alpha_composite(pil, overlay)

                                 
                mask = PImage.new("L", (new_w, new_h), 0)
                PIDraw.Draw(mask).rounded_rectangle([(0, 0), (new_w, new_h)], radius=18, fill=255)
                rounded = PImage.new("RGBA", (new_w, new_h), (0, 0, 0, 0))
                rounded.paste(pil, mask=mask)

                self._carousel_images.append(ctk.CTkImage(light_image=rounded, dark_image=rounded, size=(new_w, new_h)))
            
            except Exception as e:
                print(f"[DEBUG] carousel frame failed: {e}")

        if not self._carousel_images:
            return

        self._carousel_idx = 0

        self._carousel_frame = ctk.CTkFrame(self.left_col, fg_color="transparent")
        self._carousel_frame.pack(fill="x", pady=10)

                       
        self._carousel_img_label = ctk.CTkLabel(self._carousel_frame, text="")
        self._carousel_img_label.pack()

                                                         
        if len(self._carousel_images) > 1:
            nav = ctk.CTkFrame(self._carousel_frame, fg_color="transparent")
            nav.pack(pady=(8, 4))

            self._prev_btn = ctk.CTkButton(
                nav, text="←", width=36, height=28,
                fg_color="#333", hover_color="#444",
                command=self._carousel_prev
            )
            self._prev_btn.pack(side="left", padx=8)

            self._carousel_counter = ctk.CTkLabel(nav, text="", font=("Calibri", 13))
            self._carousel_counter.pack(side="left", padx=8)

            self._next_btn = ctk.CTkButton(
                nav, text="→", width=36, height=28,
                fg_color="#333", hover_color="#444",
                command=self._carousel_next
            )
            self._next_btn.pack(side="left", padx=8)

                            
            self._dots_frame = ctk.CTkFrame(self._carousel_frame, fg_color="transparent")
            self._dots_frame.pack(pady=(2, 6))
            self._dot_labels = []
            for i in range(len(self._carousel_images)):
                dot = ctk.CTkLabel(self._dots_frame, text="●",
                                   font=("Calibri", 9), text_color="#2D7DBF")
                dot.pack(side="left", padx=2)
                self._dot_labels.append(dot)
        else:
            self._dot_labels = []
            self._carousel_counter = None

        self._carousel_show(0)

    def _carousel_show(self, idx):
        self._carousel_idx = idx
        self._carousel_img_label.configure(image=self._carousel_images[idx])
        total = len(self._carousel_images)
        if self._carousel_counter:
            self._carousel_counter.configure(text=f"{idx + 1} / {total}")
        for i, dot in enumerate(self._dot_labels):
            dot.configure(text_color="#2D7DBF" if i == idx else "#444")
        if hasattr(self, '_prev_btn'):
            self._prev_btn.configure(state="normal" if idx > 0 else "disabled")
            self._next_btn.configure(state="normal" if idx < total - 1 else "disabled")

    def _carousel_prev(self):
        if self._carousel_idx > 0:
            self._carousel_show(self._carousel_idx - 1)

    def _carousel_next(self):
        if self._carousel_idx < len(self._carousel_images) - 1:
            self._carousel_show(self._carousel_idx + 1)

    def update_quality_options(self, value):
        if value == "Audio (MP3)":
            self.quality_combo.configure(values=["Best Available", "320 kbps", "192 kbps"])
            self.quality_combo.set("Best Available")
        else:
            self.quality_combo.configure(values=["Best Available", "1080p", "720p", "480p"])
            self.quality_combo.set("Best Available")
    

    
    def save_thumbnail(self):
        if not self.data or not self.data.get('thumbnail_bytes'): return
        try:
            safe = "".join([c for c in self.data['title'] if c.isalnum() or c in (' ', '-', '_')]).strip()
            path = DOWNLOAD_DIR / f"{safe}_cover.jpg"
            with open(path, "wb") as f:
                f.write(self.data['thumbnail_bytes'])
            self.status_label.configure(text="Cover saved!", text_color="#3B8ED0")
        except Exception as e:
            self.status_label.configure(text="Save failed", text_color="red")

                                                     
    _AUDIO_FMT_MAP = {
        "MP3":             ("mp3",    "0"),
        "FLAC (Lossless)": ("flac",   "0"),
        "M4A":             ("m4a",    "0"),
        "OGG":             ("vorbis", "0"),
        "OPUS":            ("opus",   "0"),
        "WAV (Lossless)":  ("wav",    "0"),
    }

    def _api_submit(self, method, path, body, event_handler):
        """POST to API, get task_id, start polling for events."""
        def _worker():
            try:
                r = requests.request(method, f"{_API_BASE}{path}", json=body, timeout=5)
                if r.status_code != 200:
                    event_handler({"type": "error", "success": False, "message": f"API error {r.status_code}"})
                    return
                task_id = r.json()["task_id"]
                self._poll_task(task_id, event_handler)
            except Exception as e:
                event_handler({"type": "error", "success": False, "message": f"API unreachable: {e}"})
        threading.Thread(target=_worker, daemon=True).start()

    def _poll_task(self, task_id, event_handler, interval=0.3):
        """Poll /task/{id}/events until terminal state."""
        cursor = 0
        while True:
            try:
                r = requests.get(f"{_API_BASE}/task/{task_id}/events", params={"cursor": cursor}, timeout=5)
                if r.status_code != 200:
                    break
                data = r.json()
                for ev in data.get("events", []):
                    event_handler(ev)
                cursor = data.get("cursor", cursor)
                state = data.get("state", "running")
                if state in ("complete", "error", "cancelled"):
                    break
            except Exception:
                break
            _time.sleep(interval)

    def start_download(self):
        self.download_btn.configure(state="disabled")
        self.status_label.configure(text="Initializing...", text_color="white")

        fmt = self.format_seg.get()
        qual = self.quality_combo.get()
        audio_fmt_label = self.audio_fmt_combo.get()
        audio_codec, audio_quality = self._AUDIO_FMT_MAP.get(audio_fmt_label, ("mp3", "320"))

        selected_tracks = None
        if self.is_playlist:
            selected_tracks = [item.track for item in self.track_items if item.selected.get()]
            if not selected_tracks:
                self.status_label.configure(text="No tracks selected", text_color="red")
                self.download_btn.configure(state="normal")
                return

        options = {
            "format": fmt,
            "quality": qual,
            "audio_codec": audio_codec,
            "audio_quality": audio_quality,
        }

        if self.is_playlist:
            total = len(selected_tracks)

            def _on_playlist_event(payload):
                t = payload["type"]
                if t == "batch":
                    prog = payload.get("progress", 0.0)
                    c = payload.get("completed", 0)
                    tot = payload.get("total", total)
                    self.after(0, lambda p=prog: self.progress_bar.set(p))
                    self.after(0, lambda c=c, t=tot: self.status_label.configure(
                        text=f"Progress: {c}/{t}"
                    ))
                elif t == "batch_end":
                    msg = payload.get("message", "Done")
                    ok = payload.get("success", False)
                    color = "#2ECC71" if ok else "#E67E22"
                    self.after(0, lambda m=msg, c=color: self.status_label.configure(text=m, text_color=c))
                    self.after(0, lambda: self.progress_bar.set(1.0))
                    self.after(0, lambda: self.download_btn.configure(state="normal"))

            body = {
                "tracks": [dataclasses.asdict(t) for t in selected_tracks],
                "options": options,
                "playlist_title": self.data.get("title", "Playlist"),
            }
            self._api_submit("POST", "/download/playlist", body, _on_playlist_event)
        else:
            track_obj = self.data.get('_track_obj')
            if track_obj and track_obj.source == "spotify":
                def _on_spotify_event(payload):
                    t = payload["type"]
                    msg = payload.get("message", "")
                    if t == "progress":
                        pct = payload.get("progress", 0.0)
                        self.after(0, lambda p=pct: self.progress_bar.set(p))
                        self.after(0, lambda m=msg: self.status_label.configure(text=m))
                    elif t in ("complete", "error"):
                        ok = payload.get("success", False)
                        color = "#2ECC71" if ok else "red"
                        self.after(0, lambda m=msg, c=color: self.status_label.configure(text=m, text_color=c))
                        self.after(0, lambda: self.download_btn.configure(state="normal"))

                body = {
                    "track": dataclasses.asdict(track_obj),
                    "options": options,
                }
                self._api_submit("POST", "/download/spotify", body, _on_spotify_event)
            else:
                def _on_generic_event(payload):
                    t = payload["type"]
                    msg = payload.get("message", "")
                    if t == "progress":
                        self.after(0, lambda m=msg: self.status_label.configure(text=m))
                    elif t in ("complete", "error"):
                        ok = payload.get("success", False)
                        color = "green" if ok else "red"
                        self.after(0, lambda m=msg, c=color: self.status_label.configure(text=m, text_color=c))
                        self.after(0, lambda: self.download_btn.configure(state="normal"))

                body = {
                    "url": self.data.get("url", ""),
                    "title": self.data.get("title", "audio"),
                    "options": options,
                }
                self._api_submit("POST", "/download/youtube", body, _on_generic_event)


if __name__ == "__main__":
    app = Ember()
    app.mainloop()
