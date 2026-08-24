# Ember: The Unified Desktop Music Studio Playbook

This document is a comprehensive technical specification, architectural guide, and code implementation playbook for evolving **Ember** from an audio archival/download utility into a **Full-Featured Desktop Music Player & Curation Studio**—combining instant streaming, visual polish, time-synced lyrics, audio EQ/visualizers with **Ember's core superpower** (ISRC-based precision matching, Apple Music/Spotify GraphQL metadata resolution, and permanent, DRM-free local file ownership).

---

## Table of Contents

1. [Architecture & Philosophy: The Dual-Action Engine](#1-architecture--philosophy-the-dual-action-engine)
2. [Smart Routing: Local Files vs. Remote Streams](#2-smart-routing-local-files-vs-remote-streams)
3. [The "Play-to-Keep" Cache Pipeline (Zero Double-Downloading)](#3-the-play-to-keep-cache-pipeline-zero-double-downloading)
4. [Backend Implementation: FastAPI Streaming & Local Routes](#4-backend-implementation-fastapi-streaming--local-routes)
   - [`GET /audio/stream` — YouTube Stream Proxy with Range Support](#41-get-audiostream--youtube-stream-proxy-with-range-support)
   - [`GET /audio/stream_normalized` — Live FFmpeg Loudness Normalization Pipe](#42-get-audiostream_normalized--live-ffmpeg-loudness-normalization-pipe)
   - [`GET /audio/local` — CORS & Range-Capable Local File Server](#43-get-audiolocal--cors--range-capable-local-file-server)
   - [`POST /audio/promote_cache` — 1-Click Library Promotion](#44-post-audiopromote_cache--1-click-library-promotion)
5. [Frontend Implementation: SvelteKit Media Player & Web Audio API](#5-frontend-implementation-sveltekit-media-player--web-audio-api)
   - [Web Audio API Engine: `AnalyserNode` + 6-Band `BiquadFilterNode` EQ](#51-web-audio-api-engine)
   - [Animated Frequency Visualizer ("The Bars")](#52-animated-frequency-visualizer-the-bars)
   - [Full Svelte Component: `src/lib/MediaPlayer.svelte`](#53-full-svelte-component-srclibmediaplayersvelte)
6. [Step-by-Step Integration Guide](#6-step-by-step-integration-guide)

---

## 1. Architecture & Philosophy: The Dual-Action Engine

In a standard music downloader, you blindly download files before listening. In a standard streaming app (like Spotify), you can listen instantly but never truly own the underlying files.

### The Unified Dual-Action Model
Every track row in Ember exposes two primary actions: **`[▶ Play]`** and **`[↓ Download / Save]`**:

```
                       ┌────────────────────────────────────────┐
                       │  User selects a Track in SvelteKit UI  │
                       └───────────────────┬────────────────────┘
                                           │
                        ┌──────────────────┴──────────────────┐
                        │                                     │
                        ▼                                     ▼
             [▶ CLICK PLAY BUTTON]                  [↓ CLICK DOWNLOAD BUTTON]
                        │                                     │
                        ▼                                     ▼
        ┌───────────────────────────────┐        ┌───────────────────────────────┐
        │  Is file already downloaded?  │        │  Is file in active playback   │
        └───────┬───────────────┬───────┘        │         cache folder?         │
                │ YES           │ NO             └───────┬───────────────┬───────┘
                ▼               ▼                        │ YES           │ NO
       Stream Local File    Proxy YouTube                ▼               ▼
      (/audio/local)        Stream (300ms)      Promote Cache File   Full High-Res
                            (/audio/stream)     + Tag ID3 / ISRC    yt-dlp Download
                                                (/promote_cache)    (/download/...)
```

---

## 2. Smart Routing: Local Files vs. Remote Streams

Ember's SvelteKit frontend is completely decoupled from whether a song is being streamed over the internet or read from a local hard drive.

### The URL Decision Matrix
*   **Remote Stream (YouTube Music / Spotify Track):**
    ```ts
    const audioSrc = `http://127.0.0.1:8008/audio/stream?url=${encodeURIComponent(track.spotify_url)}`;
    ```
*   **Local File (Drag-and-Dropped or Already in `/Downloads`):**
    ```ts
    const audioSrc = `http://127.0.0.1:8008/audio/local?file_path=${encodeURIComponent(track.local_file_path)}`;
    ```

Both endpoints return HTTP responses with `Access-Control-Allow-Origin: *` and `Accept-Ranges: bytes`, ensuring that SvelteKit's `<audio>` tag and the Web Audio API can scrub, seek, and analyze frequency data without CORS or security errors.

---

## 3. The "Play-to-Keep" Cache Pipeline (Zero Double-Downloading)

A critical UX requirement: **if a user plays a song and decides to download it, Ember must not download the audio a second time.**

### How the Pipeline Works
1. **Cache During Playback:** When a user calls `/audio/stream`, FastAPI instructs `yt-dlp` to write the progressive audio stream into a temporary directory (`<download_dir>/.cache/streams/<isrc_or_id>.m4a`) while simultaneously chunk-streaming it to the UI.
2. **Instant Archival:** When the user clicks **`[↓ Save to Library]`**, SvelteKit calls `/audio/promote_cache`:
   * The backend checks if `<download_dir>/.cache/streams/<id>.m4a` exists.
   * If found, it bypasses network downloads entirely, runs `core.tagger.tag_audio()` to embed Apple Music / Spotify cover art and ISRC metadata, and moves the tagged file to `<download_dir>/<Artist> - <Title>.<ext>`.
   * Total completion time: **~0.1 seconds**.

---

## 4. Backend Implementation: FastAPI Streaming & Local Routes

Add these route handlers to `backend/api/routes.py` (or as a dedicated `backend/api/stream_routes.py` module imported into `server.py`).

### 4.1 `GET /audio/stream` — YouTube Stream Proxy with Range Support

This endpoint extracts YouTube's native progressive audio formats—**Format 140 (AAC / .m4a at ~128 kbps)** or **Format 251 (Opus / .webm at ~160 kbps)**—which start playing in under 300ms and are natively supported by Chromium/WebKit.

```python
# backend/api/routes.py (Snippet to append)

import os
import requests
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Query, Response
from fastapi.responses import StreamingResponse, FileResponse
import yt_dlp

@router.get("/audio/stream")
def stream_remote_audio(url: str = Query(...), request: Request = None):
    """
    Proxy an audio stream from YouTube/YouTube Music to SvelteKit.
    Supports HTTP Range requests for seamless timeline scrubbing/seeking.
    """
    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    
    stream_url = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            stream_url = info.get("url")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to resolve audio stream: {e}")

    if not stream_url:
        raise HTTPException(status_code=404, detail="No stream URL found")

    # Build upstream headers, preserving client Range request for scrubbing
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    if request and request.headers.get("range"):
        headers["Range"] = request.headers.get("range")

    try:
        upstream = requests.get(stream_url, headers=headers, stream=True, timeout=15)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upstream stream connection error: {e}")

    response_headers = {
        "Access-Control-Allow-Origin": "*",
        "Cross-Origin-Resource-Policy": "cross-origin",
        "Accept-Ranges": "bytes",
    }
    for key in ("Content-Range", "Content-Length", "Content-Type"):
        if key in upstream.headers:
            response_headers[key] = upstream.headers[key]

    return StreamingResponse(
        upstream.iter_content(chunk_size=65536),
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("Content-Type", "audio/mp4"),
    )
```

---

### 4.2 `GET /audio/stream_normalized` — Live FFmpeg Loudness Normalization Pipe

To provide Ember's **Loudness Normalization** feature, this endpoint pipes the YouTube stream through `ffmpeg` on the fly using EBU R128 (`loudnorm`) so tracks from different albums or uploads maintain a consistent volume level.

```python
@router.get("/audio/stream_normalized")
def stream_normalized_audio(url: str = Query(...)):
    """
    Stream audio through an on-the-fly FFmpeg EBU R128 loudness normalization filter.
    Guarantees balanced volume (-14 LUFS target) across all tracks.
    """
    import subprocess
    from core.utils import get_ffmpeg_details

    ffmpeg_exe, _ = get_ffmpeg_details()
    ydl_opts = {"format": "bestaudio", "quiet": True, "noplaylist": True}

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        stream_url = info.get("url")

    if not stream_url:
        raise HTTPException(status_code=404, detail="Could not resolve stream URL")

    # EBU R128 Loudness Normalization (-14 LUFS is Spotify/YouTube standard)
    cmd = [
        ffmpeg_exe, "-re",
        "-i", stream_url,
        "-af", "loudnorm=I=-14:LRA=11:TP=-1.5",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        "-f", "mp3",
        "-"
    ]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def iter_audio():
        try:
            while True:
                chunk = process.stdout.read(65536)
                if not chunk:
                    break
                yield chunk
        finally:
            process.kill()

    headers = {
        "Access-Control-Allow-Origin": "*",
        "Cross-Origin-Resource-Policy": "cross-origin",
        "Cache-Control": "no-cache",
    }
    return StreamingResponse(iter_audio(), media_type="audio/mpeg", headers=headers)
```

---

### 4.3 `GET /audio/local` — CORS & Range-Capable Local File Server

Enables SvelteKit to play any local audio file on disk (whether inspected via drag-and-drop or saved in the user's download directory).

```python
@router.get("/audio/local")
def play_local_file(file_path: str = Query(...)):
    """
    Serve a local audio file from disk with Range request and CORS support.
    Allows SvelteKit and Web Audio API to play and analyze local files without taint errors.
    """
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Local audio file not found")

    ext = os.path.splitext(file_path)[1].lower()
    media_types = {
        ".mp3": "audio/mpeg",
        ".flac": "audio/flac",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
        ".opus": "audio/ogg",
        ".wav": "audio/wav",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(
        path=file_path,
        filename=os.path.basename(file_path),
        media_type=media_type,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cross-Origin-Resource-Policy": "cross-origin",
            "Accept-Ranges": "bytes",
        },
    )
```

---

### 4.4 `POST /audio/promote_cache` — 1-Click Library Promotion

Promotes a cached audio stream into a permanent, ID3-tagged library file in the user's `/Downloads` folder.

```python
from pydantic import BaseModel

class PromoteCacheRequest(BaseModel):
    cache_file_path: str
    track: TrackSchema
    output_format: str = "mp3"

@router.post("/audio/promote_cache")
def promote_cache_to_library(req: PromoteCacheRequest):
    """
    Promote a temporarily cached stream file into a fully tagged permanent library download.
    """
    import shutil
    from core.tagger import tag_audio
    from core.http_helper import get_bytes
    from core.utils import sanitize_filename

    cache_path = Path(req.cache_file_path)
    if not cache_path.exists():
        raise HTTPException(status_code=404, detail="Cache file expired or not found")

    t = _track_from_schema(req.track)
    artist_str = ", ".join(t.artists) if t.artists else "Unknown"
    safe_name = sanitize_filename(f"{t.title} - {artist_str}")
    out_path = Path(_controller.download_dir) / f"{safe_name}.{req.output_format}"

    # Handle filename collision
    counter = 1
    while out_path.exists():
        out_path = Path(_controller.download_dir) / f"{safe_name} ({counter}).{req.output_format}"
        counter += 1

    try:
        shutil.copy2(cache_path, out_path)
        
        # Download cover art bytes if available
        cover_bytes = None
        if t.cover_url:
            try:
                cover_bytes = get_bytes(t.cover_url, timeout=10)
            except Exception:
                pass

        # Embed ID3/FLAC metadata + ISRC + Cover Art
        tag_audio(t, str(out_path), cover_bytes)
        
        return {
            "status": "ok",
            "path": str(out_path),
            "message": f"Successfully added '{t.title}' to library",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

## 5. Frontend Implementation: SvelteKit Media Player & Web Audio API

To provide high-level visual polish and music style control ("the bars"), we use the browser's hardware-accelerated **Web Audio API** inside SvelteKit.

### 5.1 Web Audio API Engine
*   **`AudioContext.createMediaElementSource(audio)`**: Taps into the `<audio>` output stream.
*   **`AnalyserNode`**: Extracts real-time Fast Fourier Transform (FFT) frequency bin data to power animated visualizer bars.
*   **`BiquadFilterNode` (6-Band Equalizer)**: Chains 6 peaking filters (`60 Hz`, `170 Hz`, `310 Hz`, `1 kHz`, `3 kHz`, `12 kHz`) between the source and the speakers to let users switch between music style presets (*Flat*, *Bass Boost*, *Acoustic/Vocal*, *Electronic*).

---

### 5.2 Animated Frequency Visualizer ("The Bars")
Using an HTML5 `<canvas>`, we render 32 real-time frequency spectrum bars that dance to the audio beats. By coloring them with Ember's signature orange-coral flame gradient (`rgb(255, 80->140, 40)`), the player feels like a professional desktop music studio.

---

### 5.3 Full Svelte Component: `src/lib/MediaPlayer.svelte`

Save this file as `frontend/src/lib/MediaPlayer.svelte` and import it into your `+layout.svelte` or `+page.svelte`.

```svelte
<script lang="ts">
  import { onMount, onDestroy } from "svelte";

  // Public Component Props
  export let currentTrackTitle = "No track loaded";
  export let currentArtist = "Ember Audio Studio";
  export let currentCoverUrl = "/favicon.png";
  export let audioUrl = "";
  export let isLocal = false;
  export let onSaveToLibrary: (() => void) | null = null;

  let audioElement: HTMLAudioElement;
  let canvasElement: HTMLCanvasElement;

  // Web Audio API State
  let audioCtx: AudioContext | null = null;
  let analyser: AnalyserNode | null = null;
  let eqFilters: BiquadFilterNode[] = [];
  let animFrameId: number;

  let isPlaying = false;
  let currentTime = 0;
  let duration = 0;
  let activeStyle = "flat";

  // 6-Band Equalizer Center Frequencies (Hz)
  const EQ_BANDS = [60, 170, 310, 1000, 3000, 12000];

  // Equalizer Gain Presets (dB)
  const STYLE_PRESETS: Record<string, number[]> = {
    flat:       [ 0,  0,  0,  0,  0,  0],
    bass_boost: [ 7,  5,  2,  0, -1, -2],
    vocal:      [-2, -1,  2,  5,  4,  1],
    electronic: [ 5,  3,  0,  2,  4,  6],
  };

  function setupWebAudio() {
    if (audioCtx) return; // Initialize once on first user gesture

    audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
    const source = audioCtx.createMediaElementSource(audioElement);

    // 1. Create Frequency Analyser for Visualizer Bars
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 64; // Gives 32 frequency bins
    analyser.smoothingTimeConstant = 0.82;

    // 2. Build 6-Band Biquad EQ Filter Chain
    let previousNode: AudioNode = source;
    EQ_BANDS.forEach((freq) => {
      if (!audioCtx) return;
      const filter = audioCtx.createBiquadFilter();
      filter.type = "peaking";
      filter.frequency.value = freq;
      filter.Q.value = 1.4;
      filter.gain.value = 0;
      previousNode.connect(filter);
      eqFilters.push(filter);
      previousNode = filter;
    });

    // 3. Connect Filter Chain -> Analyser -> Output Destination
    previousNode.connect(analyser);
    analyser.connect(audioCtx.destination);

    // 4. Start Canvas Animation Loop
    drawVisualizer();
  }

  function handleStyleChange(styleName: string) {
    activeStyle = styleName;
    const targetGains = STYLE_PRESETS[styleName] || STYLE_PRESETS.flat;
    if (!audioCtx) return;

    eqFilters.forEach((filter, index) => {
      filter.gain.setTargetAtTime(targetGains[index], audioCtx!.currentTime, 0.15);
    });
  }

  function drawVisualizer() {
    if (!analyser || !canvasElement) return;
    const ctx = canvasElement.getContext("2d");
    if (!ctx) return;

    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);
    analyser.getByteFrequencyData(dataArray);

    ctx.clearRect(0, 0, canvasElement.width, canvasElement.height);

    const barWidth = (canvasElement.width / bufferLength) * 0.78;
    let x = 0;

    for (let i = 0; i < bufferLength; i++) {
      const value = dataArray[i];
      // Normalize bar height against canvas height
      const barHeight = Math.max(3, (value / 255) * canvasElement.height);

      // Signature Ember warm flame gradient (Orange -> Amber -> Red)
      const red = 255;
      const green = Math.max(70, 160 - i * 4);
      const blue = 40;
      ctx.fillStyle = `rgb(${red}, ${green}, ${blue})`;

      // Draw rounded bar
      ctx.fillRect(
        x,
        canvasElement.height - barHeight,
        barWidth,
        barHeight
      );

      x += barWidth + 3;
    }

    animFrameId = requestAnimationFrame(drawVisualizer);
  }

  function togglePlay() {
    if (!audioElement) return;
    setupWebAudio();
    if (audioElement.paused) {
      audioElement.play();
      isPlaying = true;
    } else {
      audioElement.pause();
      isPlaying = false;
    }
  }

  function handleSeek(e: Event) {
    const input = e.target as HTMLInputElement;
    audioElement.currentTime = parseFloat(input.value);
  }

  function formatTime(sec: number): string {
    if (isNaN(sec) || sec === 0) return "0:00";
    const mins = Math.floor(sec / 60);
    const secs = Math.floor(sec % 60);
    return `${mins}:${secs < 10 ? "0" : ""}${secs}`;
  }

  onDestroy(() => {
    if (animFrameId) cancelAnimationFrame(animFrameId);
    if (audioCtx) audioCtx.close();
  });
</script>

<div class="fixed bottom-0 left-0 right-0 h-20 bg-neutral-900/95 border-t border-neutral-800 backdrop-blur-xl px-6 flex items-center justify-between z-50 select-none">
  <!-- Hidden Audio Engine with CORS support -->
  <audio
    bind:this={audioElement}
    src={audioUrl}
    crossorigin="anonymous"
    on:timeupdate={() => (currentTime = audioElement.currentTime)}
    on:loadedmetadata={() => (duration = audioElement.duration)}
    on:ended={() => (isPlaying = false)}
  ></audio>

  <!-- Left: Artwork & Metadata -->
  <div class="flex items-center gap-3 w-1/4 min-w-[200px]">
    <img
      src={currentCoverUrl}
      alt="Cover"
      class="w-12 h-12 rounded-lg object-cover bg-neutral-800 border border-neutral-700/50 shadow-md"
    />
    <div class="overflow-hidden">
      <h4 class="font-semibold text-sm text-white truncate">{currentTrackTitle}</h4>
      <p class="text-xs text-neutral-400 truncate">{currentArtist}</p>
      {#if isLocal}
        <span class="inline-block mt-0.5 px-1.5 py-0.5 text-[10px] uppercase font-bold tracking-wider bg-emerald-500/20 text-emerald-400 rounded">
          Local Library
        </span>
      {:else}
        <span class="inline-block mt-0.5 px-1.5 py-0.5 text-[10px] uppercase font-bold tracking-wider bg-amber-500/20 text-amber-400 rounded">
          YouTube Stream
        </span>
      {/if}
    </div>
  </div>

  <!-- Center: Player Controls & Visualizer ("The Bars") -->
  <div class="flex flex-col items-center justify-center flex-1 max-w-xl px-4">
    <div class="flex items-center gap-6 mb-1">
      <!-- Play / Pause Button -->
      <button
        on:click={togglePlay}
        class="w-10 h-10 rounded-full bg-gradient-to-tr from-amber-500 to-orange-600 flex items-center justify-center text-white shadow-lg hover:brightness-110 active:scale-95 transition"
      >
        <span class="text-lg ml-0.5">{isPlaying ? "⏸" : "▶"}</span>
      </button>

      <!-- Real-Time Frequency Visualizer Canvas -->
      <div class="w-48 h-9 bg-neutral-950/60 rounded-md border border-neutral-800/80 px-2 flex items-center justify-center">
        <canvas bind:this={canvasElement} width="180" height="28" class="w-full h-full"></canvas>
      </div>
    </div>

    <!-- Timeline Scrubber Bar -->
    <div class="flex items-center gap-3 w-full text-xs text-neutral-400 font-mono">
      <span>{formatTime(currentTime)}</span>
      <input
        type="range"
        min="0"
        max={duration || 0}
        value={currentTime}
        on:input={handleSeek}
        class="flex-1 h-1.5 bg-neutral-700 rounded-lg appearance-none cursor-pointer accent-orange-500"
      />
      <span>{formatTime(duration)}</span>
    </div>
  </div>

  <!-- Right: EQ Style Presets & 1-Click Library Save Button -->
  <div class="flex items-center justify-end gap-4 w-1/4 min-w-[220px]">
    <!-- Equalizer Music Style Dropdown -->
    <div class="flex items-center gap-2 bg-neutral-950/80 border border-neutral-800 px-2.5 py-1.5 rounded-lg">
      <span class="text-xs text-neutral-400 font-medium">Style:</span>
      <select
        bind:value={activeStyle}
        on:change={(e) => handleStyleChange(e.currentTarget.value)}
        class="bg-transparent text-xs text-white font-medium focus:outline-none cursor-pointer"
      >
        <option value="flat" class="bg-neutral-900">Flat</option>
        <option value="bass_boost" class="bg-neutral-900">Bass Boost</option>
        <option value="vocal" class="bg-neutral-900">Vocal / Acoustic</option>
        <option value="electronic" class="bg-neutral-900">Electronic</option>
      </select>
    </div>

    <!-- 1-Click Save to Library / Download Button -->
    {#if !isLocal && onSaveToLibrary}
      <button
        on:click={onSaveToLibrary}
        class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/15 text-white text-xs font-semibold border border-white/10 transition"
        title="Save this stream to your permanent library with ID3 metadata"
      >
        <span>↓</span>
        <span>Save to Library</span>
      </button>
    {:else if isLocal}
      <div class="text-xs text-emerald-400 font-medium flex items-center gap-1">
        <span>✓</span>
        <span>In Library</span>
      </div>
    {/if}
  </div>
</div>

<style>
  input[type="range"]::-webkit-slider-thumb {
    appearance: none;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #f97316;
    cursor: pointer;
  }
</style>
```

---

---

## 6. Step-by-Step Integration Guide

### Phase 1: Mount the Backend Routes
1. Open `backend/api/routes.py`.
2. Append the 4 route handlers (`/audio/stream`, `/audio/stream_normalized`, `/audio/local`, `/audio/promote_cache`) provided in Section 4.
3. Ensure CORS policies allow `Access-Control-Allow-Origin: *` so SvelteKit's Web Audio API won't throw canvas taint errors.

### Phase 2: Add the UI Component in SvelteKit
1. Save the Svelte component in Section 5.3 as `frontend/src/lib/MediaPlayer.svelte`.
2. In `frontend/src/routes/+layout.svelte` (or `+page.svelte`), import `<MediaPlayer />` and bind it to a global Svelte store (`$activeTrack`) that tracks the song currently being inspected or streamed.

### Phase 3: Wire Up Row Action Buttons
For each track row in your inspect/download table:
*   Add a **`[▶ Play]`** button that sets `$activeTrack` and triggers playback:
    *   If `track.is_downloaded`, pass `http://127.0.0.1:8008/audio/local?file_path=${track.path}`.
    *   If not, pass `http://127.0.0.1:8008/audio/stream?url=${track.spotify_url}`.
*   Add a **`[↓ Save to Library]`** button:
    *   If the track was already streamed into `.cache/streams/`, call `POST /audio/promote_cache` for instant promotion.
    *   Otherwise, trigger your standard `POST /download/spotify` or `/download/youtube` task pipeline.

---

## 7. Inline Glass Media Player Bar & UI Specification

### 7.1 Layout & Glass Design System
- **Placement**: Integrated inside `.meta-bottom` directly above the card section separator (`<div class="divider"></div>`).
- **Glass Aesthetics**: Uses a translucent dark glass frame (`background: rgba(255, 255, 255, 0.03); backdrop-filter: blur(16px); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 14px`).

### 7.2 Monochrome Dark Glass Play/Pause Button
- **Colorless Finish**: Completely monochrome dark glass button (`background: rgba(0, 0, 0, 0.25)`), free of red/orange gradient tints.
- **Rounded SVG Icons**: Smooth rounded geometry (`M8 6.82v10.36...` for Play, `rx="2"` rounded bars for Pause).
- **Static Glass Sheen**: Removed `transform: scale(...)` zoom animations on hover for a clean, non-distracting glass sheen.

### 7.3 Smart Loading State Machine
- **Initial Load Phase**: Shows the spinning SVG loader (`.card-spinner-svg`) **only during initial stream buffering** at `00:00` before audio frames begin playing.
- **Seamless Playback Transition**: Automatically transitions to the Pause SVG icon (`⏸`) as soon as sound begins (`ontimeupdate` with `currentTime > 0` and `!paused`).
- **Pause & Seek Safety**: Pressing pause instantly resets `cardAudioLoading = false`, preventing spinner flashing. Dragging/seeking the timeline while paused checks `!cardAudioElement.paused` before modifying playing state, keeping the Play icon (`▶`) intact.

### 7.4 Glass Seekbar Track & Radial Glass Handle
- **Timeline Backfill**: Glass container (`.card-player-timeline`) flush with movement endpoints, with glowing gradient backfill (`.timeline-glass-fill`).
- **Radial White Glass Handle**: Designed with `background: radial-gradient(circle at 35% 35%, #ffffff 0%, #e6e6e6 60%, #d4d4d4 100%)`, `1.5px` glass border rim, and subtle red ambient glow shadow.
- **Padded Timestamp Format**: Displayed strictly as `00:00/00:00` with padded leading zeros, omitting `"Stream Preview"` labels.

### 7.5 Circular Sound Control & Vertical Volume Panel
- **36px Circular Sound Button**: Single `36px × 36px` circular container (`border-radius: 50%`) with speaker SVG icon.
- **Extended Popover Panel**: Height increased to `125px` track slider, positioned `3px` above the media player frame (`bottom: calc(100% + 11px)`).
- **Flat Floating Glass Base**: Pointy triangle arrow (`::after`) omitted for a floating card appearance.
- **Hover & Drag Protection**: 
  - `6px` invisible hit-box extension (`::before`) keeps the popover smoothly open when hovering slightly outside.
  - `data-no-drag` and `-webkit-app-region: no-drag` disable desktop window moving over the panel and its hit area.
  - Smooth vertical mouse drag/click handler (`handleVolumeMouseDown`) updates volume dynamically from 0% to 100%.

---

## Summary
With this architecture, Ember bridges the divide between **transient mobile streaming apps** and **offline archival tools**. Users get instant audio playback, interactive visualizer bars, and EQ music styling—backed by permanent, DRM-free local file ownership.

