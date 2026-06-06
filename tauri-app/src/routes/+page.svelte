<script lang="ts">
  import { onMount } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';

  // ── State ──────────────────────────────────────────────────────────────────
  let url = "";
  let statusText = "Ready";
  let progress = 0.0;
  let isDownloading = false;
  let isWarmup = false;
  let isFetching = false;          // loading track info
  let fetchError = "";

  $: isBusy = isDownloading || isWarmup || isFetching;

  let taskId: string | null = null;
  let pollInterval: number | null = null;

  const AUDIO_FMT_MAP: Record<string, [string, string]> = {
    "MP3":             ["mp3",    "0"],
    "FLAC (Lossless)": ["flac",   "0"],
    "M4A":             ["m4a",    "0"],
    "OGG":             ["vorbis", "0"],
    "OPUS":            ["opus",   "0"],
    "WAV (Lossless)":  ["wav",    "0"],
  };
  let selectedFormat = "MP3";

  let selectedVideoFormat = "Audio (MP3)";  // "Audio (MP3)" | "Video (MP4)"
  let selectedQuality = "Best Available";
  const QUALITY_OPTIONS: Record<string, string[]> = {
    "Audio (MP3)": ["Best Available", "320 kbps", "192 kbps"],
    "Video (MP4)": ["Best Available", "1080p", "720p", "480p"],
  };

  function onVideoFormatChange() {
    selectedQuality = "Best Available";
  }

  let downloadSuccess: boolean | null = null;  // null=idle, true=success, false=error
  let downloadDoneMessage = "";

  type TrackInfo = {
    title: string;
    artists: string[];
    album: string | null;
    duration: number;
    track_number: number | null;
    total_tracks: number | null;
    year: string | null;
    genre: string | null;
    cover_url: string | null;
    spotify_url: string | null;
    isrc: string | null;
    source: string;
    media_type: string;
  };

  let track: TrackInfo | null = null;
  let transitioning = false;

  // ── Playlist / album state ────────────────────────────────────────────────
  let isPlaylist = false;
  let playlistTitle = "";
  let playlistOwner = "";
  let playlistCover: string | null = null;
  let playlistType = "playlist";
  let playlistTracks: TrackInfo[] = [];
  let selectedIndices: Set<number> = new Set();
  let batchProgress = { completed: 0, total: 0, succeeded: 0, failed: 0 };

  $: showDetails = track !== null || isPlaylist;
  $: allSelected = selectedIndices.size === playlistTracks.length && playlistTracks.length > 0;

  let isExpanding = false;

  const API_BASE = "http://127.0.0.1:8008";

  // ── Helpers ────────────────────────────────────────────────────────────────
  function formatDuration(secs: number): string {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  function getErrorMessage(err: unknown): string {
    if (err instanceof Error) return err.message;
    return String(err);
  }

  function toggleTrack(idx: number) {
    if (selectedIndices.has(idx)) selectedIndices.delete(idx);
    else selectedIndices.add(idx);
    selectedIndices = new Set(selectedIndices);
  }

  function toggleAll() {
    if (allSelected) selectedIndices = new Set();
    else selectedIndices = new Set(playlistTracks.map((_: TrackInfo, i: number) => i));
  }

  // ── Warmup ─────────────────────────────────────────────────────────────────
  onMount(() => {
    isWarmup = true;
    statusText = "System active...";
    
    // Attempt to start the backend via Tauri
    // Since this runs after onMount, the UI is already fully rendered!
    if (window.__TAURI_INTERNALS__) {
        invoke('init_backend').catch(console.error);
    }
    
    // Poll the backend until it's responsive
    function attemptWarmup() {
      fetch(`${API_BASE}/warmup`, { method: "POST" })
        .then(res => {
          if (!res.ok) throw new Error("not ready");
          isWarmup = false; 
          if (!isDownloading) statusText = "Ready";
        })
        .catch(() => {
          setTimeout(attemptWarmup, 1000);
        });
    }
    attemptWarmup();
  });

  // ── Fetch track info (inspect step) ───────────────────────────────────────
  async function inspectUrl() {
    if (!url.trim() || isBusy) return;
    track = null;
    isPlaylist = false;
    playlistTracks = [];
    selectedIndices = new Set();
    batchProgress = { completed: 0, total: 0, succeeded: 0, failed: 0 };
    downloadSuccess = null;
    fetchError = "";
    isFetching = true;
    statusText = "Inspecting...";

    try {
      const res = await fetch(`${API_BASE}/track/info?url=${encodeURIComponent(url.trim())}`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `API error ${res.status}`);
      }
      const data = await res.json();

      transitioning = true;
      await new Promise(r => setTimeout(r, 300));

      if (data.type === "track" && data.track) {
        track = data.track;
        isPlaylist = false;
      } else {
        isPlaylist = true;
        playlistType = data.type;
        playlistTitle = data.title || "Playlist";
        playlistOwner = data.owner || "Spotify";
        playlistCover = data.cover_url;
        playlistTracks = data.tracks || [];
        selectedIndices = new Set(playlistTracks.map((_: TrackInfo, i: number) => i));
        
        enrichPlaylistTracks();
      }

      isExpanding = true;
      await new Promise(r => setTimeout(r, 100));
      transitioning = false;
      statusText = "Ready";
    } catch (err) {
      fetchError = getErrorMessage(err);
      statusText = "Ready";
    } finally {
      isFetching = false;
    }
  }
  
  // Progressively fetch cover art and metadata for playlist items in the background
  async function enrichPlaylistTracks() {
    for (let i = 0; i < playlistTracks.length; i++) {
      if (playlistTracks[i].isrc) continue;
      if (!playlistTracks[i].spotify_url?.includes("/track/")) continue;
      
      try {
        const res = await fetch(`${API_BASE}/track/enrich`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(playlistTracks[i])
        });
        if (res.ok) {
          playlistTracks[i] = await res.json();
          playlistTracks = [...playlistTracks]; // Reassign array to trigger Svelte reactivity
        }
      } catch (err) {
        console.error("Enrich failed:", err);
      }
    }
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') inspectUrl();
  }

  async function clearTrack() {
    transitioning = true;
    await new Promise(r => setTimeout(r, 280));
    track = null;
    isPlaylist = false;
    playlistTracks = [];
    selectedIndices = new Set();
    isExpanding = false;
    transitioning = false;
    fetchError = "";
    statusText = "Ready";
    progress = 0;
    batchProgress = { completed: 0, total: 0, succeeded: 0, failed: 0 };
    downloadSuccess = null;
    url = "";
  }

  // ── Save cover art ─────────────────────────────────────────────────────────
  let isSavingCover = false;
  let coverSaved = false;

  async function saveCover() {
    const coverUrl = track?.cover_url || playlistCover;
    const coverTitle = track?.title || playlistTitle;
    if (!coverUrl || isSavingCover) return;
    isSavingCover = true;
    coverSaved = false;

    try {
      const res = await fetch(`${API_BASE}/download/cover?url=${encodeURIComponent(coverUrl)}&title=${encodeURIComponent(coverTitle)}`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("Failed to save cover on backend");
      coverSaved = true;
      setTimeout(() => { coverSaved = false; }, 2500);
    } catch (err) {
      console.error("Save cover error:", err);
    } finally {
      isSavingCover = false;
    }
  }

  // ── Single track download ─────────────────────────────────────────────────
  async function startDownload() {
    if (!track || isDownloading) return;
    isDownloading = true;
    downloadSuccess = null;
    statusText = "Starting download...";
    progress = 0;

    try {
      const isSpotify = track.source === "spotify";
      let endpoint: string;
      let body: Record<string, unknown>;

      if (isSpotify) {
        endpoint = "/download/spotify";
        const [codec, quality] = AUDIO_FMT_MAP[selectedFormat] ?? ["mp3", "0"];
        body = {
          track: track,
          options: { format: `Audio (${selectedFormat})`, quality: "Best Available", audio_codec: codec, audio_quality: quality },
        };
      } else {
        endpoint = "/download/youtube";
        const dlOptions = selectedVideoFormat === "Video (MP4)"
          ? { format: "Video (MP4)", quality: selectedQuality, audio_codec: "mp3", audio_quality: "0" }
          : { format: "Audio (MP3)", quality: selectedQuality, audio_codec: "mp3", audio_quality: "0" };
        body = { url: track.spotify_url ?? url, title: track.title, options: dlOptions };
      }

      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!res.ok) throw new Error(`API error: ${res.status}`);

      const data = await res.json();
      taskId = data.task_id;
      if (taskId) startPolling(taskId);
    } catch (err) {
      statusText = `Error: ${getErrorMessage(err)}`;
      downloadSuccess = false;
      isDownloading = false;
    }
  }

  function defaultOptions() {
    return { format: "Audio (MP3)", quality: "Best Available", audio_codec: "mp3", audio_quality: "0" };
  }

  // ── Batch download (playlist/album) ────────────────────────────────────────
  async function startBatchDownload() {
    if (isDownloading || selectedIndices.size === 0) return;
    isDownloading = true;
    statusText = "Starting batch download...";
    progress = 0;
    batchProgress = { completed: 0, total: selectedIndices.size, succeeded: 0, failed: 0 };

    try {
      const [codec, quality] = AUDIO_FMT_MAP[selectedFormat] ?? ["mp3", "0"];
      const selectedTracks = [...selectedIndices].sort((a, b) => a - b).map(i => playlistTracks[i]);

      const body = {
        tracks: selectedTracks,
        options: { format: `Audio (${selectedFormat})`, quality: "Best Available", audio_codec: codec, audio_quality: quality },
        playlist_title: playlistTitle,
      };

      const res = await fetch(`${API_BASE}/download/playlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!res.ok) throw new Error(`API error: ${res.status}`);
      const data = await res.json();
      taskId = data.task_id;
      if (taskId) startPolling(taskId);
    } catch (err) {
      statusText = `Error: ${getErrorMessage(err)}`;
      isDownloading = false;
    }
  }

  // ── Polling ────────────────────────────────────────────────────────────────
  function startPolling(id: string) {
    let cursor = 0;
    let staleTicks = 0;

    async function poll() {
      try {
        const res = await fetch(`${API_BASE}/task/${id}/events?cursor=${cursor}`);
        if (!res.ok) { stopPolling(); return; }

        const data = await res.json();
        const newCursor = data.cursor ?? cursor;
        if (newCursor > cursor) {
          staleTicks = 0;
          cursor = newCursor;
          for (const ev of data.events) handleEvent(ev);
        } else {
          staleTicks++;
        }

        if (["complete", "error", "cancelled"].includes(data.state)) {
          stopPolling();
          isDownloading = false;
          return;
        }

        pollInterval = window.setTimeout(poll, staleTicks > 5 ? 1000 : 300);
      } catch {
        pollInterval = window.setTimeout(poll, 1000);
      }
    }
    poll();
  }

  function stopPolling() {
    if (pollInterval !== null) { clearTimeout(pollInterval); pollInterval = null; }
  }

  function handleEvent(payload: { type: string; message?: string; progress?: number; completed?: number; total?: number; succeeded?: number; failed?: number; success?: boolean }) {
    const t = payload.type;
    const msg = payload.message || "";
    if (t === "progress") {
      progress = payload.progress ?? 0;
      statusText = msg.replace(/[:\s]*\d+(\.\d+)?%/g, "").trim();
    }
    else if (t === "status") { statusText = msg; }
    else if (t === "batch") {
      batchProgress = {
        completed: payload.completed ?? batchProgress.completed,
        total: payload.total ?? batchProgress.total,
        succeeded: payload.succeeded ?? batchProgress.succeeded,
        failed: payload.failed ?? batchProgress.failed,
      };
      // Keep Svelte's global progress variable if it's already higher
      const batchPct = batchProgress.total > 0 ? batchProgress.completed / batchProgress.total : 0;
      if (batchPct > progress) progress = batchPct;
      
      statusText = `Downloaded ${batchProgress.completed} / ${batchProgress.total}`;
    }
    else if (t === "batch_end") {
      const s = payload.succeeded ?? 0;
      const f = payload.failed ?? 0;
      statusText = `Done! ${s} succeeded${f > 0 ? `, ${f} failed` : ""}`;
      progress = 1.0;
      downloadSuccess = f === 0;
      isDownloading = false;
    }
    else if (t === "complete") {
      statusText = msg;
      progress = 1.0;
      downloadSuccess = payload.success ?? true;
      isDownloading = false;
    }
    else if (t === "error") {
      statusText = msg;
      downloadSuccess = false;
      isDownloading = false;
    }
  }
</script>

<svelte:head>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet" />
</svelte:head>

<main class="container">
  <div class="background-effects">
    <div class="orb orb-1"></div>
    <div class="orb orb-2"></div>
    <div class="orb orb-3"></div>
  </div>

  <div class="content-wrapper" class:wide={isExpanding}>

    <!-- ── HEADER ────────────────────────────────────────────────────────── -->
    <header class:compact={isExpanding}>
      <h1>Ember</h1>
      {#if !isExpanding}
        <p class="subtitle">Yours, forever.</p>
      {/if}
    </header>

    <!-- ── HOME CARD (URL input) ─────────────────────────────────────────── -->
    {#if !showDetails}
      <div class="glass-card" class:exit={transitioning}>
        <div class="input-group">
          <input
            type="text"
            placeholder="Paste Spotify or YouTube link here..."
            bind:value={url}
            disabled={isBusy}
            class:locked={isBusy}
            onkeydown={handleKeydown}
          />
          <button
            onclick={inspectUrl}
            disabled={isBusy || !url}
            class:loading={isBusy}
          >
            <span class="btn-text">{isFetching ? "Inspecting..." : isWarmup ? "Preparing..." : "Inspect"}</span>
            <div class="btn-glow"></div>
          </button>
        </div>

        {#if fetchError}
          <p class="fetch-error">⚠ {fetchError}</p>
        {/if}

        <div class="status-panel" class:active={isBusy}>
          <div class="gif-wrapper" class:active={isBusy}>
            <img src="/loader.gif" alt="Status" class="status-gif" class:active={isBusy} />
          </div>
          <p class="status-label">{statusText}</p>
        </div>
      </div>
    {/if}

    <!-- ── DETAILS CARD ───────────────────────────────────────────────────── -->
    {#if showDetails && track}
      <div class="details-layout" class:exit={transitioning}>

        <div class="cover-col">
          {#if track.cover_url}
            <img class="cover-img" src={track.cover_url} alt="Album cover" />
          {:else}
            <div class="cover-placeholder">♪</div>
          {/if}

          {#if track.cover_url}
            <button
              class="save-cover-btn"
              onclick={saveCover}
              disabled={isSavingCover}
              class:saved={coverSaved}
            >
              {#if coverSaved}
                <span class="cover-btn-icon">✓</span>
                <span>Saved!</span>
              {:else if isSavingCover}
                <span class="cover-btn-icon spinning">⟳</span>
                <span>Saving...</span>
              {:else}
                <span class="cover-btn-icon">↓</span>
                <span>Save Cover</span>
              {/if}
            </button>
          {/if}
        </div>

        <div class="meta-col">

          <button class="back-btn" onclick={clearTrack}>← Back</button>

          <div class="meta-header">
            <h2 class="track-title">{track.title}</h2>
          </div>

          <div class="meta-top">
            {#if track.media_type === 'video'}
              <p class="track-artist">{track.artists[0] || 'Unknown'}</p>
              <div class="divider"></div>
              <div class="meta-grid">
                <span class="meta-key">Duration</span>
                <span class="meta-val">{formatDuration(track.duration)}</span>
                
                {#if track.album}
                  <span class="meta-key">Desc</span>
                  <span class="meta-val video-desc">{track.album}</span>
                {/if}
              </div>
            {:else}
              <p class="track-artist">{track.artists.length > 1 ? track.artists.slice(0,-1).join(', ') + ' & ' + track.artists.at(-1) : track.artists[0]}</p>

              <div class="divider"></div>

              <div class="meta-grid">
                {#if track.album}
                  <span class="meta-key">Album</span>
                  <span class="meta-val">{track.album}</span>
                {/if}

                {#if track.year}
                  <span class="meta-key">Year</span>
                  <span class="meta-val">{track.year}</span>
                {/if}

                {#if track.duration}
                  <span class="meta-key">Duration</span>
                  <span class="meta-val">{formatDuration(track.duration)}</span>
                {/if}

                {#if track.track_number}
                  <span class="meta-key">Track</span>
                  <span class="meta-val">
                    {track.track_number}{track.total_tracks ? ` / ${track.total_tracks}` : ''}
                  </span>
                {/if}

                {#if track.genre}
                  <span class="meta-key">Genre</span>
                  <span class="meta-val">{track.genre}</span>
                {/if}

                {#if track.isrc}
                  <span class="meta-key">ISRC</span>
                  <span class="meta-val mono">{track.isrc}</span>
                {:else}
                  <span class="meta-key">ISRC</span>
                  <span class="meta-val muted">—</span>
                {/if}
              </div>
            {/if}
          </div>

          <div class="meta-bottom">
            <div class="divider"></div>

            <div class="progress-track">
              <div
                class="progress-fill"
                style="width: {isDownloading && progress === 0 ? 5 : Math.max(0, progress * 100)}%;"
                class:active={isDownloading && progress < 1.0}
                class:complete={progress >= 1.0}
              ></div>
            </div>

            <div class="dl-row">
              <p class="status-label" class:error={downloadSuccess === false}>
                {statusText}
              </p>
              {#if isDownloading && progress > 0}
                <span class="progress-percent">{Math.round(progress * 100)}%</span>
              {/if}
            </div>

            {#if track.source === 'spotify'}
              <div class="dl-btn-group">
                <select class="format-select" bind:value={selectedFormat} disabled={isDownloading}>
                  {#each Object.keys(AUDIO_FMT_MAP) as fmt}
                    <option value={fmt}>{fmt}</option>
                  {/each}
                </select>
                <button class="dl-btn" onclick={startDownload} disabled={isDownloading} class:downloading={isDownloading}>
                  <span class="btn-text">{isDownloading ? "Downloading..." : "Download"}</span>
                  <div class="btn-glow"></div>
                </button>
              </div>
            {:else}
              <div class="yt-controls">
                <div class="yt-format-row">
                  <button
                    class="format-tab"
                    class:active={selectedVideoFormat === "Audio (MP3)"}
                    onclick={() => { selectedVideoFormat = "Audio (MP3)"; onVideoFormatChange(); }}
                    disabled={isDownloading}
                  >Audio (MP3)</button>
                  <button
                    class="format-tab"
                    class:active={selectedVideoFormat === "Video (MP4)"}
                    onclick={() => { selectedVideoFormat = "Video (MP4)"; onVideoFormatChange(); }}
                    disabled={isDownloading}
                  >Video (MP4)</button>
                </div>
                <select class="format-select" bind:value={selectedQuality} disabled={isDownloading}>
                  {#each QUALITY_OPTIONS[selectedVideoFormat] as q}
                    <option value={q}>{q}</option>
                  {/each}
                </select>
              </div>
              <button class="dl-btn" onclick={startDownload} disabled={isDownloading} class:downloading={isDownloading}>
                <span class="btn-text">{isDownloading ? "Downloading..." : "Download"}</span>
                <div class="btn-glow"></div>
              </button>
            {/if}
          </div>

        </div>
      </div>
    {/if}

    <!-- ── PLAYLIST / ALBUM CARD ──────────────────────────────────────────── -->
    {#if isPlaylist}
      <div class="details-layout" class:exit={transitioning}>
        <div class="cover-col">
          {#if playlistCover}
            <img class="cover-img" src={playlistCover} alt="Cover" />
          {:else}
            <div class="cover-placeholder">♪</div>
          {/if}

          {#if playlistCover}
            <button
              class="save-cover-btn"
              onclick={saveCover}
              disabled={isSavingCover}
              class:saved={coverSaved}
            >
              {#if coverSaved}
                <span class="cover-btn-icon">✓</span><span>Saved!</span>
              {:else if isSavingCover}
                <span class="cover-btn-icon spinning">⟳</span><span>Saving...</span>
              {:else}
                <span class="cover-btn-icon">↓</span><span>Save Cover</span>
              {/if}
            </button>
          {/if}
        </div>

        <div class="meta-col">
          <button class="back-btn" onclick={clearTrack}>← Back</button>

          <div class="meta-header">
            <h2 class="track-title">{playlistTitle}</h2>
          </div>

          <p class="track-artist">{playlistOwner} • {playlistTracks.length} tracks</p>

          <div class="divider"></div>

          <div class="playlist-controls">
            <button class="select-toggle-btn" onclick={toggleAll}>
              {allSelected ? "Deselect All" : "Select All"}
            </button>
            <span class="selected-count">{selectedIndices.size} selected</span>
          </div>

          <div class="track-list">
            {#each playlistTracks as t, i}
              <button
                class="track-row"
                class:selected={selectedIndices.has(i)}
                onclick={() => toggleTrack(i)}
              >
                <span class="track-check">{selectedIndices.has(i) ? "☑" : "☐"}</span>
                <span class="track-num">{i + 1}</span>
                {#if t.cover_url}
                  <img class="track-thumb" src={t.cover_url} alt="" />
                {:else}
                  <span class="track-thumb-placeholder">♪</span>
                {/if}
                <div class="track-info">
                  <span class="track-row-title">{t.title}</span>
                  <span class="track-row-artist">{t.artists?.join(', ') || 'Unknown'}</span>
                </div>
                <span class="track-dur">{t.duration != null && t.duration > 0 ? formatDuration(t.duration) : ''}</span>
              </button>
            {/each}
          </div>

          <div class="meta-bottom">
            <div class="divider"></div>

            <div class="progress-track">
              <div
                class="progress-fill"
                style="width: {isDownloading && progress === 0 ? 5 : Math.max(0, progress * 100)}%;"
                class:active={isDownloading && progress < 1.0}
                class:complete={progress >= 1.0}
              ></div>
            </div>

            <div class="dl-row">
              <p class="status-label" class:error={downloadSuccess === false}>
                {statusText}
              </p>
              {#if isDownloading && progress > 0}
                <span class="progress-percent">{Math.round(progress * 100)}%</span>
              {/if}
            </div>

            <div class="dl-btn-group">
              <select
                class="format-select"
                bind:value={selectedFormat}
                disabled={isDownloading}
              >
                {#each Object.keys(AUDIO_FMT_MAP) as fmt}
                  <option value={fmt}>{fmt}</option>
                {/each}
              </select>
              <button
                class="dl-btn"
                onclick={startBatchDownload}
                disabled={isDownloading || selectedIndices.size === 0}
                class:downloading={isDownloading}
              >
                <span class="btn-text">
                  {isDownloading ? `Downloading ${batchProgress.completed}/${batchProgress.total}...` : `Download ${selectedIndices.size} Track${selectedIndices.size !== 1 ? 's' : ''}`}
                </span>
                <div class="btn-glow"></div>
              </button>
            </div>
          </div>
        </div>
      </div>
    {/if}

  </div>
</main>

<style>
  /* ── Global ──────────────────────────────────────────────────────────────── */
  :global(html, body) {
    margin: 0; padding: 0;
    background-color: #080A12;
    color: rgba(255,255,255,0.95);
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    min-height: 100vh;
    overflow: hidden;
    background-image:
      radial-gradient(circle at 0% 0%, rgba(225,29,46,.10) 0%, transparent 40%),
      radial-gradient(circle at 100% 0%, rgba(31,40,51,.15) 0%, transparent 40%);
    background-attachment: fixed;
  }
  :global(html) { -ms-overflow-style: none; scrollbar-width: none; }
  :global(html::-webkit-scrollbar, body::-webkit-scrollbar) { display: none; }

  /* ── Layout ──────────────────────────────────────────────────────────────── */
  .container {
    position: relative;
    width: 100%; height: 100vh;
    display: flex;
    justify-content: center;
    align-items: center;
  }

  .background-effects { position: absolute; inset: 0; overflow: hidden; z-index: 0; }
  .background-effects::after {
    content: ''; position: absolute; inset: 0;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E");
    opacity: 0.04; mix-blend-mode: overlay; pointer-events: none;
  }
  .orb {
    position: absolute; border-radius: 50%;
    filter: blur(120px); opacity: 0.25;
    animation: float 12s cubic-bezier(0.4, 0, 0.2, 1) infinite alternate;
  }
  .orb-1 {
    width: 45vw; height: 45vw;
    background: radial-gradient(circle, #E11D2E 0%, transparent 60%);
    top: -15%; left: -15%;
  }
  .orb-2 {
    width: 40vw; height: 40vw;
    background: radial-gradient(circle, #1F2833 0%, transparent 60%);
    bottom: -15%; right: -15%;
    animation-delay: -6s;
  }
  .orb-3 {
    width: 35vw; height: 35vw;
    background: radial-gradient(circle, #FF4D6A 0%, transparent 60%);
    top: 30%; left: 40%;
    animation-delay: -3s; opacity: 0.15;
  }
  @keyframes float {
    0%   { transform: translate(0,0) scale(1) rotate(0deg); }
    100% { transform: translate(8%,8%) scale(1.15) rotate(10deg); }
  }

  .content-wrapper {
    position: relative; z-index: 1;
    width: 100%; max-width: 640px;
    padding: 2rem; box-sizing: border-box;
    transition: all 0.38s cubic-bezier(0.22, 1, 0.36, 1);
  }
  .content-wrapper.wide {
    position: absolute;
    inset: 2rem 2.4rem 2rem 2rem;
    max-width: none;
    width: auto;
    padding: 0;
    display: flex;
    flex-direction: column;
  }

  /* ── Header ──────────────────────────────────────────────────────────────── */
  header { text-align: center; margin-bottom: 2.5rem; transition: all 0.3s ease; }
  header.compact {
    margin-bottom: 1rem;
    padding-top: 0;
  }

  h1 {
    font-family: 'Outfit', sans-serif;
    font-weight: 700; font-size: 3.5rem;
    margin: 0; color: #FFFFFF;
    text-shadow: 0 2px 4px rgba(0,0,0,.5);
    letter-spacing: -1px;
    transition: font-size 0.3s ease;
  }
  header.compact h1 { font-size: 2rem; }

  .subtitle {
    font-family: 'Outfit', sans-serif;
    color: #A0A4A8; font-size: 1.1rem; font-weight: 300;
    margin-top: .5rem; letter-spacing: 1px;
  }

  /* ── Home glass card ─────────────────────────────────────────────────────── */
  .glass-card {
    background: rgba(255,255,255,0.03);
    backdrop-filter: blur(32px) saturate(1.4); -webkit-backdrop-filter: blur(32px) saturate(1.4);
    border-radius: 24px; padding: 2.5rem;
    box-shadow: 
      0 25px 50px -12px rgba(0,0,0,0.5),
      inset 0 1px 1px rgba(255,255,255,0.15),
      inset 1px 0 1px rgba(255,255,255,0.05),
      inset -1px -1px 1px rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.04);
    opacity: 1;
    transform: scale(1) translateY(0);
    transition: opacity 0.28s ease, transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.4s ease;
  }
  .glass-card:hover {
    box-shadow: 
      0 30px 60px -12px rgba(0,0,0,0.6),
      inset 0 1px 2px rgba(255,255,255,0.2),
      inset 1px 0 2px rgba(255,255,255,0.1),
      inset -1px -1px 1px rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.06);
    transform: scale(1.005);
  }

  .glass-card.exit {
    opacity: 0;
    transform: scale(1.03) translateY(-10px);
    pointer-events: none;
  }

  .input-group { display: flex; gap: 1rem; margin-bottom: 1.5rem; }

  input {
    flex: 1;
    background: rgba(255,255,255,0.02);
    backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
    border: 1px solid rgba(255,255,255,0.05);
    color: rgba(255,255,255,0.95); padding: 1rem 1.5rem;
    border-radius: 12px; font-size: 1.05rem;
    font-family: 'Inter', sans-serif; outline: none;
    transition: all .3s cubic-bezier(.4,0,.2,1);
    box-shadow: inset 0 2px 4px rgba(0,0,0,.3);
  }
  input::placeholder { color: rgba(255,255,255,0.4); }
  input:focus {
    background: rgba(255,255,255,0.05); 
    border-color: rgba(225,29,46,0.4);
    box-shadow: 
      inset 0 2px 4px rgba(0,0,0,.3), 
      0 0 0 4px rgba(225,29,46,.15),
      inset 0 1px 1px rgba(255,255,255,0.1);
  }
  input:disabled { opacity: .7; cursor: not-allowed; }
  input.locked {
    border-color: rgba(225,29,46,.55);
    background: rgba(225,29,46,0.05);
  }

  .fetch-error {
    color: #FF5555; font-size: .9rem;
    margin: 0 0 1rem;
    padding: .6rem 1rem;
    background: rgba(255,85,85,.08);
    border: 1px solid rgba(255,85,85,.2);
    border-radius: 10px;
  }

  /* ── Shared button ───────────────────────────────────────────────────────── */
  button {
    position: relative;
    background: rgba(225,29,46,0.8); color: #FFFFFF;
    border: 1px solid rgba(255,255,255,0.1);
    backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
    padding: 0 2rem;
    border-radius: 12px; font-size: 1.05rem; font-weight: 600;
    font-family: 'Inter', sans-serif; cursor: pointer; overflow: hidden;
    transition: all .4s cubic-bezier(0.34, 1.56, 0.64, 1);
    box-shadow: 0 4px 14px rgba(225,29,46,.3), inset 0 1px 1px rgba(255,255,255,0.2);
  }
  .btn-text { position: relative; z-index: 1; }
  .btn-glow {
    position: absolute; inset: 0;
    background: linear-gradient(135deg, rgba(225,29,46,0.9) 0%, rgba(255,85,85,1) 50%, rgba(225,29,46,0.9) 100%);
    background-size: 200% 200%;
    opacity: 0; transition: opacity .5s ease-in-out;
    animation: btn-gradient-shift 3s infinite linear;
  }
  @keyframes btn-gradient-shift {
    0% { background-position: 0% 50%; }
    100% { background-position: 200% 50%; }
  }
  button:hover:not(:disabled) .btn-glow { opacity: 1; }
  button:hover:not(:disabled) { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(225,29,46,.5), inset 0 1px 2px rgba(255,255,255,0.3); }
  button:active:not(:disabled) { transform: translateY(0); }
  button:disabled { 
    background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.4); 
    border-color: rgba(255,255,255,0.02);
    box-shadow: none; cursor: not-allowed; transform: none; 
  }
  button.loading { background: linear-gradient(135deg, rgba(225,29,46,0.6) 0%, rgba(255,111,111,0.6) 100%); }

  /* ── Status panel (home) ─────────────────────────────────────────────────── */
  .status-panel {
    display: flex; align-items: center; gap: .85rem;
    padding: .9rem 1rem; border-radius: 18px;
    background: rgba(255,255,255,0.02);
    backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(255,255,255,.05);
    transition: all 0.3s ease;
  }
  .status-panel.active {
    background: rgba(225, 29, 46, 0.04);
    border-color: rgba(225, 29, 46, 0.2);
    box-shadow: inset 0 0 20px rgba(225, 29, 46, 0.1), 0 0 15px rgba(225, 29, 46, 0.2);
  }
  .gif-wrapper {
    position: relative;
    width: 32px;
    height: 32px;
    flex-shrink: 0;
  }
  .gif-wrapper::before {
    content: '';
    position: absolute;
    inset: -6px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(225, 29, 46, 0.7) 0%, transparent 70%);
    opacity: 0.35;
    transition: opacity 0.3s ease;
    filter: blur(8px);
  }
  .gif-wrapper.active::before {
    opacity: 1;
  }
  .status-gif {
    width: 32px;
    height: 32px;
    opacity: 0.3;
    filter: grayscale(100%);
    mix-blend-mode: screen;
    transition: all 0.3s ease;
    position: relative;
    z-index: 1;
  }
  .status-gif.active {
    opacity: 1;
    filter: drop-shadow(0 0 12px rgba(225, 29, 46, 0.8));
  }

  .status-label { margin: 0; font-size: .95rem; color: #D3D7DA; letter-spacing: .03em; }
  .status-label.error   { color: #FF5555; }

  /* ── Details layout ──────────────────────────────────────────────────────── */
  .details-layout {
    display: grid;
    grid-template-columns: auto 1fr;
    align-items: stretch;
    gap: 2.5rem;
    background: rgba(255,255,255,0.03);
    backdrop-filter: blur(32px) saturate(1.4); -webkit-backdrop-filter: blur(32px) saturate(1.4);
    border-radius: 24px;
    padding: 2.5rem;
    box-shadow: 
      0 25px 50px -12px rgba(0,0,0,0.5),
      inset 0 1px 1px rgba(255,255,255,0.15),
      inset 1px 0 1px rgba(255,255,255,0.05),
      inset -1px -1px 1px rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.04);
    flex: 1;
    min-height: 0;
    box-sizing: border-box;
    opacity: 1;
    transform: scale(1) translateY(0);
    transition: opacity 0.28s ease, transform 0.28s cubic-bezier(0.22, 1, 0.36, 1);
    animation: detailsIntro 0.35s cubic-bezier(0.22, 1, 0.36, 1) both;
    overflow: visible;
  }

  @keyframes detailsIntro {
    from { opacity: 0; transform: scale(0.97) translateY(12px); }
    to { opacity: 1; transform: scale(1) translateY(0); }
  }

  .details-layout.exit {
    opacity: 0;
    transform: scale(1.03) translateY(-10px);
    pointer-events: none;
  }

  .cover-col {
    width: clamp(180px, 28vh, 300px);
    flex-shrink: 0;
    align-self: start;
  }

  .cover-img {
    width: 100%;
    height: auto;
    border-radius: 16px;
    display: block;
    box-shadow: 0 16px 40px rgba(0,0,0,.6), 0 0 0 1px rgba(255,255,255,.06);
  }
  .cover-placeholder {
    width: 100%;
    aspect-ratio: 1 / 1;
    border-radius: 16px;
    background: #1A1C23;
    display: flex; align-items: center; justify-content: center;
    font-size: 5rem; color: #2A2D35;
  }

  .meta-col {
    display: flex; flex-direction: column;
    gap: .75rem; min-width: 0;
    height: 100%;
    overflow: visible;
  }

  .meta-header {
    flex-shrink: 0;
  }

  .meta-top { 
    flex: 1 1 0; 
    display: flex; 
    flex-direction: column; 
    gap: .75rem; 
    overflow-y: auto;
    min-height: 0;
    padding-right: 0.5rem;
    scrollbar-width: thin;
    scrollbar-color: rgba(255,255,255,0.15) transparent;
  }
  .meta-top > * { flex-shrink: 0; }
  
  .meta-top::-webkit-scrollbar { width: 4px; }
  .meta-top::-webkit-scrollbar-track { background: transparent; }
  .meta-top::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 4px; }
  .meta-top::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.3); }

  .meta-bottom { 
    display: flex; 
    flex-direction: column; 
    gap: .6rem; 
    margin-top: auto; 
    flex-shrink: 0;
    padding-bottom: 6px;
  }

  .back-btn {
    background: rgba(255,255,255,0.02);
    backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
    border: 1px solid rgba(255,255,255,0.05);
    color: rgba(255,255,255,0.6); font-size: .85rem;
    padding: .35rem .9rem; border-radius: 8px;
    box-shadow: none;
    align-self: flex-start;
    margin-left: 6px;
    margin-bottom: .25rem;
    flex-shrink: 0;
  }
  .back-btn:hover:not(:disabled) {
    background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.95);
    border-color: rgba(255,255,255,0.1);
    transform: scale(1.02); box-shadow: 0 2px 8px rgba(0,0,0,0.2);
  }

  .track-title {
    font-family: 'Outfit', sans-serif;
    font-size: 1.6rem; font-weight: 700;
    margin: 0; color: #FFFFFF;
    line-height: 1.25;
    overflow: hidden; text-overflow: ellipsis;
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical;
  }

  .track-artist {
    margin: 0; font-size: 1rem; color: #A0A4A8; font-weight: 500;
    overflow: hidden; text-overflow: ellipsis;
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical;
  }

  .divider { height: 1px; background: #2A2D35; margin: .25rem 0; }

  .meta-grid {
    display: grid;
    grid-template-columns: 80px 1fr;
    row-gap: .5rem;
    column-gap: 1rem;
    font-size: .9rem;
    width: 100%;
  }
  .meta-key { color: #555E6B; font-weight: 600; text-transform: uppercase; font-size: .75rem; letter-spacing: .06em; align-self: center; }
  .meta-val { color: #D3D7DA; align-self: center; }
  .meta-val.mono { font-family: 'Courier New', monospace; font-size: .82rem; letter-spacing: .04em; color: #A0A4A8; }
  .meta-val.muted { color: #3A3D46; }

  .progress-track {
    width: 100%; height: 21px;
    background: rgba(255,255,255,0.03);
    backdrop-filter: blur(4px);
    border: 1px solid rgba(255,255,255,0.05);
    box-shadow: inset 0 2px 4px rgba(0,0,0,0.4);
    border-radius: 999px;
    position: relative;
    overflow: hidden; /* Hard clip — prevents any horizontal bleed */
    display: flex;
    align-items: center;
  }
  .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, rgba(225,29,46,0.9) 0%, rgba(255,77,106,1) 50%, rgba(225,29,46,0.9) 100%);
    background-size: 200% 100%;
    box-shadow: 0 0 10px rgba(225,29,46,0.5);
    transition: width 0.3s cubic-bezier(.4,0,.2,1);
    position: relative;
    border-radius: 999px;
  }
  .progress-fill.active, .progress-fill.complete {
    animation: pulse-glow 1.5s ease-in-out infinite alternate;
  }
  @keyframes pulse-glow {
    0% { box-shadow: 0 0 8px rgba(225,29,46,0.6), 0 0 16px rgba(225,29,46,0.3); }
    100% { box-shadow: 0 0 15px rgba(255,77,106,0.9), 0 0 25px rgba(255,77,106,0.6); }
  }

  /* Sine wave graph overlay */
  .progress-fill.active::after, .progress-fill.complete::after {
    content: '';
    position: absolute;
    top: -8px; bottom: -8px;
    left: 0; right: 0;
    z-index: 3;
    pointer-events: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='40' height='20' viewBox='0 0 40 20'%3E%3Cpath d='M0,10 Q10,0 20,10 T40,10' fill='none' stroke='rgba(255,255,255,0.7)' stroke-width='1.5'/%3E%3Cpath d='M0,10 Q10,20 20,10 T40,10' fill='none' stroke='rgba(255,255,255,0.3)' stroke-width='1.5'/%3E%3C/svg%3E");
    background-size: 40px 100%;
    background-repeat: repeat-x;
    animation: wave-flow 2s infinite linear;
    mask-image: linear-gradient(90deg, transparent 0%, black 15%, black 85%, transparent 100%);
    -webkit-mask-image: linear-gradient(90deg, transparent 0%, black 15%, black 85%, transparent 100%);
  }

  @keyframes wave-flow {
    0%   { background-position: 0 0; }
    100% { background-position: 40px 0; }
  }

  /* Linear pulsating light sweep */
  .progress-fill.active::before, .progress-fill.complete::before {
    content: '';
    position: absolute;
    top: 0; bottom: 0;
    left: 0; right: 0;
    z-index: 4;
    pointer-events: none;
    background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.4) 150px, transparent 300px, transparent 1000px);
    background-repeat: repeat-x;
    background-size: 1000px 100%;
    animation: light-sweep-bg 3s infinite linear;
    mask-image: linear-gradient(90deg, transparent 0%, black 25%, black 75%, transparent 100%);
    -webkit-mask-image: linear-gradient(90deg, transparent 0%, black 25%, black 75%, transparent 100%);
  }

  @keyframes light-sweep-bg {
    0%   { background-position: -1000px 0; }
    100% { background-position: 0px 0; }
  }

  .dl-row {
    display: flex; justify-content: space-between; align-items: center;
    min-height: 1.4rem;
  }
  .progress-percent {
    font-size: .85rem; font-weight: 600; color: #FF5555;
    font-variant-numeric: tabular-nums;
  }

  .dl-btn {
    width: 100%; height: 48px;
    border-radius: 14px; font-size: 1rem;
    margin-top: .25rem;
  }
  .dl-btn.downloading {
    background: #1F2833;
    border: 1px solid rgba(225,29,46,.3);
  }

  .dl-btn-group {
    display: flex;
    gap: 0.75rem;
    width: 100%;
  }
  .dl-btn-group .dl-btn {
    flex: 1;
  }

  .video-desc {
    white-space: pre-wrap;
    font-size: 0.85rem;
    line-height: 1.4;
    color: #A0A4A8;
    word-break: break-word;
  }

  /* ── Save Cover button ──────────────────────────────────────────────────── */
  .save-cover-btn {
    width: 100%;
    height: 28px;
    margin-top: .5rem;
    padding: 0 1rem;
    border-radius: 8px;
    font-size: .85rem;
    font-weight: 500;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: .45rem;
    background: rgba(255,255,255,.03);
    backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
    border: 1px solid rgba(255,255,255,.05);
    color: rgba(255,255,255,0.6);
    box-shadow: none;
    transition: all .3s cubic-bezier(0.34, 1.56, 0.64, 1);
    cursor: pointer;
  }
  .save-cover-btn:hover:not(:disabled) {
    background: rgba(225,29,46,.15);
    border-color: rgba(225,29,46,.4);
    color: #FFFFFF;
    box-shadow: 0 0 12px rgba(225,29,46,.2);
    transform: translateY(-2px);
  }
  .save-cover-btn:active:not(:disabled) {
    background: rgba(225,29,46,.25);
    transform: translateY(0);
  }
  .save-cover-btn:disabled {
    background: rgba(255,255,255,.02);
    color: rgba(255,255,255,0.3);
    border-color: rgba(255,255,255,0.02);
    cursor: wait;
    box-shadow: none;
    transform: none;
  }
  .save-cover-btn.saved {
    background: rgba(0,255,100,.1) !important;
    border-color: rgba(0,255,100,.4) !important;
    color: #4ADE80 !important;
    cursor: default;
  }

  .cover-btn-icon {
    font-size: 1rem;
    line-height: 1;
  }
  .cover-btn-icon.spinning {
    animation: spin .8s linear infinite;
  }
  @keyframes spin {
    0%   { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }

  /* ── Format selector ─────────────────────────────────────────────────────── */
  .format-select {
    background: rgba(255,255,255,0.03);
    backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
    border: 1px solid rgba(255,255,255,0.05);
    color: rgba(255,255,255,0.95);
    padding: 0 1rem;
    border-radius: 12px;
    font-size: .95rem;
    font-family: 'Inter', sans-serif;
    outline: none;
    cursor: pointer;
    appearance: none;
    -webkit-appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23FFFFFF' fill-opacity='0.6' d='M2 4l4 4 4-4'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 0.75rem center;
    padding-right: 2rem;
    transition: all .3s ease;
    min-width: 140px;
    box-shadow: inset 0 2px 4px rgba(0,0,0,.2);
  }
  .format-select:hover:not(:disabled) {
    border-color: rgba(225,29,46,0.3);
    background-color: rgba(255,255,255,0.05);
  }
  .format-select:focus {
    border-color: rgba(225,29,46,0.5);
    box-shadow: inset 0 2px 4px rgba(0,0,0,.2), 0 0 0 4px rgba(225,29,46,.15);
  }
  .format-select:disabled {
    opacity: .5;
    cursor: not-allowed;
  }
  .format-select option {
    background: #080A12;
    color: #FFFFFF;
  }

  /* ── Playlist controls ──────────────────────────────────────────────────── */
  .playlist-controls {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: .25rem;
  }
  .select-toggle-btn {
    background: rgba(255,255,255,.05);
    border: 1px solid rgba(255,255,255,.08);
    color: #A0A4A8;
    font-size: .8rem;
    font-weight: 500;
    padding: .3rem .8rem;
    border-radius: 8px;
    box-shadow: none;
    cursor: pointer;
  }
  .select-toggle-btn:hover:not(:disabled) {
    background: rgba(225,29,46,.1);
    border-color: rgba(225,29,46,.3);
    color: #FFFFFF;
    transform: none;
    box-shadow: none;
  }
  .selected-count {
    font-size: .8rem;
    color: #555E6B;
  }

  /* ── Track list ─────────────────────────────────────────────────────────── */
  .track-list {
    flex: 1 1 0;
    overflow-y: auto;
    overflow-x: hidden;
    min-height: 0;
    max-height: 100%;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding-right: 0.25rem;
    scrollbar-width: thin;
    scrollbar-color: rgba(255,255,255,0.15) transparent;
  }
  .track-list::-webkit-scrollbar { width: 4px; }
  .track-list::-webkit-scrollbar-track { background: transparent; }
  .track-list::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 4px; }
  .track-list::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.3); }

  .track-row {
    display: flex;
    align-items: center;
    gap: .6rem;
    padding: .5rem .6rem;
    border-radius: 10px;
    background: transparent;
    border: 1px solid transparent;
    cursor: pointer;
    transition: all .2s cubic-bezier(0.34, 1.56, 0.64, 1);
    text-align: left;
    width: auto;
    align-self: stretch;
    margin-right: 4px;
    box-sizing: border-box;
    box-shadow: none;
    min-height: 42px;
  }
  .track-row:hover:not(:disabled) {
    background: rgba(255,255,255,.04);
    border-color: rgba(255,255,255,.05);
    transform: translateX(4px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.2);
  }
  .track-row.selected {
    background: rgba(225,29,46,.1);
    border-color: rgba(225,29,46,.2);
    box-shadow: inset 0 1px 1px rgba(255,255,255,0.05);
  }
  .track-row.selected:hover:not(:disabled) {
    background: rgba(225,29,46,.15);
    transform: translateX(4px);
  }

  .track-check {
    font-size: 1rem;
    color: #555E6B;
    flex-shrink: 0;
    width: 18px;
    text-align: center;
  }
  .track-row.selected .track-check {
    color: #E11D2E;
  }

  .track-num {
    font-size: .75rem;
    color: #555E6B;
    width: 20px;
    text-align: right;
    flex-shrink: 0;
    font-variant-numeric: tabular-nums;
  }

  .track-thumb {
    width: 36px;
    height: 36px;
    border-radius: 6px;
    object-fit: cover;
    flex-shrink: 0;
    background: #1A1C23;
  }
  .track-thumb-placeholder {
    width: 36px;
    height: 36px;
    border-radius: 6px;
    background: #1A1C23;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: .9rem;
    color: #2A2D35;
    flex-shrink: 0;
  }

  .track-info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .track-row-title {
    font-size: .85rem;
    color: #D3D7DA;
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .track-row-artist {
    font-size: .72rem;
    color: #555E6B;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .track-dur {
    font-size: .75rem;
    color: #555E6B;
    flex-shrink: 0;
    font-variant-numeric: tabular-nums;
  }

  /* ── YouTube controls ───────────────────────────────────────────────────── */
  .yt-controls {
    display: flex;
    flex-direction: column;
    gap: .5rem;
    margin-bottom: .25rem;
  }
  .yt-format-row {
    display: flex;
    gap: 0;
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid rgba(255,255,255,0.05);
    background: rgba(255,255,255,0.02);
  }
  .format-tab {
    flex: 1;
    padding: .5rem 1rem;
    font-size: .85rem;
    font-weight: 500;
    background: transparent;
    color: rgba(255,255,255,0.55);
    border: none;
    border-radius: 0;
    cursor: pointer;
    transition: all .2s ease;
    box-shadow: none;
  }
  .format-tab:hover:not(:disabled) {
    background: rgba(255,255,255,0.05);
    color: rgba(255,255,255,0.95);
    transform: none;
    box-shadow: none;
  }
  .format-tab.active {
    background: rgba(225,29,46,0.8);
    color: #FFFFFF;
    box-shadow: inset 0 1px 1px rgba(255,255,255,0.2);
  }
  .format-tab:disabled {
    opacity: .5;
    cursor: not-allowed;
    background: #1A1C23;
    color: #555E6B;
    box-shadow: none;
    transform: none;
  }
</style>