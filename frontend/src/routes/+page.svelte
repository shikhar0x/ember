<script lang="ts">
  import { onMount } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import { openUrl } from '@tauri-apps/plugin-opener';
  import { fade, fly, scale, crossfade, slide } from 'svelte/transition';
  import { quintOut, cubicOut, backOut } from 'svelte/easing';

  const openExternalUrl = (link: string) => {
    openUrl(link);
  };

  const [send, receive] = crossfade({
    duration: 800,
    easing: quintOut
  });

  let url = "";
  let isUrlFocused = false;
  let isInputHovered = false;

  function handleClearUrl(e: MouseEvent) {
    e.stopPropagation();
    url = "";
    setTimeout(() => {
      const input = document.querySelector('.top-bar-input input, .input-wrapper input') as HTMLInputElement;
      if (input) input.focus();
    }, 50);
  }

  let statusText = "Ready";
  
  function getIdleText() {
    if (isExpanding) return "Ready";
    return userProfile?.display_name ? `Welcome, ${userProfile.display_name}!` : "Ready";
  }

  let progress = 0.0;
  let isDownloading = false;
  let isFetching = false;
  interface HistoryItem {
    url: string;
    cover_url?: string | null;
    title?: string;
    type?: string;
  }
  let searchHistory: HistoryItem[] = [];
  let isClearingHistory = false;

  function historyTransition(node: HTMLElement) {
    if (isClearingHistory) {
      const style = getComputedStyle(node);
      const opacity = +style.opacity;
      const height = parseFloat(style.height);
      const padding_top = parseFloat(style.paddingTop);
      const padding_bottom = parseFloat(style.paddingBottom);
      const margin_top = parseFloat(style.marginTop);
      const margin_bottom = parseFloat(style.marginBottom);

      return {
        duration: 250,
        easing: cubicOut,
        css: (t: number) => {
          const fastFade = Math.max(0, (t - 0.4) / 0.6);
          return `
            opacity: ${fastFade * opacity};
            height: ${t * height}px;
            padding-top: ${t * padding_top}px;
            padding-bottom: ${t * padding_bottom}px;
            margin-top: ${t * margin_top}px;
            margin-bottom: ${t * margin_bottom}px;
            overflow: hidden;
          `;
        }
      };
    } else {
      return slide(node, { duration: 200, easing: cubicOut });
    }
  }
  let isProfileMenuOpen = false;
  let activeProfileSubMenu = "main"; // 'main' | 'history' | 'about' | 'themes' | 'wallpapers'

  const WALLPAPER_PRESETS = [
    {
      name: "Mountain Lake",
      url: "https://images.unsplash.com/photo-1472214103451-9374bd1c798e?q=100&w=2560&ar=16:9&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1472214103451-9374bd1c798e?q=80&w=250&ar=16:9&fit=crop",
      isLight: true
    },
    {
      name: "Misty Forest",
      url: "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?q=100&w=2560&ar=16:9&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?q=80&w=250&ar=16:9&fit=crop",
      isLight: true
    },
    {
      name: "Sunrise Hills",
      url: "https://images.unsplash.com/photo-1449844908441-8829872d2607?q=100&w=2560&ar=16:9&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1449844908441-8829872d2607?q=80&w=250&ar=16:9&fit=crop",
      isLight: false
    },
    {
      name: "Tropical Falls",
      url: "https://images.unsplash.com/photo-1433086966358-54859d0ed716?q=100&w=2560&ar=16:9&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1433086966358-54859d0ed716?q=80&w=250&ar=16:9&fit=crop",
      isLight: true
    },
    {
      name: "Misty Peaks",
      url: "https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?q=100&w=2560&ar=16:9&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?q=80&w=250&ar=16:9&fit=crop",
      isLight: true
    },
    {
      name: "Dolomites",
      url: "https://images.unsplash.com/photo-1501785888041-af3ef285b470?q=100&w=2560&ar=16:9&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1501785888041-af3ef285b470?q=80&w=250&ar=16:9&fit=crop",
      isLight: false
    },
    {
      name: "Starry Forest",
      url: "https://images.unsplash.com/photo-1419242902214-272b3f66ee7a?q=100&w=2560&ar=16:9&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1419242902214-272b3f66ee7a?q=80&w=250&ar=16:9&fit=crop",
      isLight: false
    },
    {
      name: "Alpine Glow",
      url: "https://images.unsplash.com/photo-1469474968028-56623f02e42e?q=100&w=2560&ar=16:9&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1469474968028-56623f02e42e?q=80&w=250&ar=16:9&fit=crop",
      isLight: true
    },
    {
      name: "Mountain Sunset",
      url: "https://images.unsplash.com/photo-1643865420039-0c4d77d0553f?q=100&w=2560&ar=16:9&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1643865420039-0c4d77d0553f?q=80&w=250&ar=16:9&fit=crop",
      isLight: false
    },
    {
      name: "Sun Rays",
      url: "https://images.unsplash.com/photo-1425913397330-cf8af2ff40a1?q=100&w=2560&ar=16:9&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1425913397330-cf8af2ff40a1?q=80&w=250&ar=16:9&fit=crop",
      isLight: true
    },
    {
      name: "Pagoda Temple",
      url: "https://images.unsplash.com/photo-1542640244-7e672d6cef4e?q=100&w=2560&ar=16:9&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1542640244-7e672d6cef4e?q=80&w=250&ar=16:9&fit=crop",
      isLight: true
    },
    {
      name: "Outer Space",
      url: "https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=100&w=2560&ar=16:9&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=250&ar=16:9&fit=crop",
      isLight: false
    },
    {
      name: "Night Silhouette",
      url: "https://images.unsplash.com/photo-1485470733090-0aae1788d5af?q=100&w=2560&ar=16:9&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1485470733090-0aae1788d5af?q=80&w=250&ar=16:9&fit=crop",
      isLight: false
    },
    {
      name: "Brown House",
      url: "https://images.unsplash.com/photo-1470770841072-f978cf4d019e?q=100&w=2560&ar=16:9&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1470770841072-f978cf4d019e?q=80&w=250&ar=16:9&fit=crop",
      isLight: true
    },
    {
      name: "Pine Trees Mist",
      url: "https://images.unsplash.com/photo-1502252430442-aac78f397426?q=100&w=2560&ar=16:9&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1502252430442-aac78f397426?q=80&w=250&ar=16:9&fit=crop",
      isLight: true
    },
    {
      name: "Floating Cubes",
      url: "https://images.unsplash.com/photo-1622737133809-d95047b9e673?q=100&w=2560&ar=16:9&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1622737133809-d95047b9e673?q=80&w=250&ar=16:9&fit=crop",
      isLight: true
    },
    {
      name: "Golden Flow",
      url: "https://images.unsplash.com/photo-1574169208507-84376144848b?q=100&w=2560&ar=16:9&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1574169208507-84376144848b?q=80&w=250&ar=16:9&fit=crop",
      isLight: false
    },
    {
      name: "Dark Wave",
      url: "https://images.unsplash.com/photo-1614850523459-c2f4c699c52e?q=100&w=2560&ar=16:9&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1614850523459-c2f4c699c52e?q=80&w=250&ar=16:9&fit=crop",
      isLight: false
    },
    {
      name: "Holographic",
      url: "https://images.unsplash.com/photo-1557672172-298e090bd0f1?q=100&w=2560&ar=16:9&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1557672172-298e090bd0f1?q=80&w=250&ar=16:9&fit=crop",
      isLight: true
    },
    {
      name: "Abstract Canvas",
      url: "https://images.unsplash.com/photo-1541701494587-cb58502866ab?q=100&w=2560&ar=16:9&fit=crop",
      thumbnail: "https://images.unsplash.com/photo-1541701494587-cb58502866ab?q=80&w=250&ar=16:9&fit=crop",
      isLight: true
    }
  ];

  const GITHUB_USERNAME = "shikhar0x";
  const GITHUB_AVATAR_URL = `https://github.com/${GITHUB_USERNAME}.png`;
  const GITHUB_PROFILE_URL = `https://github.com/${GITHUB_USERNAME}`;

  let detectedOS = "Unknown";
  let customBgColor = "#06070c";
  let customWallpaperUrl = "";
  let manualThemeOverride = "auto"; // 'auto' | 'light' | 'dark'
  let showBgMosaic = true;
  let wallpaperOpacity = 100;
  let wallpaperBlur = 3;
  let customSavedColors: string[] = [];
  let customSavedWallpapers: string[] = [];
  let clockMonth = "";
  let clockDay = "";
  let clockTime = "";
  let fetchError = "";
  type AppState = "loading" | "greeting" | "main";
  let appState: AppState = "loading";
  let statusMessage = "Connecting to Spotify...";
  let needsLogin = false;
  let userProfile: {
    display_name: string;
    avatar_url: string | null;
    uri: string;
  } | null = null;

  $: isBusy = appState === "loading" || isDownloading || isFetching;
  $: isLightTheme = ((themeOverride, wpUrl, bgColor) => {
    if (themeOverride === 'light') return true;
    if (themeOverride === 'dark') return false;
    if (wpUrl) {
      const activeWp = WALLPAPER_PRESETS.find(w => w.url === wpUrl);
      if (activeWp) return activeWp.isLight;
    }
    const cleanHex = bgColor.replace('#', '');
    if (cleanHex.length !== 6) return false;
    const r = parseInt(cleanHex.substring(0, 2), 16);
    const g = parseInt(cleanHex.substring(2, 4), 16);
    const b = parseInt(cleanHex.substring(4, 6), 16);
    const y = 0.299 * r + 0.587 * g + 0.114 * b;
    return y > 140;
  })(manualThemeOverride, customWallpaperUrl, customBgColor);
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
  let selectedDownloadType = "audio"; // "audio" or "video"
  let selectedAudioQuality = "Best Available";
  let selectedVideoQuality = "Best Available";
  let activeDropdown: string | null = null;
  
  function slowFlyFastFade(node: HTMLElement, { duration = 600, y = -25 }) {
    return {
      duration,
      css: (t: number) => {
        const eased = cubicOut(t);
        const op = Math.min(1, t * 4);
        return `
          transform: translateY(${(1 - eased) * y}px);
          opacity: ${op};
        `;
      }
    };
  }

  let menuRotations: Record<string, number> = {};
  let previousDropdown: string | null = null;
  $: {
    if (activeDropdown !== previousDropdown) {
      if (activeDropdown) {
        menuRotations[activeDropdown] = (menuRotations[activeDropdown] || 0) + 180;
      }
      if (previousDropdown) {
        menuRotations[previousDropdown] = (menuRotations[previousDropdown] || 0) + 180;
      }
      previousDropdown = activeDropdown;
    }
  }
  const AUDIO_QUALITY_OPTIONS = ["Best Available", "320 kbps", "256 kbps", "192 kbps", "128 kbps"];
  const VIDEO_QUALITY_OPTIONS = ["Best Available", "1080p", "720p", "480p", "360p"];

  let downloadSuccess: boolean | null = null;
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
    local_file_path: string | null;
  };

  let track: TrackInfo | null = null;
  let transitioning = false;
  let isTransitioningToHome = false;

  let isPlaylist = false;
  let playlistTitle = "";
  let playlistOwner = "";
  let playlistCover: string | null = null;
  let playlistType = "playlist";
  let playlistYear: string | null = null;
  let playlistTracks: (TrackInfo | null)[] = [];
  let selectedIndices: Set<number> = new Set();
  let batchProgress = { completed: 0, total: 0, succeeded: 0, failed: 0 };

  type HistorySnapshot = {
    url: string;
    track: TrackInfo | null;
    isPlaylist: boolean;
    playlistTitle: string;
    playlistOwner: string;
    playlistCover: string | null;
    playlistType: string;
    playlistYear: string | null;
    playlistTracks: (TrackInfo | null)[];
    selectedIndices: number[];
  };

  let history: HistorySnapshot[] = [];
  let historyIndex = -1;

  $: canGoBack = historyIndex >= 0 && !isDownloading && !isFetching && !transitioning;
  $: canGoForward = historyIndex < history.length - 1 && !isDownloading && !isFetching && !transitioning;
  $: showDetails = track !== null || isPlaylist;
  $: loadedCount = playlistTracks.filter(t => t !== null).length;
  $: allSelected = selectedIndices.size === loadedCount && loadedCount > 0;
  let isExpanding = false;
  let isDraggingOver = false;
  let pairedUrl = "";
  let isEmbeddingTask = false;
  let pairedPreviewTrack: TrackInfo | null = null;
  let isFetchingPreview = false;
  let previewError = "";
  let previewEs: EventSource | null = null;

  const API_BASE = "http://127.0.0.1:8008";

  let toasts: Array<{ id: number; message: string; type: 'success' | 'error' | 'cancel' }> = [];
  let toastId = 0;

  function showToast(message: string, type: 'success' | 'error' | 'cancel' = 'success') {
    const id = toastId++;
    toasts = [...toasts, { id, message, type }];

    setTimeout(() => {
      toasts = toasts.filter(t => t.id !== id);
    }, 4000);
  }

  function formatDuration(secs: number): string {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  function getErrorMessage(err: unknown): string {
    if (err instanceof Error) return err.message;
    return String(err);
  }

  function cleanErrorMessage(msg: string | null | undefined): string {
    return msg || "Unknown error occurred.";
  }

  async function startEmbedLocal() {
    if (!track || !track.local_file_path || !pairedUrl.trim() || isDownloading) return;
    isEmbeddingTask = true;
    isDownloading = true;
    downloadSuccess = null;
    statusText = "Resolving metadata...";
    progress = 0;

    try {
      const res = await fetch(`${API_BASE}/embed/metadata`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          file_path: track.local_file_path,
          source_url: pairedUrl.trim()
        }),
      });
      if (!res.ok) throw new Error(`API error: ${res.status}`);
      const data = await res.json();
      taskId = data.task_id;
      if (taskId) startPolling(taskId);
      pairedUrl = "";
    } catch (err) {
      statusText = `Error: ${getErrorMessage(err)}`;
      downloadSuccess = false;
      isDownloading = false;
      showToast("Embedding failed", "error");
    }
  }

  async function handleFileDrop(filePath: string) {
    const supportedExts = [".mp3", ".flac", ".m4a", ".mp4", ".ogg", ".opus"];
    const dotIndex = filePath.lastIndexOf('.');
    if (dotIndex === -1) {
      showToast("Unsupported file type", "error");
      return;
    }
    const ext = filePath.slice(dotIndex).toLowerCase();
    if (!supportedExts.includes(ext)) {
      showToast(`Unsupported file type: ${ext}`, "error");
      return;
    }

    let previousUrl = "";
    if (track && track.source !== "local") {
      if (track.spotify_url && (track.spotify_url.includes("/track/") || track.spotify_url.includes("music.youtube.com") || track.spotify_url.includes("youtube.com") || track.spotify_url.includes("youtu.be"))) {
        previousUrl = track.spotify_url;
      }
    }
    if (!previousUrl && url.trim()) {
      const u = url.trim();
      if ((u.includes("open.spotify.com") && u.includes("/track/")) || u.includes("music.youtube.com") || u.includes("youtube.com") || u.includes("youtu.be")) {
        previousUrl = u;
      }
    }

    isFetching = true;
    statusText = "Analyzing audio file...";

    try {
      const res = await fetch(`${API_BASE}/audio/inspect?file_path=${encodeURIComponent(filePath)}`);
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const fileTrack = await res.json();

      transitioning = true;
      await new Promise(r => setTimeout(r, 280));
      track = fileTrack;
      isPlaylist = false;
      isExpanding = true;

      if (previousUrl) {
        pairedUrl = previousUrl;
        url = ""; // Clear main search input since it has moved to pairing input
      }

      await new Promise(r => setTimeout(r, 100));
      transitioning = false;
      statusText = getIdleText();
      isFetching = false;
      pushSnapshot();
    } catch (err) {
      isFetching = false;
      statusText = getIdleText();
      showToast("Failed to inspect local file", "error");
    }
  }

  function toggleTrack(idx: number) {
    if (selectedIndices.has(idx)) selectedIndices.delete(idx);
    else selectedIndices.add(idx);
    selectedIndices = new Set(selectedIndices);
  }

  function toggleAll() {
    if (allSelected) selectedIndices = new Set();
    else {
      const indices: number[] = [];
      playlistTracks.forEach((t, i) => { if (t !== null) indices.push(i); });
      selectedIndices = new Set(indices);
    }
  }

  onMount(() => {
    const preventContextMenu = (e: MouseEvent) => e.preventDefault();
    window.addEventListener('contextmenu', preventContextMenu);

    const updateTime = () => {
      const now = new Date();
      clockMonth = now.toLocaleString('en-US', { month: 'short' }).toUpperCase();
      clockDay = now.getDate().toString().padStart(2, '0');
      const h = now.getHours().toString().padStart(2, '0');
      const min = now.getMinutes().toString().padStart(2, '0');
      clockTime = `${h}:${min}`;
    };
    updateTime();
    const clockInterval = setInterval(updateTime, 1000);

    const ua = navigator.userAgent;
    if (ua.includes("Win")) detectedOS = "Windows";
    else if (ua.includes("Mac")) detectedOS = "macOS";
    else if (ua.includes("Linux")) detectedOS = "Linux";

    const savedColor = localStorage.getItem("customBgColor");
    if (savedColor) customBgColor = savedColor;
    const savedWallpaper = localStorage.getItem("customWallpaperUrl");
    if (savedWallpaper) customWallpaperUrl = savedWallpaper;
    const savedMosaic = localStorage.getItem("showBgMosaic");
    if (savedMosaic) showBgMosaic = savedMosaic !== "false";
    const savedManualTheme = localStorage.getItem("manualThemeOverride");
    if (savedManualTheme) manualThemeOverride = savedManualTheme;

    const savedOpacity = localStorage.getItem("wallpaperOpacity");
    if (savedOpacity) wallpaperOpacity = parseInt(savedOpacity);
    const savedBlur = localStorage.getItem("wallpaperBlur");
    if (savedBlur) wallpaperBlur = parseInt(savedBlur);

    const savedColors = localStorage.getItem("customSavedColors");
    if (savedColors) {
      try {
        customSavedColors = JSON.parse(savedColors);
      } catch (e) {
        customSavedColors = ["#06070c", "#0f051d", "#05120f", "#081326", "#1d0b0b", "#111115"];
      }
    } else {
      customSavedColors = ["#06070c", "#0f051d", "#05120f", "#081326", "#1d0b0b", "#111115"];
    }

    const savedWallpapers = localStorage.getItem("customSavedWallpapers");
    if (savedWallpapers) {
      try {
        customSavedWallpapers = JSON.parse(savedWallpapers);
      } catch (e) {
        customSavedWallpapers = [];
      }
    }

    const hist = localStorage.getItem("searchHistory");
    if (hist) {
      try {
        const parsed = JSON.parse(hist);
        if (Array.isArray(parsed)) {
          searchHistory = parsed.map(item => {
            if (typeof item === "string") {
              return { url: item };
            }
            return item;
          });
        }
      } catch (e) {}
    }

    let unlistenDragDrop: (() => void) | null = null;

    if ('__TAURI_INTERNALS__' in window) {
      invoke('init_backend')
        .then(() => startStatusPolling())
        .catch(console.error);

      import('@tauri-apps/api/webview').then(({ getCurrentWebview }) => {
        const webview = getCurrentWebview();
        webview.onDragDropEvent((event) => {
          if (event.payload.type === 'drop') {
            isDraggingOver = false;
            const paths = event.payload.paths;
            if (paths && paths.length > 0) {
              handleFileDrop(paths[0]);
            }
          } else if (event.payload.type === 'enter') {
            isDraggingOver = true;
          } else if (event.payload.type === 'leave') {
            isDraggingOver = false;
          }
        }).then((unlisten) => {
          unlistenDragDrop = unlisten;
        }).catch(console.error);
      }).catch(console.error);
    } else {
      startStatusPolling();
    }

    return () => {
      window.removeEventListener('contextmenu', preventContextMenu);
      clearInterval(clockInterval);
      if (unlistenDragDrop) {
        unlistenDragDrop();
      }
      if (previewEs) {
        previewEs.close();
      }
    };
  });

  function startStatusPolling() {
    async function poll() {
      try {
        const res = await fetch(`${API_BASE}/status`);
        if (!res.ok) throw new Error("not ready");
        const data = await res.json();

        // FFmpeg status
        if (data.ffmpeg === "downloading" || data.ffmpeg === "extracting") {
          const pct = data.ffmpeg_progress ?? 0;
          statusMessage = `Preparing audio engine... ${Math.round(pct)}%`;
          statusText = statusMessage;
          setTimeout(poll, 800);
          return;  // Keep app in loading state until ffmpeg is ready
        }
        if (data.ffmpeg === "failed") {
          statusMessage = "FFmpeg download failed. Click to download manually.";
          statusText = statusMessage;
          needsLogin = true;  // Reuse the login state to show a custom action
          setTimeout(poll, 800);
          return;
        }

        statusMessage = data.message;
        statusText = data.message;
        needsLogin = data.needs_login;
        progress = data.progress ?? 0;

        if (data.ready) {
          try {
            const fetchMe = async () => {
              try {
                const me = await fetch(`${API_BASE}/me`);
                if (me.ok) {
                  const profile = await me.json();
                  userProfile = profile;
                  statusText = getIdleText();
                  if (!profile.is_loading) {
                    showToast("Profile loaded successfully", "success");
                    return true;
                  }
                  return false;
                }
              } catch { return true; }
              return true;
            };
            const done = await fetchMe();
            if (!done) {
              const interval = setInterval(async () => {
                if (await fetchMe()) clearInterval(interval);
              }, 2000);
            }
          } catch { /* non-fatal */ }
          appState = "main";
          setTimeout(() => {
            const input = document.querySelector('input[type="text"]') as HTMLInputElement;
            if (input) input.focus();
          }, 100);
          return;
        }
      } catch { /* backend not up yet */ }
      setTimeout(poll, 800);
    }
    poll();
  }

  async function inspectUrl() {
    if (!url.trim() || isBusy) return;

    const wasExpanding = isExpanding;
    isExpanding = true;
    track = null;
    playlistTitle = "";
    isPlaylist = false;
    playlistTracks = [];
    selectedIndices = new Set();
    downloadSuccess = null;
    fetchError = "";
    isFetching = true;
    statusText = "Inspecting...";
    pairedUrl = "";
    
    const trimmedUrl = url.trim();
    const existingIndex = searchHistory.findIndex(h => (typeof h === 'string' ? h : h.url) === trimmedUrl);
    let newItem: HistoryItem = { url: trimmedUrl };
    if (existingIndex !== -1) {
      const oldItem = searchHistory[existingIndex];
      newItem = typeof oldItem === 'string' ? { url: oldItem } : oldItem;
      searchHistory = [newItem, ...searchHistory.filter((_, i) => i !== existingIndex)].slice(0, 10);
    } else {
      searchHistory = [newItem, ...searchHistory].slice(0, 10);
    }
    localStorage.setItem("searchHistory", JSON.stringify(searchHistory));

    const es = new EventSource(`${API_BASE}/inspect?url=${encodeURIComponent(url.trim())}`);
    es.onmessage = async (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === "track") {
            es.close();
            newItem.title = msg.track.title;
            newItem.cover_url = msg.track.cover_url;
            newItem.type = msg.track.media_type === "video" ? "video" : "track";
            searchHistory = [...searchHistory];
            localStorage.setItem("searchHistory", JSON.stringify(searchHistory));

            transitioning = true;
            await new Promise(r => setTimeout(r, 300));
            track = msg.track;
            isPlaylist = false;
            isExpanding = true;
            await new Promise(r => setTimeout(r, 100));
            transitioning = false;
            statusText = getIdleText();
            isFetching = false;
            pushSnapshot();
        }
        else if (msg.type === "header") {
            newItem.title = msg.meta.title;
            newItem.cover_url = msg.meta.cover_url;
            newItem.type = msg.meta.type; // "playlist" or "album"
            searchHistory = [...searchHistory];
            localStorage.setItem("searchHistory", JSON.stringify(searchHistory));

            playlistType = msg.meta.type;
            playlistTitle = msg.meta.title;
            playlistOwner = msg.meta.owner;
            playlistCover = msg.meta.cover_url;
            playlistYear = msg.meta.year || null;
            playlistTracks = new Array(msg.meta.total_tracks).fill(null);
            selectedIndices = new Set();
            
            transitioning = true;
            await new Promise(r => setTimeout(r, 300));
            isPlaylist = true;
            track = null; // Clear single track if we are loading a playlist!
            isExpanding = true;
            await new Promise(r => setTimeout(r, 100));
            transitioning = false;
            statusText = `Loading ${msg.meta.total_tracks} tracks...`;
            isFetching = true;
        }
        else if (msg.type === "track_item") {
            playlistTracks[msg.index] = msg.track;
            playlistTracks = [...playlistTracks];
            selectedIndices.add(msg.index);
            selectedIndices = new Set(selectedIndices);
            const loaded = playlistTracks.filter((t: TrackInfo | null) => t !== null).length;
            statusText = `Loaded ${loaded} / ${playlistTracks.length} tracks`;
        }
        else if (msg.type === "update") {
            const existing = playlistTracks[msg.index];
            if (existing && msg.updates) {
                playlistTracks[msg.index] = { ...existing, ...msg.updates };
                playlistTracks = [...playlistTracks];
            }
        }
        else if (msg.type === "header_update") {
            if (msg.updates?.cover_url) {
                playlistCover = msg.updates.cover_url;
                newItem.cover_url = msg.updates.cover_url;
                searchHistory = [...searchHistory];
                localStorage.setItem("searchHistory", JSON.stringify(searchHistory));
            }
            if (msg.updates?.year) {
                playlistYear = msg.updates.year;
            }
        }
        else if (msg.type === "done") {
            playlistTracks = playlistTracks.filter((t: TrackInfo | null) => t !== null);
            statusText = getIdleText();
            isFetching = false;
            es.close();
            pushSnapshot();
        }
        else if (msg.type === "error") {
            const cleanMsg = cleanErrorMessage(msg.message);
            fetchError = cleanMsg;
            showToast(cleanMsg, "error");
            statusText = getIdleText();
            isFetching = false;
            isExpanding = false;
            track = null;
            isPlaylist = false;
            es.close();
        }
    };
    es.onerror = () => {
        const cleanMsg = "Invalid link or connection error";
        fetchError = cleanMsg;
        showToast(cleanMsg, "error");
        statusText = getIdleText();
        isFetching = false;
        isExpanding = false;
        track = null;
        isPlaylist = false;
        es.close();
    };
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') inspectUrl();
    if (e.key === 'Escape') {
      if (showDetails) clearTrack();
      else if (url) url = "";
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      const input = document.querySelector('input[type="text"]') as HTMLInputElement;
      if (input) input.focus();
    }
  }

  async function clearTrack() {
    isTransitioningToHome = true;
    transitioning = true;
    await new Promise(r => setTimeout(r, 280));
    track = null;
    isPlaylist = false;
    playlistTracks = [];
    playlistYear = null;
    selectedIndices = new Set();
    isExpanding = false;
    transitioning = false;
    isTransitioningToHome = false;
    fetchError = "";
    statusText = getIdleText();
    progress = 0;
    batchProgress = { completed: 0, total: 0, succeeded: 0, failed: 0 };
    downloadSuccess = null;
    url = "";
    pairedUrl = "";
    if (previewEs) {
      previewEs.close();
      previewEs = null;
    }
    pairedPreviewTrack = null;
    isFetchingPreview = false;
    previewError = "";
  }

  function pushSnapshot() {
    history = history.slice(0, historyIndex + 1);
    history.push({
      url,
      track,
      isPlaylist,
      playlistTitle,
      playlistOwner,
      playlistCover,
      playlistType,
      playlistYear,
      playlistTracks: [...playlistTracks],
      selectedIndices: [...selectedIndices],
    });
    history = history;
    historyIndex = history.length - 1;
  }

  function restoreSnapshot(snap: HistorySnapshot) {
    stopPolling();
    isFetching = false;
    isDownloading = false;
    downloadSuccess = null;
    progress = 0;
    taskId = null;
    batchProgress = { completed: 0, total: 0, succeeded: 0, failed: 0 };
    fetchError = "";
    url = snap.url;
    track = snap.track;
    isPlaylist = snap.isPlaylist;
    playlistTitle = snap.playlistTitle;
    playlistOwner = snap.playlistOwner;
    playlistCover = snap.playlistCover;
    playlistType = snap.playlistType;
    playlistYear = snap.playlistYear;
    playlistTracks = [...snap.playlistTracks];
    selectedIndices = new Set(snap.selectedIndices);
    isExpanding = snap.track !== null || snap.isPlaylist;
    statusText = getIdleText();
    pairedUrl = "";
    if (previewEs) {
      previewEs.close();
      previewEs = null;
    }
    pairedPreviewTrack = null;
    isFetchingPreview = false;
    previewError = "";
  }

  async function goBack() {
    if (!canGoBack) return;
    if (historyIndex > 0) {
      historyIndex--;
      restoreSnapshot(history[historyIndex]);
    } else {
      isTransitioningToHome = true;
      transitioning = true;
      await new Promise(r => setTimeout(r, 280));
      historyIndex = -1;
      isExpanding = false;
      url = "";
      track = null;
      isPlaylist = false;
      playlistTracks = [];
      statusText = getIdleText();
      pairedUrl = "";
      if (previewEs) {
        previewEs.close();
        previewEs = null;
      }
      pairedPreviewTrack = null;
      isFetchingPreview = false;
      previewError = "";
      transitioning = false;
      isTransitioningToHome = false;
    }
  }

  async function goForward() {
    if (!canGoForward) return;
    historyIndex++;
    restoreSnapshot(history[historyIndex]);
  }

  let isSavingCover = false;
  let coverSaved = false;
  let savedCoverPath = "";
  async function saveCover() {
    const coverUrl = track?.cover_url || playlistCover;
    const coverTitle = track?.title || playlistTitle;
    if (!coverUrl || isSavingCover) return;
    isSavingCover = true;
    coverSaved = false;
    savedCoverPath = "";
    try {
      const res = await fetch(`${API_BASE}/download/cover?url=${encodeURIComponent(coverUrl)}&title=${encodeURIComponent(coverTitle)}`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("Failed to save cover on backend");
      const data = await res.json();
      savedCoverPath = data.path || "";
      coverSaved = true;
      showToast(`Saved to ${savedCoverPath}`, "success");
      setTimeout(() => { coverSaved = false; }, 2500);
    } catch (err) {
      console.error("Save cover error:", err);
    } finally {
      isSavingCover = false;
    }
  }

  async function startDownloadWithPairing(usePairing: boolean) {
    if (!track || isDownloading) return;
    isEmbeddingTask = false;
    isDownloading = true;
    downloadSuccess = null;
    statusText = "Starting download...";
    progress = 0;
    try {
      const isSpotify = track.source === "spotify";
      let endpoint: string;
      let body: Record<string, unknown>;

      if (isSpotify) {
        const [codec, quality] = AUDIO_FMT_MAP[selectedFormat] ?? ["mp3", "0"];
        if (usePairing && pairedUrl.trim()) {
          endpoint = "/download/manual_pair";
          body = {
            spotify_track: track,
            youtube_url: pairedUrl.trim(),
            options: { format: `Audio (${selectedFormat})`, quality: "Best Available", audio_codec: codec, audio_quality: quality },
          };
        } else {
          endpoint = "/download/spotify";
          body = {
            track: track,
            options: { format: `Audio (${selectedFormat})`, quality: "Best Available", audio_codec: codec, audio_quality: quality },
          };
        }
      } else if (track.source === "ytmusic") {
        const [codec, quality] = AUDIO_FMT_MAP[selectedFormat] ?? ["mp3", "0"];
        if (usePairing && pairedUrl.trim() && pairedPreviewTrack && pairedPreviewTrack.source === "spotify") {
          endpoint = "/download/manual_pair";
          body = {
            spotify_track: pairedPreviewTrack,
            youtube_url: track.spotify_url ?? url,
            options: { format: `Audio (${selectedFormat})`, quality: "Best Available", audio_codec: codec, audio_quality: quality },
          };
        } else {
          endpoint = "/download/ytmusic";
          body = {
            track: track,
            url: track.spotify_url ?? url,
            title: track.title,
            options: { format: `Audio (${selectedFormat})`, quality: "Best Available", audio_codec: codec, audio_quality: quality },
          };
        }
      } else {
        if (usePairing && pairedUrl.trim() && pairedPreviewTrack && pairedPreviewTrack.source === "spotify") {
          const [codec, quality] = AUDIO_FMT_MAP[selectedFormat] ?? ["mp3", "0"];
          endpoint = "/download/manual_pair";
          body = {
            spotify_track: pairedPreviewTrack,
            youtube_url: track.spotify_url ?? url,
            options: { format: `Audio (${selectedFormat})`, quality: "Best Available", audio_codec: codec, audio_quality: quality },
          };
        } else {
          endpoint = "/download/youtube";
          let dlOptions;
          if (selectedDownloadType === "video") {
            dlOptions = {
              format: "Video (MP4)",
              quality: selectedVideoQuality,
              audio_codec: "mp3",
              audio_quality: "0"
            };
          } else {
            const [codec, quality] = AUDIO_FMT_MAP[selectedFormat] ?? ["mp3", "0"];
            let preferredQuality = quality;
            if (selectedAudioQuality === "320 kbps") preferredQuality = "320";
            else if (selectedAudioQuality === "256 kbps") preferredQuality = "256";
            else if (selectedAudioQuality === "192 kbps") preferredQuality = "192";
            else if (selectedAudioQuality === "128 kbps") preferredQuality = "128";
            else if (selectedAudioQuality === "Best Available") preferredQuality = "0";

            dlOptions = {
              format: `Audio (${selectedFormat})`,
              quality: selectedAudioQuality,
              audio_codec: codec,
              audio_quality: preferredQuality
            };
          }
          body = { track: track, url: track.spotify_url ?? url, title: track.title, options: dlOptions };
        }
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
      showToast("Download failed", "error");
    }
  }

  async function startBatchDownload() {
    if (isDownloading || selectedIndices.size === 0) return;
    isDownloading = true;
    statusText = "Starting batch download...";
    progress = 0;
    batchProgress = { completed: 0, total: selectedIndices.size, succeeded: 0, failed: 0 };
    try {
      const [codec, quality] = AUDIO_FMT_MAP[selectedFormat] ?? ["mp3", "0"];
      const selectedTracks = [...selectedIndices].sort((a, b) => a - b).map(i => playlistTracks[i]).filter(t => t !== null);
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
      showToast("Batch download failed", "error");
    }
  }

  function startPolling(id: string) {
    let cursor = 0;
    let staleTicks = 0;
    async function poll() {
      if (pollInterval !== null) { clearTimeout(pollInterval); pollInterval = null; }
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

  async function cancelDownload() {
    if (!taskId) return;
    try {
      await fetch(`${API_BASE}/task/${taskId}/cancel`, { method: 'POST' });
    } catch { /* best-effort */ }
    stopPolling();
    isDownloading = false;
    statusText = 'Cancelled';
    downloadSuccess = null;
    progress = 0;
    taskId = null;
    showToast('Download cancelled', 'cancel');
  }

  function handleEvent(payload: { type: string; message?: string; progress?: number; completed?: number; total?: number; succeeded?: number; failed?: number; success?: boolean; current_track_title?: string }) {
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
      const batchPct = batchProgress.total > 0 ? batchProgress.completed / batchProgress.total : 0;
      if (batchPct > progress) progress = batchPct;
      const current = batchProgress.completed + 1 > batchProgress.total ? batchProgress.total : batchProgress.completed + 1;
      const title = payload.current_track_title || "Track";
      statusText = `Downloading: "${title}" (${current}/${batchProgress.total})`;
    }
    else if (t === "batch_end") {
      const s = payload.succeeded ?? 0;
      const f = payload.failed ?? 0;
      statusText = `Done! ${s} succeeded${f > 0 ? `, ${f} failed` : ""}`;
      progress = 1.0;
      downloadSuccess = f === 0;
      isDownloading = false;
      if (f === 0) showToast("Download completed successfully");
      else showToast("Some downloads failed", "error");
    }
    else if (t === "complete") {
      statusText = msg;
      progress = 1.0;
      downloadSuccess = payload.success ?? true;
      isDownloading = false;
      if (isEmbeddingTask) {
        showToast("Embedded successfully");
      } else {
        showToast("Download completed successfully");
      }
    }
    else if (t === "error") {
      statusText = msg;
      downloadSuccess = false;
      isDownloading = false;
      if (isEmbeddingTask) {
        showToast("Embedding failed", "error");
      } else {
        showToast("Download failed", "error");
      }
    }
  }

  function toggleProfileMenu(e: Event) {
    e.stopPropagation();
    isProfileMenuOpen = !isProfileMenuOpen;
    activeProfileSubMenu = "main";
  }

  function closeProfileMenu() {
    isProfileMenuOpen = false;
    activeProfileSubMenu = "main";
  }

  function saveTheme() {
    localStorage.setItem("customBgColor", customBgColor);
    localStorage.setItem("customWallpaperUrl", customWallpaperUrl);
    localStorage.setItem("showBgMosaic", showBgMosaic.toString());
    localStorage.setItem("wallpaperOpacity", wallpaperOpacity.toString());
    localStorage.setItem("wallpaperBlur", wallpaperBlur.toString());
    localStorage.setItem("manualThemeOverride", manualThemeOverride);
  }

  function applyPreset(color: string, wallpaper: string) {
    customBgColor = color;
    if (wallpaper !== "") {
      customWallpaperUrl = wallpaper;
    }
    saveTheme();
  }

  function toggleManualTheme() {
    const darkPresets = ['#06070c', '#0f051d', '#05120f', '#081326', '#1d0b0b', '#111115'];
    const lightPresets = ['#f0f2f5', '#fdf6e3', '#d1fae5', '#e0f2fe', '#ffe4e6', '#e2e8f0'];
    
    let darkIndex = darkPresets.indexOf(customBgColor);
    let lightIndex = lightPresets.indexOf(customBgColor);
    if (customBgColor === "#f5f6fa") lightIndex = 0; // Legacy default light

    if (manualThemeOverride === 'light' || (manualThemeOverride !== 'dark' && isLightTheme)) {
      manualThemeOverride = 'dark';
      if (lightIndex !== -1) customBgColor = darkPresets[lightIndex];
    } else {
      manualThemeOverride = 'light';
      if (darkIndex !== -1) customBgColor = lightPresets[darkIndex];
    }

    saveTheme();
  }



  function clearWallpaper() {
    customWallpaperUrl = "";
    saveTheme();
  }

  function deleteWallpaper(event: Event, urlToDelete: string) {
    event.stopPropagation();
    customSavedWallpapers = customSavedWallpapers.filter(w => w !== urlToDelete);
    localStorage.setItem("customSavedWallpapers", JSON.stringify(customSavedWallpapers));
    if (customWallpaperUrl === urlToDelete) {
      customWallpaperUrl = "";
      saveTheme();
    }
  }

  function handleWallpaperUpload(event: Event) {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files[0]) {
      const file = input.files[0];
      const reader = new FileReader();
      reader.onload = (e) => {
        const img = new Image();
        img.onload = () => {
          const canvas = document.createElement("canvas");
          let width = img.width;
          let height = img.height;
          
          const maxDimension = 1920;
          if (width > maxDimension || height > maxDimension) {
            if (width > height) {
              height = Math.round((height * maxDimension) / width);
              width = maxDimension;
            } else {
              width = Math.round((width * maxDimension) / height);
              height = maxDimension;
            }
          }
          
          canvas.width = width;
          canvas.height = height;
          const ctx = canvas.getContext("2d");
          if (ctx) {
            ctx.drawImage(img, 0, 0, width, height);
            const compressedDataUrl = canvas.toDataURL("image/jpeg", 0.75);
            customWallpaperUrl = compressedDataUrl;
            if (!customSavedWallpapers.includes(compressedDataUrl)) {
              customSavedWallpapers = [compressedDataUrl, ...customSavedWallpapers];
              localStorage.setItem("customSavedWallpapers", JSON.stringify(customSavedWallpapers));
            }
            saveTheme();
          }
        };
        if (e.target && typeof e.target.result === 'string') {
          img.src = e.target.result;
        }
      };
      reader.readAsDataURL(file);
    }
  }

  function addCustomColor() {
    if (customBgColor && !customSavedColors.includes(customBgColor)) {
      customSavedColors = [...customSavedColors, customBgColor];
      localStorage.setItem("customSavedColors", JSON.stringify(customSavedColors));
    }
  }

  function deleteCustomColor(colorToDelete: string, e: Event) {
    e.stopPropagation();
    customSavedColors = customSavedColors.filter(c => c !== colorToDelete);
    localStorage.setItem("customSavedColors", JSON.stringify(customSavedColors));
  }

  function clearHistory() {
    isClearingHistory = true;
    searchHistory = [];
    localStorage.removeItem("searchHistory");
    setTimeout(() => {
      isClearingHistory = false;
    }, 300);
  }

  function deleteHistoryItem(item: HistoryItem) {
    searchHistory = searchHistory.filter(h => h.url !== item.url);
    localStorage.setItem("searchHistory", JSON.stringify(searchHistory));
  }

  function loadHistoryUrl(item: HistoryItem) {
    url = item.url;
    closeProfileMenu();
    inspectUrl();
  }

  async function retryLogin() {
    window.open('https://accounts.spotify.com/login', '_blank');
    needsLogin = false;
    statusMessage = "Retrying connection...";
    progress = 0;
    try {
      await fetch(`${API_BASE}/retry_login`, { method: "POST" });
    } catch (e) {
      console.error("Retry login request failed:", e);
    }
    startStatusPolling();
  }

  function handlePairingUrlChange(newUrl: string) {
    if (previewEs) {
      previewEs.close();
      previewEs = null;
    }
    pairedPreviewTrack = null;
    previewError = "";
    isFetchingPreview = false;

    const trimmed = newUrl.trim();
    if (!trimmed) return;

    const isSpotifyUrl = trimmed.includes("open.spotify.com") && trimmed.includes("/track/");
    const isYTMusicUrl = trimmed.includes("music.youtube.com");
    const isYouTubeUrl = trimmed.includes("youtube.com/watch") || trimmed.includes("youtu.be/");

    const isLink = trimmed.startsWith("http://") || trimmed.startsWith("https://") || trimmed.startsWith("www.");
    if (isLink) {
      if (!isSpotifyUrl && !isYTMusicUrl && !isYouTubeUrl) {
        previewError = "Unsupported link format for pairing";
        showToast(previewError, "error");
        return;
      }
    } else {
      if (!isSpotifyUrl && !isYTMusicUrl && !isYouTubeUrl) return;
    }

    if (track) {
      if (track.source === "spotify" && isSpotifyUrl) {
        previewError = "Please paste a YouTube or YT Music link, not another Spotify link";
        showToast(previewError, "error");
        return;
      }
      if ((track.source === "ytmusic" || track.source === "youtube" || track.source === "web") && (isYTMusicUrl || isYouTubeUrl)) {
        previewError = "Please paste a Spotify link, not another YouTube link";
        showToast(previewError, "error");
        return;
      }
    }

    isFetchingPreview = true;

    if (isYouTubeUrl && !isYTMusicUrl) {
      pairedPreviewTrack = null;
      isFetchingPreview = false;
      return;
    }

    previewEs = new EventSource(`${API_BASE}/inspect?url=${encodeURIComponent(trimmed)}`);
    previewEs.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "track") {
          pairedPreviewTrack = msg.track;
          isFetchingPreview = false;
          if (previewEs) {
            previewEs.close();
            previewEs = null;
          }
        } else if (msg.type === "error" || msg.type === "done") {
          isFetchingPreview = false;
          if (previewEs) {
            previewEs.close();
            previewEs = null;
          }
          if (msg.type === "error") {
            const cleanMsg = cleanErrorMessage(msg.message);
            previewError = cleanMsg;
            showToast(cleanMsg, "error");
          }
        }
      } catch (e) {
        isFetchingPreview = false;
        if (previewEs) {
          previewEs.close();
          previewEs = null;
        }
      }
    };
    previewEs.onerror = () => {
      isFetchingPreview = false;
      if (previewEs) {
        previewEs.close();
        previewEs = null;
      }
    };
  }

  function isPlainYouTubeUrl(u: string): boolean {
    const t = u.trim();
    return (t.includes("youtube.com/watch") || t.includes("youtu.be/")) && !t.includes("music.youtube.com");
  }

  $: handlePairingUrlChange(pairedUrl);

  $: isPairingAccepted = pairedUrl.trim() !== '' && !previewError && (
    !!pairedPreviewTrack ||
    (track?.source === 'spotify' && isPlainYouTubeUrl(pairedUrl))
  );
</script>

<svelte:window onclick={() => { closeProfileMenu(); activeDropdown = null; }} oncontextmenu={(e) => e.preventDefault()} />



<svelte:head>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet" />
</svelte:head>

{#if isDraggingOver}
  <div class="drag-overlay" transition:fade={{ duration: 200 }}>
    <div class="drag-overlay-content" transition:scale={{ start: 0.9, duration: 200 }}>
      <div class="drag-icon-wrapper">
        <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9 13h6m-3-3v6m-9 1V7a2 2 0 012-2h6l2 2h7a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
        </svg>
      </div>
      <p class="drag-title">Embed Metadata onto Audio File</p>
      {#if url.trim()}
        <p class="drag-subtitle">Drop to embed metadata from: <span class="url-preview">{url}</span></p>
      {:else}
        <p class="drag-subtitle">Drop to inspect audio file metadata</p>
      {/if}
    </div>
  </div>
{/if}

{#if appState === "loading"}
  <div class="onboarding-screen" class:light-theme={isLightTheme}>
    <div class="status-panel-wrapper">
      <div class="status-panel">
        <div class="status-gif-wrapper">
          <img src="/loader.gif" alt="" class="status-gif" />
        </div>
        <p class="status-label">{statusMessage}</p>
      </div>
    </div>

    {#if needsLogin && statusMessage.includes("FFmpeg download failed")}
      <div class="login-container">
        <p class="login-hint">
          FFmpeg could not be downloaded automatically.
          <br/>
          <a href="https://ffbinaries.com/downloads" target="_blank" rel="noopener noreferrer" style="color: #6366f1; text-decoration: underline;">
            Download FFmpeg manually
          </a>
          <br/>
          <span style="font-size: 0.75rem; color: rgba(255,255,255,0.4);">
            Place the files in ~/.ember/bin/ and restart the app.
          </span>
        </p>
        <button class="retry-btn" onclick={retryLogin}>
          Retry Download
        </button>
      </div>
    {:else if needsLogin && !statusMessage.includes("FFmpeg") && !statusMessage.includes("Fetching") && !statusMessage.includes("Almost ready") && !statusMessage.includes("Please log in")}
      <div class="login-container">
        <p class="login-hint">
          A secure browser window will open to verify your Spotify session.
          You do <strong>not</strong> need to close your existing browser.
          If a profile lock error occurs, close the browser manually and click Try Again.
          <br/><span style="font-size: 0.8rem; opacity: 0.6;">This only happens once.</span>
        </p>
        <button class="retry-btn" onclick={retryLogin}>
          Try Again
        </button>
      </div>
    {/if}
  </div>
{/if}

{#if appState === "main"}
  <div class="clock-widget" class:light-theme={isLightTheme} in:fly={{ y: 30, duration: 800, delay: 200, easing: quintOut }}>
    <div class="clock-date">
      <span class="clock-month">{clockMonth}</span>
      <span class="clock-day">{clockDay}</span>
    </div>
    <div class="clock-divider"></div>
    <div class="clock-time">{clockTime}</div>
  </div>

  {#if userProfile}
    <div class="profile-widget" class:light-theme={isLightTheme} in:fly={{ y: 30, duration: 800, delay: 200, easing: quintOut }}>
      <div class="nav-arrows-inline">
        <button class="nav-btn" onclick={goBack} disabled={!canGoBack} aria-label="Go back"><svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M 14 17 L 10.4 13.4 Q 9 12 10.4 10.6 L 14 7"/></svg></button>
        <button class="nav-btn" onclick={clearTrack} disabled={!showDetails || isDownloading || isFetching || transitioning} aria-label="Go home">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20" style="vertical-align: middle;">
            <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"></path>
            <polyline points="9 22 9 12 15 12 15 22"></polyline>
          </svg>
        </button>
        <button class="nav-btn" onclick={goForward} disabled={!canGoForward} aria-label="Go forward"><svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M 10 17 L 13.6 13.4 Q 15 12 13.6 10.6 L 10 7"/></svg></button>
      </div>
      
      <div class="profile-divider"></div>
      <button class="profile-btn" onclick={toggleProfileMenu}>
        {#if userProfile.avatar_url}
          <img class="profile-avatar" src={userProfile.avatar_url} alt="Avatar" />
        {/if}
        <span class="profile-name">{(userProfile.display_name || 'User').split(' ')[0]}</span>
      </button>
      
      {#if isProfileMenuOpen}
        <div class="profile-dropdown" role="presentation" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()} in:fly={{ y: -12, duration: 300, easing: cubicOut }} out:fly={{ y: -12, duration: 180, easing: cubicOut }}>
          {#if activeProfileSubMenu === 'main'}
            <div class="profile-submenu-container" in:fly={{ y: -12, duration: 300, easing: cubicOut }}>
              <div class="profile-menu-header">
                <span>Account Options</span>
              </div>
              <div class="profile-main-options">
                <button class="profile-opt-btn" onclick={() => activeProfileSubMenu = 'themes'}>
                  <svg class="opt-icon" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M4 12V6c0-2.2 1.8-4 4-4h1c.3 0 .5.2.5.5v3c0 .8.7 1.5 1.5 1.5s1.5-.7 1.5-1.5v-3c0-.3.2-.5.5-.5h4c1.6 0 3 1.4 3 3v6H4z" />
                    <rect x="3" y="13" width="18" height="4" rx="2" />
                    <path d="M9 17v4c0 1.65 1.35 3 3 3s3-1.35 3-3v-4H9z" />
                  </svg>
                  <div class="opt-text">
                    <span class="opt-title">Themes</span>
                    <span class="opt-desc">Customize background & wallpaper</span>
                  </div>
                  <svg class="opt-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>
                </button>

                <button class="profile-opt-btn" onclick={() => activeProfileSubMenu = 'history'}>
                  <svg class="opt-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="10" />
                    <polyline points="12 6 12 12 16 14" />
                  </svg>
                  <div class="opt-text">
                    <span class="opt-title">History</span>
                    <span class="opt-desc">View and manage search history</span>
                  </div>
                  <svg class="opt-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>
                </button>

                <button class="profile-opt-btn" onclick={() => activeProfileSubMenu = 'about'}>
                  <svg class="opt-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="16" x2="12" y2="12" />
                    <line x1="12" y1="8" x2="12.01" y2="8" />
                  </svg>
                  <div class="opt-text">
                    <span class="opt-title">About</span>
                    <span class="opt-desc">App details and information</span>
                  </div>
                  <svg class="opt-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>
                </button>
              </div>
            </div>
          {:else if activeProfileSubMenu === 'themes'}
            <div class="profile-submenu-container" in:fly={{ y: -12, duration: 300, easing: cubicOut }}>
              <div class="profile-menu-header">
                <button class="menu-back-btn" onclick={() => activeProfileSubMenu = 'main'} title="Back">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="19" y1="12" x2="5" y2="12" />
                    <polyline points="12 19 5 12 12 5" />
                  </svg>
                </button>
                <span class="centered-header-title">Themes</span>
                <button class="theme-slider-toggle" onclick={toggleManualTheme} class:light-active={isLightTheme} title="Toggle Light/Dark Mode">
                  <svg class="slider-icon moon-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
                  </svg>
                  
                  <svg class="slider-icon sun-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="4" />
                    <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
                  </svg>
                  
                  <div class="slider-thumb"></div>
                </button>
              </div>
              <div class="profile-theme-content">
                <div class="theme-option-group">
                  <span class="theme-group-label">Background Color</span>
                  <div class="circular-color-picker-group">
                    <div class="circular-color-input-wrapper">
                      <svg viewBox="0 0 24 24" width="34" height="34" style="display: block; width: 100%; height: 100%;">
                        <path d="M12 12 L12 2 A10 10 0 0 1 20.66 7 L12 12" fill="#ff4d4d"/>
                        <path d="M12 12 L20.66 7 A10 10 0 0 1 20.66 17 L12 12" fill="#ffeb3b"/>
                        <path d="M12 12 L20.66 17 A10 10 0 0 1 12 22 L12 12" fill="#4caf50"/>
                        <path d="M12 12 L12 22 A10 10 0 0 1 3.34 17 L12 12" fill="#00bcd4"/>
                        <path d="M12 12 L3.34 17 A10 10 0 0 1 3.34 7 L12 12" fill="#2196f3"/>
                        <path d="M12 12 L3.34 7 A10 10 0 0 1 12 2 L12 12" fill="#9c27b0"/>
                        <circle cx="12" cy="12" r="3.5" fill="#111115" />
                      </svg>
                      <input type="color" bind:value={customBgColor} class="theme-color-input-circular" oninput={saveTheme} />
                    </div>
                    <input type="text" bind:value={customBgColor} class="theme-color-text-input" oninput={saveTheme} placeholder="#06070c" />
                  </div>
                </div>

                <div class="theme-option-group">
                  <div class="custom-colors-header">
                    <span class="theme-group-label" style="margin-bottom: 0;">Saved Colors</span>
                    <button class="add-color-btn" onclick={addCustomColor} title="Save Current Color">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="13" height="13">
                        <line x1="12" y1="5" x2="12" y2="19" />
                        <line x1="5" y1="12" x2="19" y2="12" />
                      </svg>
                      <span>Save</span>
                    </button>
                  </div>
                  <div class="custom-colors-grid">
                    {#each customSavedColors as color}
                      <div class="custom-color-item" role="button" tabindex="0" style="background-color: {color}" onclick={() => applyPreset(color, customWallpaperUrl)} onkeydown={(e) => e.key === 'Enter' && applyPreset(color, customWallpaperUrl)} title={color}>
                        <button class="delete-color-btn" onclick={(e) => deleteCustomColor(color, e)} title="Delete Color">
                          ✕
                        </button>
                      </div>
                    {/each}
                  </div>
                </div>

                <div class="theme-option-group">
                  <span class="theme-group-label">Wallpaper</span>
                  <div class="wallpaper-trigger-wrapper">
                    <button class="select-wallpaper-trigger-btn" onclick={() => activeProfileSubMenu = 'wallpapers'} title="Select Wallpaper">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" width="15" height="15" style="vertical-align: middle; margin-right: 6px;">
                        <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                        <circle cx="8.5" cy="8.5" r="1.5" />
                        <polyline points="21 15 16 10 5 21" />
                      </svg>
                      <span>{customWallpaperUrl ? 'Change Wallpaper' : 'Select Wallpaper'}</span>
                    </button>
                    {#if customWallpaperUrl}
                      <button class="clear-wallpaper-btn-modern" onclick={clearWallpaper} title="Remove Wallpaper">✕</button>
                    {/if}
                  </div>
                </div>

                <div class="theme-option-group">
                  <div class="mosaic-toggle-wrapper">
                    <span class="theme-group-label" style="margin-bottom: 0;">Show Background Mosaic</span>
                    <button class="mosaic-checkbox-btn" onclick={() => { showBgMosaic = !showBgMosaic; saveTheme(); }} title="Toggle Background Icons">
                      <div class="custom-checkbox" class:checked={showBgMosaic}>
                        {#if showBgMosaic}
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="20 6 9 17 4 12" />
                          </svg>
                        {/if}
                      </div>
                    </button>
                  </div>
                </div>

                <div class="theme-option-group">
                  <span class="theme-group-label">Presets</span>
                  <div class="theme-presets-grid">
                    {#if isLightTheme}
                      <button class="preset-btn" class:active={customBgColor === '#f0f2f5'} onclick={() => applyPreset('#f0f2f5', '')}>Default</button>
                      <button class="preset-btn" class:active={customBgColor === '#fdf6e3'} onclick={() => applyPreset('#fdf6e3', '')}>Ivory</button>
                      <button class="preset-btn" class:active={customBgColor === '#d1fae5'} onclick={() => applyPreset('#d1fae5', '')}>Mint</button>
                      <button class="preset-btn" class:active={customBgColor === '#e0f2fe'} onclick={() => applyPreset('#e0f2fe', '')}>Sky</button>
                      <button class="preset-btn" class:active={customBgColor === '#ffe4e6'} onclick={() => applyPreset('#ffe4e6', '')}>Rose</button>
                      <button class="preset-btn" class:active={customBgColor === '#e2e8f0'} onclick={() => applyPreset('#e2e8f0', '')}>Slate</button>
                    {:else}
                      <button class="preset-btn" class:active={customBgColor === '#06070c'} onclick={() => applyPreset('#06070c', '')}>Default</button>
                      <button class="preset-btn" class:active={customBgColor === '#0f051d'} onclick={() => applyPreset('#0f051d', '')}>Midnight</button>
                      <button class="preset-btn" class:active={customBgColor === '#05120f'} onclick={() => applyPreset('#05120f', '')}>Forest</button>
                      <button class="preset-btn" class:active={customBgColor === '#081326'} onclick={() => applyPreset('#081326', '')}>Ocean</button>
                      <button class="preset-btn" class:active={customBgColor === '#1d0b0b'} onclick={() => applyPreset('#1d0b0b', '')}>Sunset</button>
                      <button class="preset-btn" class:active={customBgColor === '#111115'} onclick={() => applyPreset('#111115', '')}>Carbon</button>
                    {/if}
                  </div>
                </div>
              </div>
            </div>
          {:else if activeProfileSubMenu === 'about'}
            <div class="profile-submenu-container" in:fly={{ y: -12, duration: 300, easing: cubicOut }}>
              <div class="profile-menu-header">
                <button class="menu-back-btn" onclick={() => activeProfileSubMenu = 'main'} title="Back">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="19" y1="12" x2="5" y2="12" />
                    <polyline points="12 19 5 12 12 5" />
                  </svg>
                </button>
                <span class="centered-header-title">About</span>
                <div style="width: 32px;"></div>
              </div>
              <div class="profile-about-content">
                <div class="about-logo">Ember</div>
                <div class="about-tagline">Yours, forever.</div>
                <div class="about-version">v1.0.0</div>
                <div class="about-info-grid">
                  <div class="about-developer-card">
                    <img class="about-avatar" src={GITHUB_AVATAR_URL} alt="Shikhar Upadhyay" />
                    <div class="about-developer-info">
                      <span class="about-developer-name">Shikhar Upadhyay</span>
                      <span class="about-developer-handle">@{GITHUB_USERNAME}</span>
                    </div>
                    <button class="about-github-btn" onclick={() => openExternalUrl(GITHUB_PROFILE_URL)} title="View GitHub Profile">
                      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                        <path d="M12 0C5.37 0 0 5.37 0 12c0 5.3 3.438 9.8 8.205 11.387.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61-.546-1.385-1.333-1.755-1.333-1.755-1.09-.744.083-.729.083-.729 1.205.084 1.84 1.237 1.84 1.237 1.07 1.834 2.807 1.304 3.492.997.108-.775.42-1.305.763-1.605-2.665-.303-5.467-1.334-5.467-5.93 0-1.31.468-2.38 1.235-3.22-.123-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23a11.5 11.5 0 0 1 3.003-.404c1.02.005 2.047.138 3.003.404 2.291-1.552 3.297-1.23 3.297-1.23.654 1.653.242 2.874.12 3.176.77.84 1.233 1.91 1.233 3.22 0 4.61-2.807 5.625-5.48 5.921.432.372.816 1.103.816 2.222 0 1.606-.015 2.896-.015 3.286 0 .32.216.694.825.576C20.565 21.795 24 17.295 24 12c0-6.63-5.37-12-12-12z"/>
                      </svg>
                      <span>GitHub</span>
                    </button>
                  </div>

                  <div class="divider about-divider-thin"></div>

                  <div class="about-meta-grid">
                    <span class="meta-key">Platform</span><span class="meta-val">{detectedOS}</span>
                    <span class="meta-key">License</span><span class="meta-val">MIT</span>
                  </div>
                  
                  <div class="divider about-divider-thin"></div>

                  <button class="about-github-btn" onclick={() => openExternalUrl('https://github.com/shikhar0x/ember/releases')} title="Check for updates">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <polyline points="23 4 23 10 17 10"></polyline>
                      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
                    </svg>
                    <span>Check for updates</span>
                  </button>
                </div>
              </div>
            </div>
          {:else if activeProfileSubMenu === 'history'}
            <div class="profile-submenu-container" in:fly={{ y: -12, duration: 300, easing: cubicOut }}>
              <div class="profile-menu-header">
                <button class="menu-back-btn" onclick={() => activeProfileSubMenu = 'main'} title="Back">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="19" y1="12" x2="5" y2="12" />
                    <polyline points="12 19 5 12 12 5" />
                  </svg>
                </button>
                <span>Search History</span>
                {#if searchHistory.length > 0}
                  <button class="clear-history-btn" onclick={clearHistory} title="Clear History">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"></path>
                    </svg>
                  </button>
                {:else}
                  <div style="width: 32px;"></div>
                {/if}
              </div>
              <div class="profile-menu-list">
                {#if searchHistory.length === 0 && !isClearingHistory}
                  <div class="profile-menu-empty" transition:fade={{ duration: 150 }}>No history yet</div>
                {/if}
                {#each searchHistory as h (h.url)}
                  <div class="history-item-container" transition:historyTransition>
                    <button class="profile-menu-item history-item" onclick={() => loadHistoryUrl(h)} title={h.url}>
                      <div class="history-cover-wrapper">
                        {#if h.cover_url}
                          <img class="history-cover" src={h.cover_url} alt="Cover" />
                        {:else}
                          <div class="history-cover-placeholder">
                            {#if h.type === 'playlist'}
                              <svg class="history-icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <line x1="8" y1="6" x2="21" y2="6" />
                                <line x1="8" y1="12" x2="21" y2="12" />
                                <line x1="8" y1="18" x2="21" y2="18" />
                                <line x1="3" y1="6" x2="3.01" y2="6" />
                                <line x1="3" y1="12" x2="3.01" y2="12" />
                                <line x1="3" y1="18" x2="3.01" y2="18" />
                              </svg>
                            {:else if h.type === 'album'}
                              <svg class="history-icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <circle cx="12" cy="12" r="10" />
                                <circle cx="12" cy="12" r="3" />
                              </svg>
                            {:else if h.type === 'video'}
                              <svg class="history-icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <rect x="2" y="2" width="20" height="20" rx="5" ry="5" />
                                <polygon points="10.5 9 14.5 12 10.5 15" />
                              </svg>
                            {:else}
                              <svg class="history-icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M9 18V5l12-2v13" />
                                <circle cx="6" cy="18" r="3" />
                                <circle cx="18" cy="16" r="3" />
                              </svg>
                            {/if}
                          </div>
                        {/if}
                      </div>
                      <div class="history-info">
                        {#if h.title}
                          <span class="history-title">{h.title}</span>
                        {/if}
                        <span class="history-url">{h.url}</span>
                      </div>
                    </button>
                    <button class="delete-history-item-btn" onclick={(e) => { e.stopPropagation(); deleteHistoryItem(h); }} title="Delete from history">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="18" y1="6" x2="6" y2="18" />
                        <line x1="6" y1="6" x2="18" y2="18" />
                      </svg>
                    </button>
                  </div>
                {/each}
              </div>
            </div>
          {:else if activeProfileSubMenu === 'wallpapers'}
            <div class="profile-submenu-container" in:fly={{ y: -12, duration: 300, easing: cubicOut }}>
              <div class="profile-menu-header">
                <button class="menu-back-btn" onclick={() => activeProfileSubMenu = 'themes'} title="Back to Themes">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="19" y1="12" x2="5" y2="12" />
                    <polyline points="12 19 5 12 12 5" />
                  </svg>
                </button>
                <span class="centered-header-title">Wallpapers</span>
                <div style="width: 32px;"></div>
              </div>
              <div class="profile-menu-list wallpapers-preset-list">
                <div class="wallpapers-grid">
                  <input type="file" id="wallpaper-file-input" accept="image/*" onchange={handleWallpaperUpload} style="display: none;" />
                  <div class="wallpaper-card add-card" role="button" tabindex="0" onclick={() => document.getElementById('wallpaper-file-input')?.click()} onkeydown={(e) => e.key === 'Enter' && document.getElementById('wallpaper-file-input')?.click()} title="Add Custom Wallpaper">
                    <div class="wallpaper-add-placeholder">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="22" height="22">
                        <line x1="12" y1="5" x2="12" y2="19" />
                        <line x1="5" y1="12" x2="19" y2="12" />
                      </svg>
                    </div>
                    <div class="wallpaper-overlay">
                      <span class="wallpaper-name">Add</span>
                    </div>
                  </div>

                  <div class="wallpaper-card none-card" role="button" tabindex="0" class:active={!customWallpaperUrl} onclick={clearWallpaper} onkeydown={(e) => e.key === 'Enter' && clearWallpaper()} title="No Wallpaper">
                    <div class="wallpaper-none-placeholder">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="20" height="20">
                        <circle cx="12" cy="12" r="10" />
                        <line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
                      </svg>
                    </div>
                    <div class="wallpaper-overlay">
                      <span class="wallpaper-name">None</span>
                      {#if !customWallpaperUrl}
                        <svg class="wallpaper-check-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      {/if}
                    </div>
                  </div>

                  {#each WALLPAPER_PRESETS as wp}
                    <div class="wallpaper-card" role="button" tabindex="0" class:active={customWallpaperUrl === wp.url} onclick={() => applyPreset(customBgColor, wp.url)} onkeydown={(e) => e.key === 'Enter' && applyPreset(customBgColor, wp.url)} title={wp.name}>
                      <img class="wallpaper-thumb" src={wp.thumbnail} alt={wp.name} loading="lazy" />
                      <div class="wallpaper-overlay">
                        <span class="wallpaper-name">{wp.name}</span>
                        {#if customWallpaperUrl === wp.url}
                          <svg class="wallpaper-check-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="20 6 9 17 4 12" />
                          </svg>
                        {/if}
                      </div>
                    </div>
                  {/each}

                  {#each customSavedWallpapers as cwp}
                    <div class="wallpaper-card custom-wallpaper-card" role="button" tabindex="0" class:active={customWallpaperUrl === cwp} onclick={() => applyPreset(customBgColor, cwp)} onkeydown={(e) => e.key === 'Enter' && applyPreset(customBgColor, cwp)} title="Custom Wallpaper">
                      <img class="wallpaper-thumb" src={cwp} alt="Custom" loading="lazy" />
                      <div class="wallpaper-overlay">
                        <span class="wallpaper-name">Custom</span>
                        {#if customWallpaperUrl === cwp}
                          <svg class="wallpaper-check-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="20 6 9 17 4 12" />
                          </svg>
                        {/if}
                        <button class="delete-wallpaper-btn" onclick={(e) => deleteWallpaper(e, cwp)} title="Delete wallpaper">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                            <line x1="18" y1="6" x2="6" y2="18"></line>
                            <line x1="6" y1="6" x2="18" y2="18"></line>
                          </svg>
                        </button>
                      </div>
                    </div>
                  {/each}
                </div>
                {#if customWallpaperUrl}
                  <div class="wallpaper-slider-group">
                    <div class="slider-header">
                      <span class="theme-group-label" style="margin-bottom: 0;">Wallpaper Opacity</span>
                      <span class="slider-val">{wallpaperOpacity}%</span>
                    </div>
                    <input type="range" min="10" max="100" step="5" bind:value={wallpaperOpacity} oninput={saveTheme} class="theme-slider" />
                  </div>
                  
                  <div class="wallpaper-slider-group">
                    <div class="slider-header">
                      <span class="theme-group-label" style="margin-bottom: 0;">Wallpaper Blur</span>
                      <span class="slider-val">{wallpaperBlur}px</span>
                    </div>
                    <input type="range" min="0" max="15" step="1" bind:value={wallpaperBlur} oninput={saveTheme} class="theme-slider" />
                  </div>
                {/if}
              </div>
            </div>
          {/if}
        </div>
      {/if}
    </div>
  {/if}
{/if}

<main class="container" class:light-theme={isLightTheme} style="--custom-bg: {customBgColor};">
  {#if customWallpaperUrl}
    <div class="custom-wallpaper-bg" style="opacity: {wallpaperOpacity / 100}; filter: blur({wallpaperBlur}px); background-image: url({customWallpaperUrl});" aria-hidden="true"></div>
  {/if}
  <div class="bg-mosaic-container" style="opacity: {showBgMosaic ? 1 : 0}; transition: opacity 0.5s ease; pointer-events: none;" aria-hidden="true">
    <div class="bg-mosaic-grid">
      {#each [...Array(48)] as _, i}
        <div class="bg-mosaic-item type-{i % 3}">
          {#if i % 3 === 0}
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
              <circle cx="12" cy="12" r="10" />
              <circle cx="12" cy="12" r="5" />
              <polygon points="11 10.2 13.8 12 11 13.8" fill="currentColor" />
            </svg>
          {:else if i % 3 === 1}
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
              <path d="M22.54 6.42a2.78 2.78 0 0 0-1.95-1.96C18.88 4 12 4 12 4s-6.88 0-8.59.46a2.78 2.78 0 0 0-1.95 1.96A29 29 0 0 0 1 12a29 29 0 0 0 .46 5.58 2.78 2.78 0 0 0 1.95 1.96C5.12 20 12 20 12 20s6.88 0 8.59-.46a2.78 2.78 0 0 0 1.95-1.96A29 29 0 0 0 23 12a29 29 0 0 0-.46-5.58z" />
              <polygon points="9.75 8.5 15.5 12 9.75 15.5" fill="currentColor" />
            </svg>
          {:else}
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round">
              <circle cx="12" cy="12" r="10" />
              <path d="M7.5 9c2.5-0.8 6.5-0.8 9 0" />
              <path d="M8.2 11.5c2-0.6 5.6-0.6 7.6 0" />
              <path d="M9 14c1.5-0.4 4.5-0.4 6 0" />
            </svg>
          {/if}
        </div>
      {/each}
    </div>
  </div>
  {#if appState === "main"}
  <div class="content-wrapper" class:wide={isExpanding}>
    <header class:compact={isExpanding} in:fly={{ y: 30, duration: 800, easing: quintOut }}>
      {#if isExpanding}
        <div class="input-group top-bar-input" class:exit={isTransitioningToHome} transition:fade={{ duration: 300 }}>
          <div class="input-wrapper" role="group" onmouseenter={() => isInputHovered = true} onmouseleave={() => isInputHovered = false}>
            <input
              type="text"
              placeholder="Paste Spotify, YouTube Music, or YouTube link here..."
              value={(isUrlFocused || isFetching) ? url : (track?.title || playlistTitle || url)}
              onfocus={(e) => { isUrlFocused = true; setTimeout(() => e.currentTarget.select(), 0); }}
              onblur={() => { isUrlFocused = false; }}
              oninput={(e) => { url = e.currentTarget.value; }}
              onkeydown={(e) => {
                if (e.key === 'Enter') {
                  e.currentTarget.blur();
                  inspectUrl();
                } else {
                  handleKeydown(e);
                }
              }}
              disabled={isBusy}
              class:locked={isBusy}
            />
            {#if isFetching}
              <img class="search-icon-gif" src="/loader.gif" alt="Loading" transition:fade={{ duration: 150 }} />
            {:else}
              <svg class="search-icon" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" transition:fade={{ duration: 150 }}>
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            {/if}
            <span class="search-divider">|</span>
            {#if url && !isBusy && (!showDetails || isUrlFocused || isInputHovered)}
              <button class="clear-url-btn" onclick={handleClearUrl} disabled={isBusy} title="Clear URL" transition:fade={{ duration: 150 }}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="clear-url-svg"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></button>
            {/if}
          </div>
        </div>
      {:else}
        <h1>Ember</h1>
        <p class="subtitle">Yours, forever.</p>
      {/if}
    </header>

    {#if !showDetails && !isFetching}
      <div class="glass-card" class:exit={transitioning}>
        {#if !isFetching}
          <div class="input-group" in:fly={{ y: 30, duration: 800, delay: 100, easing: quintOut }}>
            <div class="input-wrapper" role="group" onmouseenter={() => isInputHovered = true} onmouseleave={() => isInputHovered = false}>
              <input
                type="text"
                placeholder="Paste Spotify, YouTube Music, or YouTube link here..."
                bind:value={url}
                disabled={isBusy}
                class:locked={isBusy}
                onkeydown={handleKeydown}
              />
              <svg class="search-icon" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <span class="search-divider">|</span>
              {#if url && !isBusy && (!showDetails || isUrlFocused || isInputHovered)}
                <button class="clear-url-btn" onclick={handleClearUrl} disabled={isBusy} title="Clear URL" transition:fade={{ duration: 150 }}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="clear-url-svg"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></button>
              {/if}
            </div>
            <button
              onclick={inspectUrl}
              disabled={isBusy || !url}
              class:loading={isBusy}
            >
              <span class="btn-text">{isFetching ? "Inspecting..." : "Inspect"}</span>
              <div class="btn-glow"></div>
            </button>
          </div>
        {/if}

        {#if !isFetching}
          <div class="drag-hint" in:fly={{ y: 20, duration: 600, delay: 300, easing: quintOut }}>
            <span class="drag-hint-icon">🎵</span>
            <span class="drag-hint-text">Drag & drop an MP3/FLAC here to embed metadata</span>
          </div>
        {/if}

        {#if fetchError}
          <details class="fetch-error-details" style="margin-bottom: 1rem;">
            <summary class="fetch-error-summary">⚠ Error</summary>
            <div class="fetch-error-content">{fetchError}</div>
          </details>
        {/if}

        <div class="status-panel-wrapper">
          <div class="status-panel" class:active={isFetching}>
            <div class="status-gif-wrapper" class:active={isFetching}>
              <img src="/loader.gif" alt="Status" class="status-gif" />
            </div>
            <p class="status-label">{isFetching ? statusText : getIdleText()}</p>
          </div>
        </div>
        
        {#if needsLogin && !statusMessage.includes("Fetching") && !statusMessage.includes("Almost ready") && !statusMessage.includes("Please log in")}
          <div class="login-container">
            <p class="login-hint">
              A secure browser window will open to verify your Spotify session.
              You do <strong>not</strong> need to close your existing browser.
              If a profile lock error occurs, close the browser manually and click Try Again.
              <br/><span style="font-size: 0.8rem; opacity: 0.6;">This only happens once.</span>
            </p>
            <button class="retry-btn" onclick={retryLogin}>
              Try Again
            </button>
          </div>
        {/if}
      </div>
    {/if}

    {#if isExpanding}
      <div class="details-layout" class:exit={transitioning}>
        {#if !isFetching && track?.cover_url}
          <div class="details-backdrop" style="background-image: url({track.cover_url});"></div>
        {:else if !isFetching && playlistCover}
          <div class="details-backdrop" style="background-image: url({playlistCover});"></div>
        {/if}

        <div class="cover-col">
          {#if isFetching && !track && !isPlaylist}
            <div class="cover-placeholder skeleton-pulse">
              <span class="skeleton-icon spinning">⟳</span>
            </div>
          {:else if track}
            {#if track.cover_url}
              <img class="cover-img" src={track.cover_url} alt="Album cover" />
            {:else}
              <div class="cover-placeholder">♪</div>
            {/if}
            {#if track.cover_url}
              <button class="save-cover-btn" onclick={saveCover} disabled={isSavingCover} class:saved={coverSaved}>
                {#if coverSaved}
                  <span class="cover-btn-icon">✓</span><span>Saved!</span>
                {:else if isSavingCover}
                  <span class="cover-btn-icon spinning">⟳</span><span>Saving...</span>
                {:else}
                  <span class="cover-btn-icon">↓</span><span>Save Cover</span>
                {/if}
              </button>
            {/if}
          {:else if isPlaylist}
            {#if playlistCover}
              <img class="cover-img" src={playlistCover} alt="Cover" />
            {:else}
              <div class="cover-placeholder">♪</div>
            {/if}
            {#if playlistCover}
              <button class="save-cover-btn" onclick={saveCover} disabled={isSavingCover} class:saved={coverSaved}>
                {#if coverSaved}<span class="cover-btn-icon">✓</span><span>Saved!</span>{:else if isSavingCover}<span class="cover-btn-icon spinning">⟳</span><span>Saving...</span>{:else}<span class="cover-btn-icon">↓</span><span>Save Cover</span>{/if}
              </button>
            {/if}
          {/if}
        </div>

        <div class="meta-col">
          {#if isFetching && !track && !isPlaylist}
            <div class="meta-header">
              <div class="skeleton-line title-skeleton"></div>
            </div>
            <div class="meta-top">
              <div class="skeleton-line artist-skeleton"></div>
              <div class="divider"></div>
              <div class="meta-grid">
                <span class="meta-key">Source</span><span class="meta-val skeleton-text">Inspecting link...</span>
                <span class="meta-key">Status</span><span class="meta-val skeleton-text">{statusText}</span>
              </div>
            </div>
            <div class="meta-bottom">
              <div class="divider"></div>
            </div>
          {:else if track}
            <div class="meta-header">
              <h2 class="track-title">{track.title}</h2>
            </div>
            <div class="meta-top">
              <p class="track-artist">{track.artists.length > 1 ? track.artists.slice(0,-1).join(', ') + ' & ' + track.artists.at(-1) : track.artists[0]}</p>
              <div class="divider"></div>
              <div class="meta-grid">
                {#if track.album}<span class="meta-key">Album</span><span class="meta-val">{track.album}</span>{/if}
                {#if track.year}<span class="meta-key">Year</span><span class="meta-val">{track.year}</span>{/if}
                {#if track.duration}<span class="meta-key">Duration</span><span class="meta-val">{formatDuration(track.duration)}</span>{/if}
                {#if track.track_number}<span class="meta-key">Track</span><span class="meta-val">{track.track_number}{track.total_tracks ? ` / ${track.total_tracks}` : ''}</span>{/if}
                {#if track.genre}<span class="meta-key">Genre</span><span class="meta-val">{track.genre}</span>{/if}
                {#if track.isrc && track.source === 'spotify'}<span class="meta-key">ISRC</span><span class="meta-val mono">{track.isrc}</span>{:else if track.source === 'spotify'}<span class="meta-key">ISRC</span><span class="meta-val muted">—</span>{/if}
              </div>
            </div>
            <div class="meta-bottom">
              <div class="divider"></div>
              <div class="progress-row">
                <div class="progress-track">
                  <div class="progress-fill" style="width: {isDownloading && progress === 0 ? 5 : Math.max(0, progress * 100)}%;" class:active={isDownloading && progress < 1.0} class:complete={progress >= 1.0}></div>
                </div>
                {#if isDownloading}
                  <button class="cancel-btn" onclick={cancelDownload} aria-label="Cancel download">✕</button>
                {/if}
              </div>
              <div class="dl-row">
                <p class="status-label" class:error={downloadSuccess === false}>{statusText}</p>
                {#if isDownloading}<span class="progress-percent">{Math.round(progress * 100)}%</span>{/if}
              </div>
              {#if (track.source === 'spotify' || track.source === 'ytmusic' || track.source === 'local' || track.source === 'youtube' || track.source === 'web') && selectedDownloadType !== 'video'}
                <div class="pairing-container" transition:slide={{ duration: 250, easing: cubicOut }}>
                  <div class="pairing-input-wrapper">
                    <span class="pairing-icon">🔗</span>
                    <input
                      type="text"
                      class="pairing-input"
                      placeholder={track.source === 'local' ? "Paste Spotify/YTMusic URL to copy tags from..." : (track.source === 'ytmusic' || track.source === 'youtube' || track.source === 'web' ? "Paste a Spotify URL for metadata..." : "Paste a YouTube or YT Music URL...")}
                      bind:value={pairedUrl}
                      disabled={isDownloading}
                    />
                    {#if pairedUrl}
                      <button class="clear-pairing-btn" onclick={() => pairedUrl = ""} disabled={isDownloading}>✕</button>
                    {/if}
                  </div>

                  {#if isFetchingPreview}
                    <div class="preview-status" transition:fade>
                      <span class="spinner-icon">⟳</span>
                      <span>Resolving metadata preview...</span>
                    </div>
                  {:else if previewError}
                    <div class="preview-error" transition:fade>
                      <span>⚠ {previewError}</span>
                    </div>
                  {:else if pairedPreviewTrack}
                    <div class="metadata-preview-card" transition:slide={{ duration: 250 }}>
                      <div class="preview-header">
                        <span class="preview-badge">Metadata Preview</span>
                        {#if pairedPreviewTrack.source === 'spotify'}
                          <span class="preview-source-badge spotify">Spotify</span>
                        {:else if pairedPreviewTrack.source === 'ytmusic'}
                          <span class="preview-source-badge ytmusic">YouTube Music</span>
                        {:else}
                          <span class="preview-source-badge youtube">YouTube</span>
                        {/if}
                      </div>
                      <div class="preview-body">
                        {#if pairedPreviewTrack.cover_url}
                          <img class="preview-cover-img" src={pairedPreviewTrack.cover_url} alt="Cover Preview" />
                        {:else}
                          <div class="preview-cover-placeholder">♪</div>
                        {/if}
                        <div class="preview-details">
                          <div class="preview-title">{pairedPreviewTrack.title}</div>
                          <div class="preview-artist">
                            {pairedPreviewTrack.artists.length > 1 ? pairedPreviewTrack.artists.slice(0,-1).join(', ') + ' & ' + pairedPreviewTrack.artists.at(-1) : pairedPreviewTrack.artists[0]}
                          </div>
                          {#if pairedPreviewTrack.album}
                            <div class="preview-album">Album: {pairedPreviewTrack.album}</div>
                          {/if}
                          {#if pairedPreviewTrack.year}
                            <div class="preview-year">Year: {pairedPreviewTrack.year}</div>
                          {/if}
                        </div>
                      </div>
                    </div>
                  {/if}
                </div>
              {/if}
              {#if track.source !== 'local'}
                {#if track.source === 'spotify' || track.source === 'ytmusic' || (isPairingAccepted && (track.source === 'youtube' || track.source === 'web'))}
                  <div class="dl-btn-group" class:paired-flow={isPairingAccepted}>
                    {#if isPairingAccepted}
                      <div class="custom-dropdown-container">
                        <button class="format-select" class:open={activeDropdown === 'format_1'} style="--rotation: {menuRotations['format_1'] || 0}deg" disabled={isDownloading} onclick={(e) => { e.stopPropagation(); activeDropdown = activeDropdown === 'format_1' ? null : 'format_1'; }}>
                          {selectedFormat}
                        </button>
                        {#if activeDropdown === 'format_1'}
                          <div class="custom-dropdown-menu" transition:fly={{ y: 12, duration: 400, easing: cubicOut }}>
                            {#each Object.keys(AUDIO_FMT_MAP) as fmt}
                              <button class="custom-dropdown-item" onclick={() => { selectedFormat = fmt; activeDropdown = null; }}>
                                {fmt}
                              </button>
                            {/each}
                          </div>
                        {/if}
                      </div>
                      <div class="dl-btn-pair">
                        {#if track.source === 'spotify'}
                          <button class="dl-btn secondary-dl" onclick={() => startDownloadWithPairing(false)} disabled={isDownloading}>
                            <span class="btn-text">Auto-Match & Download</span>
                          </button>
                          <button class="dl-btn primary-dl" onclick={() => startDownloadWithPairing(true)} disabled={isDownloading} class:downloading={isDownloading}>
                            <span class="btn-text">{isDownloading ? "Downloading..." : "Download & Embed via Link"}</span>
                            <div class="btn-glow"></div>
                          </button>
                        {:else}
                          <button class="dl-btn secondary-dl" onclick={() => startDownloadWithPairing(false)} disabled={isDownloading}>
                            <span class="btn-text">Download with YT Embeddings</span>
                          </button>
                          <button class="dl-btn primary-dl" onclick={() => startDownloadWithPairing(true)} disabled={isDownloading} class:downloading={isDownloading}>
                            <span class="btn-text">{isDownloading ? "Downloading..." : "Download with Spotify Embeddings"}</span>
                            <div class="btn-glow"></div>
                          </button>
                        {/if}
                      </div>
                    {:else}
                      <div class="custom-dropdown-container">
                        <button class="format-select" class:open={activeDropdown === 'format_2'} style="--rotation: {menuRotations['format_2'] || 0}deg" disabled={isDownloading} onclick={(e) => { e.stopPropagation(); activeDropdown = activeDropdown === 'format_2' ? null : 'format_2'; }}>
                          {selectedFormat}
                        </button>
                        {#if activeDropdown === 'format_2'}
                          <div class="custom-dropdown-menu" transition:fly={{ y: 12, duration: 400, easing: cubicOut }}>
                            {#each Object.keys(AUDIO_FMT_MAP) as fmt}
                              <button class="custom-dropdown-item" onclick={() => { selectedFormat = fmt; activeDropdown = null; }}>
                                {fmt}
                              </button>
                            {/each}
                          </div>
                        {/if}
                      </div>
                      <button class="dl-btn" onclick={() => startDownloadWithPairing(false)} disabled={isDownloading || (pairedUrl.trim() !== '' && !isPairingAccepted && !isFetchingPreview)} class:downloading={isDownloading}>
                        <span class="btn-text">{isDownloading ? "Downloading..." : "Download"}</span>
                        <div class="btn-glow"></div>
                      </button>
                    {/if}
                  </div>
                {:else}
                  <div class="yt-controls">
                    <div class="yt-format-row">
                      <div class="format-slider" style="transform: translateX({selectedDownloadType === 'video' ? 'calc(100% + 3px)' : '0%'})"></div>
                      <button
                        type="button"
                        class="format-tab"
                        class:active={selectedDownloadType === "audio"}
                        onclick={() => { selectedDownloadType = "audio"; }}
                        disabled={isDownloading}
                      >Audio</button>
                      <button
                        type="button"
                        class="format-tab"
                        class:active={selectedDownloadType === "video"}
                        onclick={() => { selectedDownloadType = "video"; }}
                        disabled={isDownloading}
                      >Video</button>
                    </div>
                    
                    <div class="dl-btn-group">
                      <div class="custom-dropdown-container format-collapse" class:collapsed={selectedDownloadType !== "audio"}>
                        <button class="format-select" class:open={activeDropdown === 'format_2'} style="--rotation: {menuRotations['format_2'] || 0}deg" disabled={isDownloading || selectedDownloadType !== "audio"} onclick={(e) => { e.stopPropagation(); activeDropdown = activeDropdown === 'format_2' ? null : 'format_2'; }}>
                          {selectedFormat}
                        </button>
                        {#if activeDropdown === 'format_2'}
                          <div class="custom-dropdown-menu" transition:fly={{ y: 12, duration: 400, easing: cubicOut }}>
                            {#each Object.keys(AUDIO_FMT_MAP) as fmt}
                              <button class="custom-dropdown-item" onclick={() => { selectedFormat = fmt; activeDropdown = null; }}>
                                {fmt}
                              </button>
                            {/each}
                          </div>
                        {/if}
                      </div>
                      <div class="custom-dropdown-container">
                        <button class="format-select" class:open={activeDropdown === 'quality_2'} style="--rotation: {menuRotations['quality_2'] || 0}deg" disabled={isDownloading} onclick={(e) => { e.stopPropagation(); activeDropdown = activeDropdown === 'quality_2' ? null : 'quality_2'; }}>
                          {#key selectedDownloadType}
                            <span class="quality-label-text" in:fade={{ duration: 150 }}>
                              {selectedDownloadType === "audio" ? selectedAudioQuality : selectedVideoQuality}
                            </span>
                          {/key}
                        </button>
                        {#if activeDropdown === 'quality_2'}
                          <div class="custom-dropdown-menu" transition:fly={{ y: 12, duration: 400, easing: cubicOut }}>
                            {#each (selectedDownloadType === "audio" ? AUDIO_QUALITY_OPTIONS : VIDEO_QUALITY_OPTIONS) as q}
                              <button class="custom-dropdown-item" onclick={() => { if (selectedDownloadType === "audio") { selectedAudioQuality = q; } else { selectedVideoQuality = q; } activeDropdown = null; }}>
                                {q}
                              </button>
                            {/each}
                          </div>
                        {/if}
                      </div>
                      <button class="dl-btn" onclick={() => startDownloadWithPairing(false)} disabled={isDownloading} class:downloading={isDownloading}>
                        <span class="btn-text">{isDownloading ? "Downloading..." : "Download"}</span>
                        <div class="btn-glow"></div>
                      </button>
                    </div>
                  </div>
                {/if}
              {:else}
                <div class="dl-btn-group">
                  <div class="custom-dropdown-container">
                    <button class="format-select" disabled style="background-image: none; padding-right: 1rem; text-align: left; opacity: 0.85;">
                      {track.local_file_path ? track.local_file_path.split('.').pop()?.toUpperCase() : 'AUDIO'}
                    </button>
                  </div>
                  <button class="dl-btn" onclick={startEmbedLocal} disabled={isDownloading || !pairedUrl.trim()} class:downloading={isDownloading}>
                    <span class="btn-text">{isDownloading ? "Embedding..." : "Embed Metadata"}</span>
                    <div class="btn-glow"></div>
                  </button>
                </div>
              {/if}
            </div>
          {:else if isPlaylist}
            <div class="meta-header">
              <h2 class="track-title">{playlistTitle}</h2>
            </div>
            <p class="track-artist">{playlistOwner} • {playlistTracks.length} tracks{#if playlistYear} • {playlistYear}{/if}</p>
            <div class="divider"></div>
            <div class="playlist-controls">
              <button class="select-toggle-btn" onclick={toggleAll}>{allSelected ? "Deselect All" : "Select All"}</button>
              <span class="selected-count">{selectedIndices.size} selected</span>
            </div>
            <div class="track-list">
              {#each playlistTracks as t, i}
                {#if t}
                <button class="track-row" class:selected={selectedIndices.has(i)} onclick={() => toggleTrack(i)}>
                  <span class="track-check-wrapper">
                    <span class="custom-checkbox" class:checked={selectedIndices.has(i)}>
                      {#if selectedIndices.has(i)}
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      {/if}
                    </span>
                  </span>
                  <span class="track-num">{i + 1}</span>
                  {#if t.cover_url}<img class="track-thumb" src={t.cover_url} alt="" />{:else}<span class="track-thumb-placeholder">♪</span>{/if}
                  <div class="track-info">
                    <span class="track-row-title">{t.title}</span>
                    <span class="track-row-artist">{t.artists?.join(', ') || 'Unknown'}{#if t.year} • {t.year}{/if}</span>
                  </div>
                  <span class="track-dur">{t.duration != null && t.duration > 0 ? formatDuration(t.duration) : ''}</span>
                </button>
                {:else}
                <div class="track-row loading-row">
                  <span class="track-num">{i + 1}</span>
                  <span class="track-thumb-placeholder">⟳</span>
                  <div class="track-info"><span class="track-row-title muted">Loading...</span></div>
                </div>
                {/if}
              {/each}
            </div>
            <div class="meta-bottom">
              <div class="divider"></div>
              <div class="progress-row">
                <div class="progress-track">
                  <div class="progress-fill" style="width: {isDownloading && progress === 0 ? 5 : Math.max(0, progress * 100)}%;" class:active={isDownloading && progress < 1.0} class:complete={progress >= 1.0}></div>
                </div>
                {#if isDownloading}
                  <button class="cancel-btn" onclick={cancelDownload} aria-label="Cancel download">✕</button>
                {/if}
              </div>
              <div class="dl-row">
                <p class="status-label" class:error={downloadSuccess === false}>{statusText}</p>
                {#if isDownloading}<span class="progress-percent">{Math.round(progress * 100)}%</span>{/if}
              </div>
              <div class="dl-btn-group">
                <div class="custom-dropdown-container">
                  <button class="format-select" class:open={activeDropdown === 'format_3'} style="--rotation: {menuRotations['format_3'] || 0}deg" disabled={isDownloading} onclick={(e) => { e.stopPropagation(); activeDropdown = activeDropdown === 'format_3' ? null : 'format_3'; }}>
                    {selectedFormat}
                  </button>
                  {#if activeDropdown === 'format_3'}
                    <div class="custom-dropdown-menu" transition:fly={{ y: 12, duration: 400, easing: cubicOut }}>
                      {#each Object.keys(AUDIO_FMT_MAP) as fmt}
                        <button class="custom-dropdown-item" onclick={() => { selectedFormat = fmt; activeDropdown = null; }}>
                          {fmt}
                        </button>
                      {/each}
                    </div>
                  {/if}
                </div>
                <button class="dl-btn" onclick={startBatchDownload} disabled={isDownloading || selectedIndices.size === 0} class:downloading={isDownloading}>
                  <span class="btn-text">{isDownloading ? `Downloading ${batchProgress.completed + 1 > batchProgress.total ? batchProgress.total : batchProgress.completed + 1}/${batchProgress.total} songs...` : `Download ${selectedIndices.size} Track${selectedIndices.size !== 1 ? 's' : ''}`}</span>
                  <div class="btn-glow"></div>
                </button>
              </div>
            </div>
          {/if}
        </div>
      </div>
    {/if}
  </div>
  {/if}
</main>

<div class="toast-container">
  {#each toasts as toast (toast.id)}
    <div
      class="toast"
      class:error={toast.type === 'error'}
      class:cancel={toast.type === 'cancel'}
      in:fly={{ x: 40, duration: 400, easing: quintOut }}
      out:fly={{ x: 40, duration: 400, easing: quintOut }}
    >
      {#if toast.type === 'error'}
        <svg class="toast-icon error-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
      {:else if toast.type === 'cancel'}
        <svg class="toast-icon cancel-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10" />
          <line x1="15" y1="9" x2="9" y2="15" />
          <line x1="9" y1="9" x2="15" y2="15" />
        </svg>
      {:else}
        <svg class="toast-icon success-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      {/if}
      <span class="toast-message-text">{toast.message}</span>
    </div>
  {/each}
</div>

<style>
  :global(*) {
    user-select: none;
    -webkit-user-select: none;
    -webkit-user-drag: none;
  }
  
  :global(input), :global(textarea) {
    user-select: auto;
    -webkit-user-select: auto;
  }

  :global(html, body) {
    margin: 0; padding: 0;
    background-color: #06070c;
    color: rgba(255,255,255,0.95);
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    min-height: 100vh;
    overflow: hidden;
    background-image:
      radial-gradient(circle at 5% 5%, rgba(225, 29, 46, 0.08) 0%, transparent 45%),
      radial-gradient(circle at 95% 5%, rgba(30, 144, 255, 0.08) 0%, transparent 45%),
      radial-gradient(circle at 50% 90%, rgba(138, 43, 226, 0.04) 0%, transparent 40%);
    background-attachment: fixed;
  }
  :global(html) { -ms-overflow-style: none; scrollbar-width: none; }
  :global(html::-webkit-scrollbar, body::-webkit-scrollbar) { display: none; }

  .container {
    position: relative;
    width: 100%; height: 100vh;
    display: flex;
    justify-content: center;
    align-items: center;
    background-color: var(--custom-bg, #06070c);
    background-image: 
      var(--custom-wallpaper, none),
      radial-gradient(circle at 5% 5%, rgba(225, 29, 46, 0.08) 0%, transparent 45%),
      radial-gradient(circle at 95% 5%, rgba(30, 144, 255, 0.08) 0%, transparent 45%),
      radial-gradient(circle at 50% 90%, rgba(138, 43, 226, 0.04) 0%, transparent 40%);
    background-size: cover;
    background-position: center;
    transition: background-color 0.5s cubic-bezier(0.23, 1, 0.32, 1);
  }

  .bg-mosaic-container {
    position: fixed;
    inset: -10%;
    z-index: 0;
    pointer-events: none;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .bg-mosaic-grid {
    display: grid;
    grid-template-columns: repeat(8, 1fr);
    gap: clamp(40px, 6vw, 100px);
    transform: rotate(-15deg) scale(1.15);
    width: 120%;
    height: 120%;
    opacity: 0.07;
  }
  .bg-mosaic-item {
    display: flex;
    align-items: center;
    justify-content: center;
    width: clamp(32px, 5vw, 64px);
    height: clamp(32px, 5vw, 64px);
    margin: auto;
    transition: all 0.3s ease;
  }
  .bg-mosaic-item.type-0, .bg-mosaic-item.type-1 {
    color: rgba(225, 29, 46, 0.7);
    filter: blur(1.5px) drop-shadow(0 0 3px rgba(225, 29, 46, 0.35));
  }
  .bg-mosaic-item.type-2 {
    color: rgba(30, 215, 96, 0.7);
    filter: blur(1.5px) drop-shadow(0 0 3px rgba(30, 215, 96, 0.35));
  }
  .bg-mosaic-item svg {
    width: 100%;
    height: 100%;
  }

  .content-wrapper {
    position: relative; z-index: 1;
    width: 100%; max-width: 720px;
    padding: 2rem; box-sizing: border-box;
    transition: all 0.38s cubic-bezier(0.22, 1, 0.36, 1);
  }
  .content-wrapper.wide {
    position: absolute;
    inset: 3rem 2.4rem 2rem 2rem;
    max-width: none;
    width: auto;
    padding-top: 3.5rem;
    display: flex;
    flex-direction: column;
  }

  header { text-align: center; margin-bottom: 2.5rem; transition: all 0.5s cubic-bezier(0.16, 1, 0.3, 1); }
  header.compact {
    position: fixed;
    top: calc(2.8rem + 7px);
    transform: translateY(-50%);
    left: 14rem;
    right: 20.5rem;
    margin: 0;
    padding: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 99;
    transition: all 0.5s cubic-bezier(0.23, 1, 0.32, 1);
  }
  h1 {
    font-family: 'Outfit', sans-serif;
    font-weight: 700; font-size: 3.5rem;
    margin: 0; color: #FFFFFF;
    text-shadow: 0 2px 4px rgba(0,0,0,.5);
    letter-spacing: -1px;
    transition: font-size 0.5s cubic-bezier(0.16, 1, 0.3, 1);
  }
  header.compact h1 { font-size: 2rem; }
  .subtitle {
    font-family: 'Outfit', sans-serif;
    color: #A0A4A8; font-size: 1.1rem; font-weight: 300;
    margin-top: .5rem; letter-spacing: 1px;
  }

  .top-bar-input {
    max-width: 580px;
    width: 100%;
    margin: 0 auto;
    transition: all 0.5s cubic-bezier(0.23, 1, 0.32, 1);
  }
  .top-bar-input.exit {
    opacity: 0;
    transform: scale(1.03) translateY(-10px);
    pointer-events: none;
  }
  .top-bar-input input {
    text-align: center;
    padding-left: 3.1rem;
    padding-right: 3.1rem;
  }

  .input-wrapper .search-divider {
    position: absolute;
    left: 2.7rem;
    top: 50%;
    transform: translateY(-50%);
    font-size: 1rem;
    color: rgba(255, 255, 255, 0.15);
    pointer-events: none;
    user-select: none;
    font-weight: 300;
    z-index: 10;
  }

  .glass-card {
    position: relative;
    background: linear-gradient(to bottom, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.01) 100%);
    border: 1px solid rgba(255,255,255,0.06);
    border-top-color: rgba(255,255,255,0.18);
    border-bottom-color: rgba(255,255,255,0.02);
    border-radius: 36px;
    padding: 2.5rem;
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.25),
      inset 0 -1px 0 rgba(0,0,0,0.15),
      0 8px 32px rgba(0,0,0,0.25),
      0 2px 6px rgba(0,0,0,0.12);
    transition: all 0.4s cubic-bezier(0.23, 1, 0.32, 1);
  }

  .glass-card:hover {
    transform: translateY(-2px);
    background: linear-gradient(to bottom, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.02) 100%);
    border-color: rgba(255,255,255,0.08);
    border-top-color: rgba(255,255,255,0.25);
    border-bottom-color: rgba(255,255,255,0.03);
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.35),
      inset 0 -1px 0 rgba(0,0,0,0.12),
      0 16px 48px rgba(0,0,0,0.3),
      0 2px 8px rgba(0,0,0,0.15);
  }

  .glass-card.exit {
    opacity: 0;
    transform: scale(1.03) translateY(-10px);
    pointer-events: none;
  }

  .input-group { display: flex; gap: 1rem; margin-bottom: 1.5rem; }
  .input-wrapper {
    position: relative;
    flex: 1;
    display: flex;
    align-items: center;
  }
  .input-wrapper .search-icon {
    position: absolute;
    left: 1.25rem;
    top: 50%;
    transform: translateY(-50%);
    width: 1.15rem;
    height: 1.15rem;
    color: rgba(255, 255, 255, 0.4);
    pointer-events: none;
    transition: color 0.3s cubic-bezier(0.23, 1, 0.32, 1);
    z-index: 10;
  }
  .input-wrapper .search-icon-gif {
    position: absolute;
    left: 1.25rem;
    top: 50%;
    transform: translateY(-50%);
    width: 1.15rem;
    height: 1.15rem;
    z-index: 10;
    border-radius: 50%;
  }
  input {
    flex: 1;
    width: 100%;
    background: linear-gradient(to bottom, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%);
    backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
    border: 1px solid rgba(255,255,255,0.06);
    border-top-color: rgba(255,255,255,0.15);
    border-bottom-color: rgba(255,255,255,0.02);
    color: rgba(255,255,255,0.95); padding: 0.85rem 2.8rem 0.85rem 3.4rem;
    border-radius: 36px; font-size: 0.85rem;
    font-family: 'Inter', sans-serif; outline: none;
    transition: all 0.3s cubic-bezier(0.23, 1, 0.32, 1);
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15),
      inset 0 2px 4px rgba(0,0,0,0.15);
  }
  .clear-url-btn {
    position: absolute;
    right: 1.25rem;
    top: 50%;
    transform: translateY(-50%);
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    box-shadow: none !important;
    color: rgba(255, 255, 255, 0.45);
    cursor: pointer;
    font-size: 0.75rem;
    width: 22px;
    height: 22px;
    padding: 0 !important;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    line-height: 0;
    transition: all 0.2s cubic-bezier(0.23, 1, 0.32, 1);
    z-index: 15;
    outline: none !important;
  }
  .clear-url-btn:hover {
    background: rgba(255, 255, 255, 0.12);
    border-color: rgba(255, 255, 255, 0.2) !important;
    color: rgba(255, 255, 255, 0.85);
    transform: translateY(-50%) scale(1.05);
  }
  .clear-url-svg {
    width: 11px;
    height: 11px;
    color: currentColor;
    display: inline-block;
  }
  input::placeholder { color: rgba(255,255,255,0.4); }
  .input-wrapper input:focus + .search-icon {
    color: rgba(255, 255, 255, 0.85);
  }
  input:focus {
    background: linear-gradient(to bottom, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.02) 100%); 
    border-color: rgba(255,255,255,0.08);
    border-top-color: rgba(255,255,255,0.22);
    border-bottom-color: rgba(255,255,255,0.03);
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.20),
      inset 0 -1px 0 rgba(0,0,0,0.12),
      inset 0 2px 4px rgba(0,0,0,0.1);
  }
  input:disabled { opacity: .7; cursor: not-allowed; }

  .fetch-error {
    color: #FF5555; font-size: .9rem;
    margin: 0 0 1rem;
    padding: .6rem 1rem;
    background: rgba(255,85,85,.08);
    border: 1px solid rgba(255,85,85,.2);
    border-radius: 10px;
  }
  .fetch-error-details {
    margin: 0.5rem 0;
    padding: 0.5rem 1rem;
    background: rgba(255,85,85,.08);
    border: 1px solid rgba(255,85,85,.2);
    border-radius: 10px;
    color: #FF5555;
    text-align: left;
  }
  .fetch-error-details summary {
    cursor: pointer;
    font-weight: 500;
    outline: none;
  }
  .fetch-error-details summary::-webkit-details-marker {
    color: #FF5555;
  }
  .fetch-error-content {
    margin-top: 0.5rem;
    padding-top: 0.5rem;
    border-top: 1px solid rgba(255,85,85,.15);
    font-size: 0.9rem;
    white-space: pre-wrap;
    word-break: break-word;
    color: rgba(255,255,255,0.85);
  }

  button {
    position: relative;
    background: linear-gradient(to bottom, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%); color: #FFFFFF;
    border: 1px solid rgba(255,255,255,0.06);
    border-top-color: rgba(255,255,255,0.15);
    border-bottom-color: rgba(255,255,255,0.02);
    backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
    padding: 0 2rem;
    border-radius: 36px; font-size: 1.05rem; font-weight: 600;
    font-family: 'Inter', sans-serif; cursor: pointer; overflow: hidden;
    transition: all 0.3s cubic-bezier(0.23, 1, 0.32, 1);
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15),
      0 4px 14px rgba(0,0,0,0.18),
      0 2px 6px rgba(0,0,0,0.12);
  }
  .input-group button {
    padding: 0 1.25rem;
    font-size: 0.95rem;
    flex-shrink: 0;
  }
  .btn-text { position: relative; z-index: 1; }
  .btn-glow { display: none; }
  button:hover:not(:disabled) .btn-glow { display: none; }
  button:hover:not(:disabled):not(.format-tab):not(.delete-history-item-btn):not(.clear-url-btn) { transform: scale(1.02);
    background: linear-gradient(to bottom, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.02) 100%);
    border-color: rgba(255,255,255,0.08);
    border-top-color: rgba(255,255,255,0.22);
    border-bottom-color: rgba(255,255,255,0.03);
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.20),
      inset 0 -1px 0 rgba(0,0,0,0.12),
      0 6px 20px rgba(0,0,0,0.22),
      0 2px 8px rgba(0,0,0,0.15);
  }
  button:active:not(:disabled):not(.format-tab):not(.delete-history-item-btn):not(.clear-url-btn) { transform: scale(0.98); }
  button:disabled { 
    background: rgba(255,255,255,0.03); color: rgba(255,255,255,0.4); 
    border-color: rgba(255,255,255,0.08);
    box-shadow: none; cursor: not-allowed; transform: none; 
  }
  @keyframes glass-pulse {
    0% { background: rgba(255,255,255,0.02); border-color: rgba(255,255,255,0.08); }
    50% { background: rgba(255,255,255,0.06); border-color: rgba(255,255,255,0.15); }
    100% { background: rgba(255,255,255,0.02); border-color: rgba(255,255,255,0.08); }
  }
  button.loading, button.loading:disabled {
    background: rgba(255,255,255,0.02);
    border-color: rgba(255,255,255,0.08);
    color: rgba(255,255,255,0.7);
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15),
      0 4px 14px rgba(0,0,0,0.1),
      0 2px 6px rgba(0,0,0,0.08);
    cursor: wait;
    transform: none;
    animation: glass-pulse 2s infinite ease-in-out;
  }

  .status-panel-wrapper {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .glass-card .status-panel-wrapper {
    display: block;
    width: 100%;
  }

  .glass-card .status-panel {
    width: 100%;
    box-sizing: border-box;
    justify-content: flex-start;
  }

  .status-panel {
    position: relative;
    z-index: 2;
    display: flex;
    align-items: center;
    gap: 0.85rem;
    padding: 0.9rem 1.4rem;
    border-radius: 36px;
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.08);
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15),
      0 8px 32px rgba(0,0,0,0.25),
      0 2px 6px rgba(0,0,0,0.12);
    transition: all 0.3s cubic-bezier(0.23, 1, 0.32, 1);
  }

  .status-panel.active {
    background: rgba(255,255,255,0.04);
    border-color: rgba(255,255,255,0.12);
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.20),
      inset 0 -1px 0 rgba(0,0,0,0.12),
      0 8px 32px rgba(225, 29, 46, 0.15),
      0 2px 6px rgba(0,0,0,0.12);
  }

  .status-gif-wrapper {
    position: relative;
    width: 32px;
    height: 32px;
    flex-shrink: 0;
    border-radius: 50%;
    border: none !important;
    outline: none !important;
    transition: all 0.3s ease;
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
    border-radius: 50%;
    border: none !important;
    outline: none !important;
  }

  .status-gif-wrapper.active .status-gif {
    opacity: 1;
    filter: none;
  }

  .status-label { margin: 0; font-size: .95rem; color: #D3D7DA; letter-spacing: .03em; }
  .status-label.error { color: #FF5555; }

  .details-layout {
    position: relative;
    overflow: hidden;
    display: grid;
    grid-template-columns: auto 1fr;
    align-items: stretch;
    gap: 2.5rem;
    background: rgba(255,255,255,0.02);
    border-radius: 36px;
    padding: 2.5rem;
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15),
      0 25px 50px -12px rgba(0,0,0,0.4),
      0 2px 6px rgba(0,0,0,0.12);
    border: 1px solid rgba(255,255,255,0.08);
    flex: 1;
    min-height: 0;
    box-sizing: border-box;
    transition: all 0.5s cubic-bezier(0.23, 1, 0.32, 1);
  }

  .details-backdrop {
    position: absolute;
    inset: -30px;
    background-size: cover;
    background-position: center center;
    filter: blur(60px) brightness(0.35) saturate(1.6);
    opacity: 0.5;
    z-index: 0;
    pointer-events: none;
    transform: scale(1.15);
  }

  .details-layout.exit {
    opacity: 0;
    transform: scale(1.03) translateY(-10px);
    pointer-events: none;
  }

  .cover-col {
    position: relative;
    z-index: 1;
    width: clamp(180px, 28vh, 300px);
    flex-shrink: 0;
    align-self: start;
  }
  .cover-img {
    width: 100%;
    height: auto;
    border-radius: 24px;
    display: block;
    box-shadow: 0 16px 40px rgba(0,0,0,.6), 0 0 0 1px rgba(255,255,255,.08);
  }
  .cover-placeholder {
    width: 100%;
    aspect-ratio: 1 / 1;
    border-radius: 24px;
    background: #1A1C23;
    display: flex; align-items: center; justify-content: center;
    font-size: 5rem; color: #2A2D35;
  }

  .meta-col {
    position: relative;
    z-index: 1;
    display: flex; flex-direction: column;
    gap: .75rem; min-width: 0;
    height: 100%;
    overflow: visible;
  }
  .meta-header { flex-shrink: 0; }
  .meta-top { 
    flex: 1 1 0; 
    display: flex; 
    flex-direction: column; 
    gap: .75rem; 
    overflow-y: auto;
    min-height: 0;
    padding-right: 0.5rem;
    scrollbar-width: thin;
    scrollbar-color: rgba(225, 29, 46, 0.2) transparent;
  }
  .meta-top > * { flex-shrink: 0; }
  .meta-top::-webkit-scrollbar { width: 5px; }
  .meta-top::-webkit-scrollbar-track { background: transparent; }
  .meta-top::-webkit-scrollbar-thumb { background: rgba(225, 29, 46, 0.2); border-radius: 99px; transition: background 0.3s ease; }
  .meta-top::-webkit-scrollbar-thumb:hover { background: rgba(225, 29, 46, 0.55); }

  .meta-bottom { 
    display: flex; 
    flex-direction: column; 
    gap: .6rem; 
    margin-top: auto; 
    flex-shrink: 0;
    padding-bottom: 6px;
  }

  .nav-arrows-inline {
    display: flex;
    gap: 0.5rem;
    padding: 0 0.3rem;
  }
  .nav-btn {
    width: 48px;
    height: 48px;
    border-radius: 50%;
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.08);
    color: rgba(255,255,255,0.75);
    font-size: 2rem;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all 0.2s ease;
    padding: 0;
    line-height: 1;
    font-family: monospace;
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15);
  }
  .nav-btn:hover:not(:disabled) {
    background: rgba(255,255,255,0.04);
    color: #fff;
    border-color: rgba(255,255,255,0.12);
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.20),
      inset 0 -1px 0 rgba(0,0,0,0.12),
      0 4px 15px rgba(0, 0, 0, 0.25);
    transform: scale(1.02);
  }
  .nav-btn:active:not(:disabled) {
    transform: scale(0.95);
  }
  .nav-btn:disabled {
    opacity: 0.3;
    cursor: not-allowed;
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

  .progress-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .progress-row .progress-track { flex: 1; }

  .cancel-btn {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: rgba(255,255,255,0.02);
    backdrop-filter: blur(24px);
    border: 1px solid rgba(255,255,255,0.08);
    color: rgba(255,255,255,0.55);
    font-size: 0.75rem;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all 0.2s ease;
    padding: 0;
    flex-shrink: 0;
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15);
  }
  .cancel-btn:hover {
    background: rgba(225,29,46,0.15);
    border-color: rgba(225,29,46,0.35);
    color: #fff;
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.20),
      inset 0 -1px 0 rgba(0,0,0,0.12),
      0 0 10px rgba(225,29,46,0.25);
    transform: scale(1.1);
  }
  .cancel-btn:active {
    transform: scale(0.92);
  }

  .progress-track {
    width: 100%; height: 21px;
    background: rgba(255,255,255,0.03);
    backdrop-filter: blur(24px);
    border: 1px solid rgba(255,255,255,0.05);
    box-shadow: inset 0 2px 4px rgba(0,0,0,0.4);
    border-radius: 999px;
    position: relative;
    overflow: hidden;
    display: flex;
    align-items: center;
  }
  .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, rgba(225,29,46,0.9) 0%, rgba(255,77,106,1) 50%, rgba(225,29,46,0.9) 100%);
    background-size: 200% 100%;
    box-shadow: 0 0 10px rgba(225,29,46,0.5);
    transition: width 0.5s cubic-bezier(0.23, 1, 0.32, 1);
    position: relative;
    border-radius: 999px;
  }
  .progress-fill.active, .progress-fill.complete {
    animation: pulse-glow 1.5s ease-in-out infinite alternate;
  }
  @keyframes pulse-glow {
    0% { box-shadow: 0 0 8px rgba(225,29,46,0.6), 0 0 16px rgba(225,29,46,0.18); }
    100% { box-shadow: 0 0 15px rgba(255,77,106,0.9), 0 0 25px rgba(255,77,106,0.6); }
  }

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
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15);
  }
  .dl-btn:hover:not(:disabled) {
    transform: scale(1.02);
  }
  .dl-btn:active:not(:disabled) {
    transform: scale(0.98);
  }
  .dl-btn.downloading {
    background: #1F2833;
    border: 1px solid rgba(225,29,46,.18);
  }

  .dl-btn-group {
    display: flex;
    gap: 0.75rem;
    width: 100%;
    transition: gap 0.3s cubic-bezier(0.23, 1, 0.32, 1);
  }
  .format-collapse {
    max-width: 200px;
    opacity: 1;
    overflow: visible;
    transition: max-width 0.3s cubic-bezier(0.23, 1, 0.32, 1),
                opacity 0.25s ease,
                margin 0.3s cubic-bezier(0.23, 1, 0.32, 1),
                padding 0.3s cubic-bezier(0.23, 1, 0.32, 1);
  }
  .format-collapse.collapsed {
    max-width: 0;
    opacity: 0;
    overflow: hidden;
    margin: 0 -0.375rem 0 0;
    pointer-events: none;
  }
  .format-collapse.collapsed .format-select {
    padding: 0;
    border-width: 0;
    min-width: 0;
  }
  .dl-btn-group .dl-btn {
    flex: 1;
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15);
  }
  .dl-btn-group.paired-flow {
    flex-direction: row;
    align-items: center;
    gap: 0.6rem;
  }
  .dl-btn-group.paired-flow .format-select {
    width: auto;
    flex-shrink: 0;
  }
  .dl-btn-group.paired-flow .dl-btn-pair {
    display: flex;
    gap: 0.6rem;
    flex: 1;
  }
  .dl-btn-group.paired-flow .dl-btn-pair .dl-btn {
    flex: 1;
    font-size: 0.78rem;
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15);
  }
  .dl-btn-group.paired-flow .dl-btn.secondary-dl {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: rgba(255, 255, 255, 0.85);
  }
  .dl-btn-group.paired-flow .dl-btn.secondary-dl:hover {
    background: rgba(255, 255, 255, 0.08);
    border-color: rgba(255, 255, 255, 0.2);
    color: #fff;
  }

  .save-cover-btn {
    width: 100%;
    height: 28px;
    margin-top: .5rem;
    padding: 0 1rem;
    border-radius: 16px;
    font-size: .85rem;
    font-weight: 500;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: .45rem;
    background: rgba(255,255,255,0.02);
    backdrop-filter: blur(24px);
    border: 1px solid rgba(255,255,255,0.08);
    color: rgba(255,255,255,0.7);
    transition: all 0.3s cubic-bezier(0.23, 1, 0.32, 1);
    cursor: pointer;
    white-space: nowrap;
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15);
  }
  .save-cover-btn:hover:not(:disabled) {
    background: rgba(225,29,46,.15);
    border-color: rgba(225,29,46,.4);
    color: #FFFFFF;
    transform: translateY(-2px);
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.20),
      inset 0 -1px 0 rgba(0,0,0,0.12);
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

  .format-select {
    background: rgba(0, 0, 0, 0.45);
    backdrop-filter: blur(24px);
    border: 1px solid rgba(255,255,255,0.08);
    color: rgba(255,255,255,0.95);
    padding: 0 1rem;
    border-radius: 12px;
    font-size: .95rem;
    font-family: 'Inter', sans-serif;
    outline: none;
    cursor: pointer;
    appearance: none;
    position: relative;
    padding-right: 2rem;
    transition: all 0.3s cubic-bezier(0.23, 1, 0.32, 1);
    min-width: 140px;
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15),
      inset 0 2px 4px rgba(0,0,0,0.1);
    height: 48px;
    margin-top: .25rem;
    white-space: nowrap;
  }
  .quality-label-text {
    display: inline-block;
    width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    vertical-align: middle;
  }
  .format-select::after {
    content: "";
    position: absolute;
    right: 0.75rem;
    top: 50%;
    width: 16px;
    height: 16px;
    margin-top: -8px;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%23FFFFFF' stroke-opacity='0.6' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M 7 10 L 10.6 13.6 Q 12 15 13.4 13.6 L 17 10'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: center;
    background-size: contain;
    transform: rotate(var(--rotation, 0deg));
    transition: transform 0.4s cubic-bezier(0.23, 1, 0.32, 1);
  }
  
  .format-select:hover:not(:disabled) {
    border-color: rgba(255,255,255,0.12);
    background: rgba(0, 0, 0, 0.35);
  }
  .format-select:focus {
    border-color: rgba(225,29,46,0.5);
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.20),
      inset 0 -1px 0 rgba(0,0,0,0.12),
      inset 0 2px 4px rgba(0,0,0,0.1),
      0 0 0 4px rgba(225,29,46,.15);
  }
  .format-select:disabled {
    opacity: .5;
    cursor: not-allowed;
  }


  .yt-controls {
    display: flex;
    flex-direction: column;
    gap: .5rem;
    margin-bottom: .25rem;
    width: 100%;
  }
  .yt-format-row {
    display: flex;
    gap: 3px;
    padding: 4px;
    border-radius: 36px;
    border: 1px solid rgba(255,255,255,0.08);
    background: rgba(255,255,255,0.02);
    position: relative;
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15),
      inset 0 2px 4px rgba(0,0,0,0.1);
    align-self: stretch;
    height: 48px;
    margin-top: .25rem;
    box-sizing: border-box;
  }
  .format-slider {
    position: absolute;
    top: 4px;
    left: 4px;
    width: calc(50% - 5.5px);
    height: calc(100% - 8px);
    border-radius: 32px;
    background: rgba(255,255,255,0.10);
    border: 1px solid rgba(255,255,255,0.14);
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.08);
    transition: transform 0.35s cubic-bezier(0.23, 1, 0.32, 1);
    z-index: 0;
    box-sizing: border-box;
  }
  .format-tab {
    flex: 1;
    padding: .5rem 1rem;
    font-size: .85rem;
    font-weight: 500;
    -webkit-appearance: none;
    appearance: none;
    background: transparent !important;
    color: rgba(255,255,255,0.45);
    border: none !important;
    box-shadow: none !important;
    outline: none !important;
    border-radius: 32px;
    cursor: pointer;
    transition: color 0.3s cubic-bezier(0.23, 1, 0.32, 1), text-shadow 0.3s ease;
    position: relative;
    z-index: 1;
  }
  .format-tab:hover,
  .format-tab:focus,
  .format-tab:focus-visible,
  .format-tab:active {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    outline: none !important;
  }
  .format-tab:hover:not(:disabled):not(.active) {
    color: rgba(255,255,255,0.75);
    text-shadow: 0 0 8px rgba(255,255,255,0.3);
  }
  .format-tab.active {
    color: #FFFFFF;
    font-weight: 600;
  }
  .format-tab:disabled {
    opacity: .5;
    cursor: not-allowed;
    color: #555E6B;
  }

  .playlist-controls {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: .25rem;
  }
  .select-toggle-btn {
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.08);
    color: #A0A4A8;
    font-size: .8rem;
    font-weight: 500;
    padding: .3rem .8rem;
    border-radius: 16px;
    transition: all 0.3s cubic-bezier(0.23, 1, 0.32, 1);
    cursor: pointer;
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15);
  }
  .select-toggle-btn:hover:not(:disabled) {
    background: rgba(225,29,46,.1);
    border-color: rgba(225,29,46,.18);
    color: #FFFFFF;
    transform: none;
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.20),
      inset 0 -1px 0 rgba(0,0,0,0.12);
  }
  .selected-count {
    font-size: .8rem;
    color: #555E6B;
  }

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
    scrollbar-color: rgba(225, 29, 46, 0.2) transparent;
  }
  .track-list::-webkit-scrollbar { width: 5px; }
  .track-list::-webkit-scrollbar-track { background: transparent; }
  .track-list::-webkit-scrollbar-thumb { background: rgba(225, 29, 46, 0.2); border-radius: 99px; transition: background 0.3s ease; }
  .track-list::-webkit-scrollbar-thumb:hover { background: rgba(225, 29, 46, 0.55); }

  .track-row {
    display: flex;
    align-items: center;
    gap: .6rem;
    padding: .5rem .6rem;
    border-radius: 10px;
    background: transparent;
    border: 1px solid transparent;
    cursor: pointer;
    transition: all .3s cubic-bezier(0.23, 1, 0.32, 1);
    text-align: left;
    width: auto;
    align-self: stretch;
    margin: 0 13px;
    box-sizing: border-box;
    min-height: 42px;
  }
  .track-row:hover:not(:disabled) {
    background: rgba(255,255,255,.04);
    border-color: rgba(255,255,255,.05);
    transform: translateX(4px);
  }
  .track-row.selected {
    background: rgba(225,29,46,.1);
    border-color: rgba(225,29,46,.2);
  }
  .track-row.selected:hover:not(:disabled) {
    background: rgba(225,29,46,.15);
    transform: translateX(4px);
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

  .onboarding-screen {
    position: fixed; inset: 0;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 2rem;
    z-index: 1000;
    pointer-events: none;
  }
  .onboarding-screen > * {
    pointer-events: auto;
  }

  .onboarding-screen .status-panel-wrapper::before {
    content: '';
    position: absolute;
    inset: -6px -8px;
    border-radius: 30px;
    background: radial-gradient(
      ellipse at center,
      rgba(107, 159, 212, 0.15) 0%,
      rgba(74, 127, 191, 0.08) 50%,
      transparent 75%
    );
    z-index: 0;
    pointer-events: none;
  }

  .onboarding-screen .status-panel {
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15),
      0 8px 32px rgba(0,0,0,0.25),
      0 2px 6px rgba(0,0,0,0.12);
  }
  .onboarding-screen .status-gif {
    opacity: 0.85;
    filter: none;
  }
  .login-hint {
    font-size: 0.85rem;
    color: #555E6B;
    text-align: center;
    line-height: 1.6;
    margin: 0;
    padding: 0.75rem 1.25rem;
    border-radius: 36px;
    background: rgba(225,29,46,0.05);
    border: 1px solid rgba(225,29,46,0.15);
    max-width: 340px;
  }

  .clock-widget {
    position: fixed;
    top: 2.8rem;
    transform: translateY(-50%);
    left: 2rem;
    z-index: 100;
    display: flex;
    align-items: center;
    gap: 1.1rem;
    background: rgba(255,255,255,0.02);
    padding: 0.45rem 1.3rem;
    border-radius: 100px;
    border: 1px solid rgba(255,255,255,0.08);
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    color: rgba(255, 255, 255, 0.9);
    font-family: 'Inter', sans-serif;
    user-select: none;
    transition: all 0.5s cubic-bezier(0.23, 1, 0.32, 1);
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15),
      0 8px 32px rgba(0,0,0,0.25),
      0 2px 6px rgba(0,0,0,0.12);
  }
  .clock-date {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    line-height: 1.1;
  }
  .clock-month {
    font-size: 1.1rem;
    font-weight: 700;
    letter-spacing: 1px;
    color: #e11d2e;
  }
  .clock-day {
    font-size: 2.1rem;
    font-weight: 600;
  }
  .clock-divider {
    width: 1px;
    height: 42px;
    background: rgba(255, 255, 255, 0.1);
  }
  .clock-time {
    font-size: 1.35rem;
    font-weight: 300;
    letter-spacing: 0.5px;
  }

  .profile-widget {
    position: fixed;
    top: 2.8rem;
    transform: translateY(-50%);
    right: 2.4rem;
    z-index: 100;
    display: flex;
    align-items: center;
    background: rgba(255,255,255,0.02);
    padding: 0.4rem;
    border-radius: 100px;
    border: 1px solid rgba(255,255,255,0.08);
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    transition: all 0.5s cubic-bezier(0.23, 1, 0.32, 1);
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15),
      0 8px 32px rgba(0,0,0,0.25),
      0 2px 6px rgba(0,0,0,0.12);
  }
  .profile-divider {
    width: 1px;
    height: 30px;
    background: rgba(255, 255, 255, 0.1);
    margin: 0 0.6rem;
  }
  .profile-btn {
    display: flex;
    align-items: center;
    gap: 1.1rem;
    background: transparent;
    padding: 0.3rem 1.5rem 0.3rem 1.5rem;
    border-radius: 100px;
    border: none;
    transition: all 0.3s cubic-bezier(0.23, 1, 0.32, 1);
    cursor: pointer;
    font-family: inherit;
    outline: none;
    width: 100%;
    max-width: 520px;
    justify-content: flex-start;
    text-align: left;
  }
  .profile-btn:hover {
    background: rgba(255, 255, 255, 0.08);
    transform: scale(1.02);
    box-shadow: 0 4px 15px rgba(0,0,0,0.3);
  }
  .profile-btn:active {
    transform: scale(0.98);
  }
  .profile-avatar {
    width: 48px;
    height: 48px;
    border-radius: 50%;
    object-fit: cover;
  }
  .profile-name {
    color: #E2E4E9;
    font-size: 1.35rem;
    font-weight: 500;
    text-align: left;
    flex: 1;
  }

  .profile-dropdown {
    position: absolute;
    top: calc(100% + 0.5rem);
    left: 0;
    right: 0;
    width: auto;
    background: rgba(0, 0, 0, 0.45);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 16px;
    backdrop-filter: blur(40px);
    -webkit-backdrop-filter: blur(40px);
    box-shadow:
      inset 0 1.5px 0 rgba(255, 255, 255, 0.25),
      inset 0 -1.5px 0 rgba(0, 0, 0, 0.25),
      0 24px 60px rgba(0, 0, 0, 0.6),
      0 4px 16px rgba(0, 0, 0, 0.3);
    overflow: hidden;
    display: flex;
    flex-direction: column;
    min-height: 250px;
    transition: min-height 0.3s cubic-bezier(0.23, 1, 0.32, 1);
  }
  .profile-submenu-container {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    flex: 1;
  }
  .profile-main-options {
    display: flex;
    flex-direction: column;
    padding: 0.6rem;
    gap: 0.4rem;
  }
  .profile-opt-btn {
    display: flex;
    align-items: center;
    gap: 1rem;
    width: 100%;
    padding: 0.9rem 1.1rem;
    background: rgba(255, 255, 255, 0.01);
    border: 1px solid rgba(255, 255, 255, 0.03);
    border-radius: 10px;
    cursor: pointer;
    text-align: left;
    transition: all 0.25s cubic-bezier(0.23, 1, 0.32, 1);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
  }
  .profile-opt-btn:hover {
    background: rgba(255, 255, 255, 0.07);
    border-color: rgba(255, 255, 255, 0.12);
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.15),
      0 4px 12px rgba(0, 0, 0, 0.15);
    transform: translateY(-1px);
  }
  .profile-opt-btn:active {
    transform: scale(0.98);
  }
  .opt-icon {
    width: 22px;
    height: 22px;
    color: rgba(255, 255, 255, 0.6);
    transition: color 0.2s ease;
  }
  .profile-opt-btn:hover .opt-icon {
    color: #FFFFFF;
  }
  .opt-text {
    display: flex;
    flex-direction: column;
    flex: 1;
  }
  .opt-title {
    font-size: 0.95rem;
    font-weight: 500;
    color: #E2E4E9;
  }
  .opt-desc {
    font-size: 0.75rem;
    color: rgba(255, 255, 255, 0.4);
  }
  .opt-chevron {
    width: 16px;
    height: 16px;
    color: rgba(255, 255, 255, 0.25);
    transition: transform 0.2s ease, color 0.2s ease;
  }
  .profile-opt-btn:hover .opt-chevron {
    color: rgba(255, 255, 255, 0.6);
    transform: translateX(2px);
  }
  .menu-back-btn {
    background: transparent;
    border: none;
    color: rgba(255, 255, 255, 0.6);
    cursor: pointer;
    padding: 6px;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
  }
  .menu-back-btn:hover {
    color: #FFFFFF;
    background: rgba(255, 255, 255, 0.08);
  }
  .menu-back-btn svg {
    width: 20px;
    height: 20px;
  }
  .theme-slider-toggle {
    width: 66px;
    height: 32px;
    border-radius: 99px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    position: relative;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 7.5px;
    box-sizing: border-box;
    transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
    outline: none;
  }
  .profile-widget.light-theme .theme-slider-toggle {
    background: rgba(0, 0, 0, 0.05);
    border-color: rgba(0, 0, 0, 0.1);
  }
  .theme-slider-toggle:hover {
    border-color: rgba(255, 255, 255, 0.2);
    background: rgba(255, 255, 255, 0.08);
  }
  .profile-widget.light-theme .theme-slider-toggle:hover {
    border-color: rgba(0, 0, 0, 0.18);
    background: rgba(0, 0, 0, 0.08);
  }
  .slider-icon {
    width: 15px;
    height: 15px;
    color: rgba(255, 255, 255, 0.35);
    z-index: 3;
    transition: color 0.3s ease;
    pointer-events: none;
  }
  .profile-widget.light-theme .slider-icon {
    color: rgba(15, 17, 23, 0.35);
  }
  .theme-slider-toggle.light-active .sun-icon {
    color: #ffd54f !important;
  }
  .theme-slider-toggle:not(.light-active) .moon-icon {
    color: #9fa8da !important;
  }
  .slider-thumb {
    width: 25px;
    height: 25px;
    border-radius: 50%;
    position: absolute;
    top: 2.5px;
    left: 2.5px;
    box-sizing: border-box;
    z-index: 2;
    transition: transform 0.38s cubic-bezier(0.25, 0.8, 0.25, 1), background 0.3s ease, border-color 0.3s ease, box-shadow 0.3s ease;
    
    /* Liquid glass for Dark Theme */
    background: radial-gradient(circle at 30% 30%, rgba(255, 255, 255, 0.35) 0%, rgba(255, 255, 255, 0.05) 100%);
    backdrop-filter: blur(4px) saturate(120%);
    -webkit-backdrop-filter: blur(4px) saturate(120%);
    border: 1px solid rgba(255, 255, 255, 0.4);
    box-shadow: inset 0 2px 3px rgba(255, 255, 255, 0.6), 0 2px 6px rgba(0, 0, 0, 0.2);
  }
  .profile-widget.light-theme .slider-thumb {
    /* Liquid glass for Light Theme */
    background: radial-gradient(circle at 30% 30%, rgba(255, 255, 255, 0.8) 0%, rgba(0, 0, 0, 0.05) 100%);
    backdrop-filter: blur(4px) saturate(120%);
    -webkit-backdrop-filter: blur(4px) saturate(120%);
    border: 1px solid rgba(0, 0, 0, 0.2);
    box-shadow: inset 0 2px 4px rgba(255, 255, 255, 0.9), 0 2px 5px rgba(0, 0, 0, 0.15);
  }
  .theme-slider-toggle.light-active .slider-thumb {
    transform: translateX(34px);
  }
  
  /* Light theme header overrides */
  .profile-widget.light-theme .menu-back-btn {
    color: rgba(15, 17, 23, 0.6) !important;
  }
  .profile-widget.light-theme .menu-back-btn:hover {
    color: rgba(15, 17, 23, 0.95) !important;
    background: rgba(0, 0, 0, 0.06) !important;
  }
  .profile-about-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 1.5rem;
    text-align: center;
  }
  .about-logo {
    font-size: 2.2rem;
    font-weight: 800;
    letter-spacing: -1px;
    background: linear-gradient(135deg, #FFFFFF 0%, rgba(255,255,255,0.4) 100%);
    background-clip: text;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0.2rem;
  }
  .about-tagline {
    font-size: 0.85rem;
    color: rgba(255, 255, 255, 0.5);
    margin-bottom: 1rem;
  }
  .about-version {
    font-size: 0.75rem;
    padding: 2px 8px;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 20px;
    color: rgba(255, 255, 255, 0.7);
    margin-bottom: 1.5rem;
  }
  .about-info-grid {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
    font-size: 0.8rem;
    width: 100%;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
    padding-top: 1rem;
  }
  .info-label {
    color: rgba(255, 255, 255, 0.4);
  }
  .info-val {
    color: rgba(255, 255, 255, 0.85);
    text-align: right;
  }
  .about-developer-card {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    width: 100%;
    justify-content: center;
  }
  .about-avatar {
    width: 44px;
    height: 44px;
    border-radius: 50%;
    object-fit: cover;
    border: 1px solid rgba(255, 255, 255, 0.1);
    flex-shrink: 0;
  }
  .about-developer-info {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    flex: 1;
    min-width: 0;
  }
  .about-developer-name {
    font-size: 0.9rem;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.95);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .about-developer-handle {
    font-size: 0.78rem;
    color: rgba(255, 255, 255, 0.45);
  }
  .about-github-btn {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: rgba(255, 255, 255, 0.85);
    font-size: 0.78rem;
    font-weight: 500;
    padding: 0.4rem 0.75rem;
    border-radius: 20px;
    text-decoration: none;
    flex-shrink: 0;
    cursor: pointer;
    outline: none;
    transition: all 0.2s ease;
  }
  .about-github-btn:hover {
    background: rgba(255, 255, 255, 0.12);
    border-color: rgba(255, 255, 255, 0.2);
    color: #fff;
    transform: none !important;
  }
  .about-divider-thin {
    margin: 0.4rem 0;
    opacity: 0.6;
  }
  .about-meta-grid {
    width: 100%;
    display: grid;
    grid-template-columns: 1fr 1fr;
    row-gap: 0.6rem;
    text-align: center;
    max-width: 200px;
    margin: 0 auto;
  }
  .about-meta-grid .meta-key {
    text-align: left;
  }
  .about-meta-grid .meta-val {
    text-align: right;
  }
  .centered-header-title {
    position: absolute;
    left: 50%;
    transform: translateX(-50%);
    margin: 0;
    pointer-events: none;
  }
  .profile-theme-content {
    display: flex;
    flex-direction: column;
    padding: 1.25rem;
    gap: 1.2rem;
  }
  .theme-option-group {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    width: 100%;
  }
  .theme-group-label {
    font-size: 0.78rem;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.4);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    text-align: left;
  }
  .circular-color-picker-group {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    width: 100%;
  }
  .circular-color-input-wrapper {
    position: relative;
    width: 34px;
    height: 34px;
    border-radius: 50%;
    border: 1px solid rgba(255, 255, 255, 0.2);
    overflow: hidden;
    cursor: pointer;
    box-shadow: 0 0 10px rgba(0, 0, 0, 0.25);
    flex-shrink: 0;
  }
  .theme-color-input-circular {
    position: absolute;
    inset: -5px;
    width: calc(100% + 10px);
    height: calc(100% + 10px);
    opacity: 0;
    cursor: pointer;
  }
  .theme-color-text-input {
    flex: 1;
    padding: 0.5rem 0.75rem;
    font-size: 0.8rem;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    color: #FFFFFF;
    outline: none;
    font-family: monospace;
    transition: all 0.2s ease;
  }
  .theme-color-text-input:focus {
    border-color: rgba(255, 255, 255, 0.25);
    background: rgba(255, 255, 255, 0.05);
  }
  .wallpaper-trigger-wrapper {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
  }
  .select-wallpaper-trigger-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    flex: 1;
    padding: 0.6rem 0.8rem;
    font-size: 0.8rem;
    font-weight: 500;
    color: rgba(255, 255, 255, 0.85);
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    cursor: pointer;
    transition: all 0.2s cubic-bezier(0.23, 1, 0.32, 1);
    outline: none;
  }
  .profile-widget.light-theme .select-wallpaper-trigger-btn {
    color: rgba(15, 17, 23, 0.85);
    background: rgba(0, 0, 0, 0.03);
    border-color: rgba(0, 0, 0, 0.06);
  }
  .select-wallpaper-trigger-btn:hover {
    color: #FFFFFF;
    background: rgba(255, 255, 255, 0.08);
    border-color: rgba(255, 255, 255, 0.15);
  }
  .profile-widget.light-theme .select-wallpaper-trigger-btn:hover {
    color: rgba(15, 17, 23, 0.95);
    background: rgba(0, 0, 0, 0.06);
    border-color: rgba(0, 0, 0, 0.12);
  }
  .clear-wallpaper-btn-modern {
    background: rgba(225, 29, 46, 0.1);
    border: 1px solid rgba(225, 29, 46, 0.15);
    color: #ff4d6a;
    border-radius: 10px;
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    font-size: 0.85rem;
    transition: all 0.2s ease;
    padding: 0;
  }
  .clear-wallpaper-btn-modern:hover {
    background: rgba(225, 29, 46, 0.2);
    border-color: rgba(225, 29, 46, 0.35);
    transform: scale(1.05);
  }

  /* Wallpapers Presets Submenu Grid Styles */
  .wallpapers-preset-list {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow-y: auto;
    padding: 0.75rem 1rem;
    box-sizing: border-box;
  }
  .wallpapers-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.6rem;
    width: 100%;
    margin-bottom: 1rem;
  }
  .none-card {
    background: rgba(255, 255, 255, 0.03);
    display: flex;
    align-items: center;
    justify-content: center;
    box-sizing: border-box;
  }
  .profile-widget.light-theme .none-card {
    background: rgba(0, 0, 0, 0.03);
  }
  .wallpaper-none-placeholder {
    color: rgba(255, 255, 255, 0.35);
    display: flex;
    align-items: center;
    justify-content: center;
    transition: color 0.2s ease;
  }
  .profile-widget.light-theme .wallpaper-none-placeholder {
    color: rgba(15, 17, 23, 0.35);
  }
  .none-card:hover .wallpaper-none-placeholder {
    color: rgba(255, 255, 255, 0.7);
  }
  .profile-widget.light-theme .none-card:hover .wallpaper-none-placeholder {
    color: rgba(15, 17, 23, 0.7);
  }
  .add-card {
    background: rgba(255, 255, 255, 0.03);
    display: flex;
    align-items: center;
    justify-content: center;
    box-sizing: border-box;
  }
  .profile-widget.light-theme .add-card {
    background: rgba(0, 0, 0, 0.03);
  }
  .wallpaper-add-placeholder {
    color: rgba(255, 255, 255, 0.35);
    display: flex;
    align-items: center;
    justify-content: center;
    transition: color 0.2s ease;
  }
  .profile-widget.light-theme .wallpaper-add-placeholder {
    color: rgba(15, 17, 23, 0.35);
  }
  .add-card:hover .wallpaper-add-placeholder {
    color: rgba(255, 255, 255, 0.7);
  }
  .profile-widget.light-theme .add-card:hover .wallpaper-add-placeholder {
    color: rgba(15, 17, 23, 0.7);
  }
  .wallpaper-card {
    position: relative;
    aspect-ratio: 16 / 10;
    border-radius: 10px;
    overflow: hidden;
    cursor: pointer;
    border: 1.5px solid rgba(255, 255, 255, 0.08);
    transition: all 0.3s cubic-bezier(0.23, 1, 0.32, 1);
    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.15);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
  }
  .profile-widget.light-theme .wallpaper-card {
    border-color: rgba(0, 0, 0, 0.06);
    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.05);
  }
  .wallpaper-card:hover {
    transform: translateY(-2px) scale(1.02);
    border-color: rgba(255, 255, 255, 0.25);
    box-shadow: 0 6px 15px rgba(0, 0, 0, 0.25);
  }
  .profile-widget.light-theme .wallpaper-card:hover {
    border-color: rgba(0, 0, 0, 0.15);
    box-shadow: 0 6px 15px rgba(0, 0, 0, 0.08);
  }
  .wallpaper-card.active {
    border-color: #E11D2E !important;
    box-shadow: 0 0 12px rgba(225, 29, 46, 0.4);
  }
  .wallpaper-thumb {
    width: 100%;
    height: 100%;
    object-fit: cover;
    transition: transform 0.5s ease;
  }
  .wallpaper-card:hover .wallpaper-thumb {
    transform: scale(1.08);
  }
  .wallpaper-overlay {
    position: absolute;
    inset: 0;
    background: linear-gradient(to top, rgba(0, 0, 0, 0.8) 0%, rgba(0, 0, 0, 0) 100%);
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    padding: 0.45rem 0.55rem;
    box-sizing: border-box;
  }
  .wallpaper-name {
    font-size: 0.75rem;
    font-weight: 600;
    color: #fff;
    text-shadow: 0 1px 4px rgba(0, 0, 0, 0.8);
  }
  .wallpaper-check-icon {
    width: 18px;
    height: 18px;
    color: #4cd964;
    filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.5));
  }
  
  .delete-wallpaper-btn {
    position: absolute;
    top: 4px;
    right: 4px;
    background: rgba(0, 0, 0, 0.5);
    border: none;
    border-radius: 50%;
    padding: 0;
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #fff;
    cursor: pointer;
    opacity: 1;
    transition: all 0.2s;
  }
  .delete-wallpaper-btn:hover {
    background: rgba(255, 69, 58, 0.8);
  }
  .delete-wallpaper-btn svg {
    width: 12px;
    height: 12px;
  }

  /* --- LIGHT THEME OVERRIDES --- */
  .remove-wallpaper-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.4rem;
    width: 100%;
    padding: 0.6rem;
    background: rgba(225, 29, 46, 0.1);
    border: 1px solid rgba(225, 29, 46, 0.15);
    border-radius: 12px;
    color: #ff4d6a;
    font-size: 0.78rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.25s ease;
    margin-top: auto;
  }
  .remove-wallpaper-btn:hover {
    background: rgba(225, 29, 46, 0.18);
    border-color: rgba(225, 29, 46, 0.3);
    transform: translateY(-1px);
  }
  .custom-wallpaper-bg {
    position: absolute;
    inset: 0;
    z-index: 0;
    background-size: cover;
    background-position: center;
    pointer-events: none;
    transition: opacity 0.3s ease, filter 0.3s ease;
  }
  .wallpaper-slider-group {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    width: 82% !important;
    margin: 0 auto 1.2rem auto !important;
    box-sizing: border-box;
  }
  .slider-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
  }
  .slider-val {
    font-size: 0.75rem;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.8);
  }
  .profile-widget.light-theme .slider-val {
    color: rgba(15, 17, 23, 0.8);
  }
  /* Premium Range Slider styling */
  .theme-slider {
    -webkit-appearance: none !important;
    appearance: none !important;
    width: 100% !important;
    height: 4px !important;
    border-radius: 99px !important;
    background: rgba(255, 255, 255, 0.08) !important;
    border: none !important;
    padding: 0 !important;
    backdrop-filter: none !important;
    -webkit-backdrop-filter: none !important;
    box-shadow: none !important;
    outline: none !important;
    cursor: pointer;
    transition: background 0.2s ease;
  }
  .profile-widget.light-theme .theme-slider {
    background: rgba(0, 0, 0, 0.05) !important;
    border: none !important;
  }
  .theme-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: #E11D2E;
    border: none;
    box-shadow: 0 1px 4px rgba(0,0,0,0.3);
    transition: transform 0.1s ease, background-color 0.2s ease;
  }
  .theme-slider::-webkit-slider-thumb:hover {
    transform: scale(1.2);
    background: #ff3344;
  }
  .theme-presets-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.4rem;
    width: 100%;
  }
  .preset-btn {
    padding: 0.45rem;
    font-size: 0.75rem;
    font-weight: 500;
    color: rgba(255, 255, 255, 0.65);
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s ease;
  }
  .preset-btn:hover {
    color: #FFFFFF;
    background: rgba(255, 255, 255, 0.08);
    border-color: rgba(255, 255, 255, 0.15);
  }
  .preset-btn.active {
    color: #FFFFFF;
    background: rgba(255, 255, 255, 0.12);
    border-color: rgba(255, 255, 255, 0.3);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  }
  .mosaic-toggle-wrapper {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
  }
  .mosaic-checkbox-btn {
    background: transparent;
    border: none;
    cursor: pointer;
    padding: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    outline: none;
  }
  .custom-colors-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    margin-bottom: 0.2rem;
  }
  .add-color-btn {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    color: rgba(255, 255, 255, 0.8);
    font-size: 0.72rem;
    font-weight: 500;
    padding: 0.25rem 0.5rem;
    cursor: pointer;
    outline: none;
    transition: all 0.2s ease;
  }
  .profile-widget.light-theme .add-color-btn {
    background: rgba(0, 0, 0, 0.04);
    border-color: rgba(0, 0, 0, 0.08);
    color: rgba(15, 17, 23, 0.8);
  }
  .add-color-btn:hover {
    background: rgba(255, 255, 255, 0.1);
    border-color: rgba(255, 255, 255, 0.15);
    color: #FFFFFF;
  }
  .profile-widget.light-theme .add-color-btn:hover {
    background: rgba(0, 0, 0, 0.08);
    border-color: rgba(0, 0, 0, 0.12);
    color: rgba(15, 17, 23, 0.95);
  }
  .custom-colors-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    width: 100%;
    padding: 2px 0;
  }
  .custom-color-item {
    position: relative;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    border: 1px solid rgba(255, 255, 255, 0.15);
    cursor: pointer;
    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
    transition: transform 0.2s ease;
  }
  .profile-widget.light-theme .custom-color-item {
    border-color: rgba(0, 0, 0, 0.1);
  }
  .custom-color-item:hover {
    transform: scale(1.1);
  }
  .delete-color-btn {
    position: absolute;
    top: -5px;
    right: -5px;
    background: #E11D2E;
    border: none;
    border-radius: 50%;
    width: 13px;
    height: 13px;
    color: #FFFFFF;
    font-size: 8px;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.2s ease, transform 0.2s ease;
    box-shadow: 0 1px 3px rgba(0,0,0,0.3);
    padding: 0;
  }
  .custom-color-item:hover .delete-color-btn {
    opacity: 1;
    pointer-events: auto;
  }
  .delete-color-btn:hover {
    transform: scale(1.15);
    background: #ff3344;
  }

  /* LIGHT THEME STYLES OVERRIDE CASCADE */
  .container.light-theme,
  .clock-widget.light-theme,
  .profile-widget.light-theme {
    color: rgba(15, 17, 23, 0.9) !important;
  }
  .container.light-theme h1,
  .container.light-theme h2,
  :global(.container.light-theme h3),
  .container.light-theme p,
  .container.light-theme span,
  .container.light-theme div,
  .container.light-theme button,
  .container.light-theme input,
  .clock-widget.light-theme *,
  .profile-widget.light-theme * {
    /* Exclude accent items, color wheel sectors, and checkbox marks from global color override */
    color: inherit;
  }
  
  .profile-widget.light-theme .wallpaper-name,
  .profile-widget.light-theme .delete-wallpaper-btn {
    color: #fff !important;
  }
  
  /* Primary Text Elements */
  .container.light-theme h1,
  .container.light-theme h2,
  :global(.container.light-theme h3),
  .container.light-theme .profile-name,
  .container.light-theme .centered-header-title,
  .container.light-theme .about-developer-name,
  .container.light-theme .opt-title,
  .container.light-theme .history-title,
  .container.light-theme .track-title,
  .container.light-theme .track-row-title,
  .container.light-theme .artist-name,
  .container.light-theme .album-name,
  .clock-widget.light-theme .clock-time,
  .container.light-theme .info-val,
  .container.light-theme .meta-val,
  .container.light-theme .color-hex-label {
    color: rgba(15, 17, 23, 0.92) !important;
  }
  .profile-widget.light-theme .about-logo {
    background: none !important;
    -webkit-text-fill-color: rgba(15, 17, 23, 0.92) !important;
    color: rgba(15, 17, 23, 0.92) !important;
    filter: none;
  }
  
  /* Secondary / Muted Text Elements */
  .clock-widget.light-theme .clock-month,
  .clock-widget.light-theme .clock-day,
  .clock-widget.light-theme .clock-date,
  .container.light-theme .subtitle,
  .container.light-theme .opt-desc,
  .container.light-theme .history-url,
  .container.light-theme .track-artist,
  .container.light-theme .track-row-artist,
  .container.light-theme .track-dur,
  .container.light-theme .track-num,
  .profile-widget.light-theme .about-tagline,
  .profile-widget.light-theme .about-version,
  .profile-widget.light-theme .about-developer-handle,
  .onboarding-screen.light-theme .status-label,
  .onboarding-screen.light-theme .login-hint,
  .container.light-theme .info-label,
  .container.light-theme .meta-key,
  .container.light-theme .duration,
  .container.light-theme .theme-group-label {
    color: rgba(15, 17, 23, 0.55) !important;
  }
  
  .container.light-theme input[type="text"] {
    color: rgba(15, 17, 23, 0.92) !important;
  }
  .container.light-theme input::placeholder {
    color: rgba(15, 17, 23, 0.35) !important;
  }
  
  /* SVG icon stroke/fill styling */
  .container.light-theme svg,
  .clock-widget.light-theme svg,
  .profile-widget.light-theme svg {
    color: rgba(15, 17, 23, 0.7) !important;
  }
  
  /* Keep colors of logo sectors and other red/green indicators unchanged */
  .container.light-theme .circular-color-picker-group svg *,
  .container.light-theme .download-btn svg,
  .container.light-theme .active svg,
  .container.light-theme .delete-wallpaper-btn svg,
  .profile-widget.light-theme .delete-wallpaper-btn svg,
  .container.light-theme .bg-mosaic-item.type-0 svg,
  .container.light-theme .bg-mosaic-item.type-1 svg,
  .container.light-theme .bg-mosaic-item.type-2 svg {
    color: inherit !important;
  }
  
  /* Glass Card overrides (Remove dark frame background & shadows) */
  .container.light-theme .glass-card,
  .clock-widget.light-theme,
  .profile-widget.light-theme,
  .container.light-theme .details-layout {
    background: rgba(255, 255, 255, 0.55) !important;
    border-color: rgba(0, 0, 0, 0.06) !important;
    border-top-color: rgba(255, 255, 255, 0.6) !important;
    border-bottom-color: rgba(0, 0, 0, 0.02) !important;
    box-shadow: 
      inset 0 1px 0 rgba(255, 255, 255, 0.4),
      0 8px 32px rgba(0, 0, 0, 0.04),
      0 2px 6px rgba(0, 0, 0, 0.02) !important;
  }
  .container.light-theme .glass-card:hover,
  .clock-widget.light-theme:hover,
  .profile-widget.light-theme:hover {
    background: rgba(255, 255, 255, 0.6) !important;
    box-shadow: 
      inset 0 1px 0 rgba(255, 255, 255, 0.5),
      0 12px 36px rgba(0, 0, 0, 0.06),
      0 3px 8px rgba(0, 0, 0, 0.03) !important;
  }

  /* --- RESULT PAGE & PLAYLIST OVERRIDES --- */
  .container.light-theme .details-backdrop {
    filter: blur(60px) brightness(1.15) saturate(1.2) !important;
  }
  .container.light-theme .divider {
    background: rgba(0, 0, 0, 0.1) !important;
  }
  .container.light-theme .cover-placeholder {
    background: rgba(0, 0, 0, 0.05);
    color: rgba(0, 0, 0, 0.2);
  }
  .container.light-theme .track-row:hover:not(:disabled) {
    background: rgba(0, 0, 0, 0.05);
  }
  .container.light-theme .track-row.selected {
    background: rgba(225, 29, 46, 0.08);
  }
  .container.light-theme .track-row.selected:hover:not(:disabled) {
    background: rgba(225, 29, 46, 0.12);
  }
  .container.light-theme .track-thumb-placeholder {
    background: rgba(0, 0, 0, 0.08);
    color: rgba(0, 0, 0, 0.4);
  }
  
  /* Glass inputs and button containers inside light theme */
  .container.light-theme .profile-dropdown,
  .profile-widget.light-theme .profile-dropdown,
  .container.light-theme .format-select,
  .container.light-theme .download-btn,
  .container.light-theme .preset-btn,
  .profile-widget.light-theme .preset-btn,
  .container.light-theme .about-github-btn,
  .profile-widget.light-theme .about-github-btn,
  .container.light-theme .profile-opt-btn,
  .profile-widget.light-theme .profile-opt-btn,
  .profile-widget.light-theme .nav-btn,
  .container.light-theme .custom-dropdown-container button,
  :global(.profile-widget.light-theme .theme-text-input),
  .profile-widget.light-theme .theme-color-text-input {
    background: rgba(0, 0, 0, 0.03) !important;
    border-color: rgba(0, 0, 0, 0.06) !important;
    box-shadow: none !important;
  }
  
  /* Active states for light theme inputs/buttons */
  .container.light-theme .preset-btn.active,
  .profile-widget.light-theme .preset-btn.active {
    color: rgba(0, 0, 0, 0.95) !important;
    background: rgba(0, 0, 0, 0.08) !important;
    border-color: rgba(0, 0, 0, 0.25) !important;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05) !important;
  }
  
  /* Transparent wrappers for history elements in light theme */
  .container.light-theme .history-item-container,
  .profile-widget.light-theme .history-item-container {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
  }
  
  /* Invert GIFs in light theme */
  .container.light-theme .search-icon-gif,
  .onboarding-screen.light-theme .status-gif,
  .container.light-theme .status-gif {
    filter: invert(1);
  }
  
  /* Soft light glass integration for history buttons */
  .profile-widget.light-theme .profile-menu-item.history-item {
    background: rgba(0, 0, 0, 0.02) !important;
    border: 1px solid rgba(0, 0, 0, 0.04) !important;
    box-shadow: none !important;
  }
  .profile-widget.light-theme .profile-menu-item.history-item:hover {
    background: rgba(0, 0, 0, 0.05) !important;
    border-color: rgba(0, 0, 0, 0.1) !important;
  }
  .profile-widget.light-theme .delete-history-item-btn {
    background: rgba(0, 0, 0, 0.03) !important;
    border: 1px solid rgba(0, 0, 0, 0.06) !important;
  }
  .profile-widget.light-theme .delete-history-item-btn:hover {
    background: rgba(225, 29, 46, 0.15) !important;
    border-color: rgba(225, 29, 46, 0.3) !important;
    color: rgba(225, 29, 46, 0.9) !important;
  }
  
  /* Glass Hover States */
  .container.light-theme .profile-opt-btn:hover,
  .profile-widget.light-theme .profile-opt-btn:hover,
  .container.light-theme .preset-btn:hover,
  .profile-widget.light-theme .preset-btn:hover,
  .container.light-theme .about-github-btn:hover,
  .profile-widget.light-theme .about-github-btn:hover,
  .profile-widget.light-theme .nav-btn:hover:not(:disabled),
  .profile-widget.light-theme .nav-btn:hover:not(:disabled),
  .container.light-theme .custom-dropdown-container button:hover:not(:disabled) {
    background: rgba(0, 0, 0, 0.06) !important;
    border-color: rgba(0, 0, 0, 0.12) !important;
  }
  
  /* Dropdowns - Match glass-card transparency exactly */
  .profile-widget.light-theme .profile-dropdown {
    background: rgba(255, 255, 255, 0.55) !important;
    backdrop-filter: blur(24px) !important;
    -webkit-backdrop-filter: blur(24px) !important;
    border-color: rgba(0, 0, 0, 0.06) !important;
    border-top-color: rgba(255, 255, 255, 0.6) !important;
    border-bottom-color: rgba(0, 0, 0, 0.02) !important;
    box-shadow: 
      inset 0 1px 0 rgba(255, 255, 255, 0.4),
      0 10px 30px rgba(0, 0, 0, 0.06), 
      0 1px 1px rgba(0, 0, 0, 0.03) !important;
  }
  
  /* Divider adjustments */
  .container.light-theme .divider,
  .container.light-theme .about-divider-thin,
  .profile-widget.light-theme .profile-divider,
  .clock-widget.light-theme .clock-divider {
    background: rgba(0, 0, 0, 0.08) !important;
  }
  
  /* Custom specific components */
  .container.light-theme .about-version {
    background: rgba(0, 0, 0, 0.04) !important;
    border-color: rgba(0, 0, 0, 0.06) !important;
  }
  .container.light-theme .about-avatar {
    border-color: rgba(0, 0, 0, 0.08) !important;
  }
  
  /* Prevent hover color in light theme from turning white and washing out */
  .profile-widget.light-theme .profile-menu-item:hover,
  .profile-widget.light-theme .profile-menu-item.history-item:hover,
  .profile-widget.light-theme .profile-menu-item:hover *,
  .profile-widget.light-theme .profile-menu-item.history-item:hover * {
    color: rgba(15, 17, 23, 0.92) !important;
  }
  .profile-widget.light-theme .profile-menu-item.history-item:hover .history-url {
    color: rgba(15, 17, 23, 0.55) !important;
  }
  
  /* Background logo opacity enhancement for light contrast */
  .container.light-theme .bg-mosaic-container {
    mix-blend-mode: multiply;
  }
  .container.light-theme .bg-mosaic-grid {
    opacity: 0.12 !important;
  }
  @keyframes dropdownSlideIn {
    from {
      opacity: 0;
      transform: translateY(-12px) scale(0.96);
    }
    to {
      opacity: 1;
      transform: translateY(0) scale(1);
    }
  }
  .profile-menu-header {
    padding: 1rem;
    font-size: 0.85rem;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.5);
    text-transform: uppercase;
    letter-spacing: 1px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    display: flex;
    justify-content: space-between;
    align-items: center;
    position: relative;
  }
  .clear-history-btn {
    background: transparent;
    border: none;
    color: rgba(255, 255, 255, 0.4);
    cursor: pointer;
    padding: 6px;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
  }
  .clear-history-btn:hover {
    color: #FFFFFF;
    background: rgba(255, 255, 255, 0.08);
  }
  .clear-history-btn svg {
    width: 18px;
    height: 18px;
  }
  .profile-menu-list {
    max-height: 300px;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 0.5rem;
  }
  .profile-menu-list {
    scrollbar-width: thin;
    scrollbar-color: rgba(255, 255, 255, 0.15) transparent;
  }
  .profile-menu-list::-webkit-scrollbar {
    width: 5px;
  }
  .profile-menu-list::-webkit-scrollbar-track {
    background: transparent;
  }
  .profile-menu-list::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.15);
    border-radius: 99px;
    transition: background 0.3s ease;
  }
  .profile-menu-list::-webkit-scrollbar-thumb:hover {
    background: rgba(255, 255, 255, 0.3);
  }
  .profile-menu-empty {
    padding: 1.5rem 1rem;
    text-align: center;
    color: rgba(255, 255, 255, 0.4);
    font-size: 0.9rem;
  }
  .profile-menu-item {
    display: flex;
    align-items: center;
    gap: 0.8rem;
    width: 100%;
    padding: 0.8rem 1rem;
    background: transparent;
    border: none !important;
    box-shadow: none !important;
    border-radius: 16px;
    color: rgba(255, 255, 255, 0.9);
    font-size: 0.9rem;
    cursor: pointer;
    text-align: left;
    transition: all 0.2s;
  }
  .profile-menu-item:hover {
    background: rgba(255, 255, 255, 0.08);
    color: #fff;
    box-shadow: none !important;
    transform: none !important;
  }
  .profile-menu-item span {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .history-item-container {
    position: relative;
    width: 100%;
    margin-bottom: 0.25rem;
  }
  .profile-menu-item.history-item {
    padding: 0.5rem;
    padding-right: 2.5rem;
    gap: 0.75rem;
    border: 1px solid rgba(255, 255, 255, 0.02) !important;
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.01);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
    transition: all 0.25s cubic-bezier(0.25, 0.8, 0.25, 1);
  }
  .profile-menu-item.history-item:hover {
    transform: translateY(-1px) translateX(2px);
    background: rgba(255, 255, 255, 0.07);
    border-color: rgba(255, 255, 255, 0.12) !important;
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, 0.15),
      0 4px 12px rgba(0, 0, 0, 0.15);
  }
  .delete-history-item-btn {
    position: absolute;
    right: 0.5rem;
    top: 50%;
    transform: translateY(-50%);
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    color: rgba(255, 255, 255, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    opacity: 0;
    pointer-events: none;
    transition: all 0.2s cubic-bezier(0.23, 1, 0.32, 1);
    padding: 0;
    box-shadow: none !important;
    outline: none !important;
  }
  .delete-history-item-btn:hover {
    background: rgba(225, 29, 46, 0.2) !important;
    border-color: rgba(225, 29, 46, 0.4) !important;
    color: #ff4d6a;
    transform: translateY(-50%) scale(1.08) !important;
  }
  .history-item-container:hover .delete-history-item-btn {
    opacity: 1;
    pointer-events: auto;
  }
  .delete-history-item-btn svg {
    width: 10px;
    height: 10px;
  }
  .profile-menu-item.history-item:hover .history-cover-wrapper {
    border-color: rgba(225, 29, 46, 0.4);
    box-shadow: 0 0 8px rgba(225, 29, 46, 0.25);
  }
  .history-cover-wrapper {
    width: 40px;
    height: 40px;
    border-radius: 16px;
    overflow: hidden;
    flex-shrink: 0;
    background: rgba(255, 255, 255, 0.05);
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid rgba(255, 255, 255, 0.08);
    transition: all 0.25s ease;
  }
  .history-cover {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .history-cover-placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .history-icon-svg {
    width: 18px;
    height: 18px;
    color: rgba(255, 255, 255, 0.4);
    transition: color 0.25s ease;
  }
  .profile-menu-item.history-item:hover .history-icon-svg {
    color: rgba(225, 29, 46, 0.85);
  }
  .history-info {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    min-width: 0;
    flex: 1;
  }
  .history-title {
    font-size: 0.85rem;
    font-weight: 500;
    color: rgba(255, 255, 255, 0.95);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .history-url {
    font-size: 0.72rem;
    color: rgba(255, 255, 255, 0.4);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .toast-container {
    position: fixed;
    bottom: 2rem;
    right: 2rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    z-index: 9999;
  }

  .toast {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.08);
    color: white;
    padding: 0.85rem 1.25rem;
    border-radius: 36px;
    position: relative;
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15),
      0 8px 32px rgba(0,0,0,0.25),
      0 2px 6px rgba(0,0,0,0.12);
    max-width: 320px;
    font-size: 0.9rem;
    font-weight: 500;
  }
  .toast-icon {
    width: 18px;
    height: 18px;
    flex-shrink: 0;
  }
  .toast.error {
    background: rgba(255, 85, 85, 0.12);
    border-color: rgba(255, 85, 85, 0.35);
    color: #FFAAAA;
  }
  .toast-icon.error-icon {
    color: #FF5555;
  }
  .toast-icon.success-icon {
    color: #4ADE80;
  }
  .toast-message-text {
    line-height: 1.3;
  }
  .toast.cancel {
    background: rgba(255, 193, 7, 0.15);
    border-color: rgba(255, 193, 7, 0.4);
    color: #FFC107;
  }
  .toast-icon.cancel-icon {
    color: #FFC107;
  }

  .drag-hint {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.6rem;
    margin: 1rem 0 0.5rem 0;
    padding: 0.6rem 1rem;
    border: 1px dashed rgba(255, 255, 255, 0.08);
    border-radius: 20px;
    background: rgba(255, 255, 255, 0.02);
    color: rgba(255, 255, 255, 0.4);
    font-size: 0.85rem;
    transition: all 0.3s ease;
  }
  .drag-hint-icon {
    font-size: 1.2rem;
  }
  .drag-hint-text {
    font-weight: 400;
  }
  .container.light-theme .drag-hint {
    border-color: rgba(0, 0, 0, 0.06);
    color: rgba(0, 0, 0, 0.4);
    background: rgba(0, 0, 0, 0.01);
  }

  .retry-btn {
    margin-top: 1rem;
    padding: 0.6rem 1.5rem;
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.08);
    backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15),
      0 4px 14px rgba(0,0,0,0.18),
      0 2px 6px rgba(0,0,0,0.12);
    border-radius: 36px;
    color: white;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.3s ease;
  }

  .retry-btn:hover {
    background: rgba(255,255,255,0.04);
    border-color: rgba(255,255,255,0.12);
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.20),
      inset 0 -1px 0 rgba(0,0,0,0.12),
      0 6px 20px rgba(0,0,0,0.22),
      0 2px 8px rgba(0,0,0,0.15);
    transform: scale(1.02);
  }

  .login-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem;
  }

  /* Drag & Drop Overlay Styles */
  .drag-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(8, 10, 18, 0.85);
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    z-index: 9999;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem;
  }
  .drag-overlay-content {
    border: 2px dashed rgba(225, 29, 46, 0.4);
    background: rgba(255, 255, 255, 0.03);
    border-radius: 36px;
    padding: 3rem 2rem;
    text-align: center;
    max-width: 500px;
    width: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.05);
    transition: all 0.3s ease;
  }
  .drag-icon-wrapper {
    background: rgba(225, 29, 46, 0.1);
    border: 1px solid rgba(225, 29, 46, 0.2);
    border-radius: 50%;
    width: 80px;
    height: 80px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #FF5555;
    margin-bottom: 1.5rem;
    box-shadow: 0 0 20px rgba(225, 29, 46, 0.2);
  }
  .drag-title {
    font-family: 'Outfit', sans-serif;
    font-size: 1.5rem;
    font-weight: 600;
    color: #FFFFFF;
    margin: 0 0 0.75rem 0;
  }
  .drag-subtitle {
    font-family: 'Inter', sans-serif;
    font-size: 0.95rem;
    color: rgba(255, 255, 255, 0.7);
    margin: 0;
    line-height: 1.5;
  }
  .url-preview {
    color: #FF5555;
    font-weight: 500;
    word-break: break-all;
  }
  /* Manual Pairing Input Styles */
  .pairing-container {
    margin-bottom: 0.5rem;
    width: 100%;
  }
  .pairing-input-wrapper {
    position: relative;
    display: flex;
    align-items: center;
    background: rgba(255,255,255,0.02);
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 36px;
    padding: 0 0.75rem;
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15),
      0 4px 12px rgba(0,0,0,0.12);
    transition: all 0.3s cubic-bezier(0.23, 1, 0.32, 1);
  }
  .pairing-input-wrapper:hover {
    border-color: rgba(255,255,255,0.12);
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.20),
      inset 0 -1px 0 rgba(0,0,0,0.12),
      0 8px 24px rgba(0,0,0,0.20);
  }
  .pairing-input-wrapper:focus-within {
    border-color: rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.04);
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.20),
      inset 0 -1px 0 rgba(0,0,0,0.12),
      0 8px 24px rgba(0,0,0,0.20);
    outline: none;
  }
  .pairing-icon {
    font-size: 0.95rem;
    opacity: 0.6;
    margin-right: 0.5rem;
    user-select: none;
  }
  .pairing-input-wrapper input.pairing-input {
    flex: 1;
    background: transparent;
    border: none;
    box-shadow: none;
    padding: 0.75rem 0.25rem;
    font-size: 0.9rem;
    color: rgba(255, 255, 255, 0.9);
    font-family: 'Inter', sans-serif;
    outline: none;
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
    border-radius: 0;
  }
  .pairing-input-wrapper input.pairing-input::placeholder {
    color: rgba(255, 255, 255, 0.3);
  }
  .clear-pairing-btn {
    background: transparent;
    border: none;
    color: rgba(255, 255, 255, 0.4);
    font-size: 0.8rem;
    cursor: pointer;
    width: 22px;
    height: 22px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    transition: all 0.2s ease;
    flex-shrink: 0;
    line-height: 1;
    padding: 0;
  }
  .clear-pairing-btn:hover {
    color: #fff;
    background: rgba(255, 255, 255, 0.1);
  }

  /* Skeleton Loading Styles */
  .skeleton-pulse {
    animation: skeleton-pulse-anim 1.5s infinite ease-in-out;
  }
  @keyframes skeleton-pulse-anim {
    0% { opacity: 0.6; }
    50% { opacity: 0.3; }
    100% { opacity: 0.6; }
  }
  .skeleton-icon {
    font-size: 3.5rem;
    color: rgba(255, 255, 255, 0.15);
  }
  .skeleton-line {
    background: linear-gradient(90deg, rgba(255,255,255,0.03) 25%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.03) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite linear;
    border-radius: 8px;
  }
  @keyframes shimmer {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }
  .title-skeleton {
    width: 60%;
    height: 1.8rem;
    margin-bottom: 0.5rem;
  }
  .artist-skeleton {
    width: 40%;
    height: 1.1rem;
    margin-bottom: 1.5rem;
  }
  .skeleton-text {
    color: rgba(255, 255, 255, 0.35) !important;
  }
  .inline-status {
    display: block;
    margin-top: 1rem;
  }

  .cover-placeholder.error-placeholder-icon {
    background: linear-gradient(135deg, rgba(255, 85, 85, 0.08) 0%, rgba(255, 85, 85, 0.02) 100%);
    border: 1px solid rgba(255, 85, 85, 0.15);
    box-shadow: inset 0 1px 0 rgba(255, 85, 85, 0.15);
  }
  .warning-icon {
    font-size: 3.5rem;
    color: rgba(255, 85, 85, 0.65);
    animation: warning-pulse-anim 2s infinite ease-in-out;
  }
  @keyframes warning-pulse-anim {
    0% { transform: scale(1); opacity: 0.8; }
    50% { transform: scale(1.05); opacity: 0.5; }
    100% { transform: scale(1); opacity: 0.8; }
  }
  .meta-badge.error {
    background: rgba(255, 85, 85, 0.12);
    border-color: rgba(255, 85, 85, 0.25);
    color: rgba(255, 85, 85, 0.85);
  }
  .error-message-text {
    font-size: 1.15rem;
    font-weight: 500;
    color: rgba(255, 85, 85, 0.85);
    margin: 0.2rem 0 1.25rem;
    line-height: 1.4;
  }

  .metadata-preview-card {
    margin-top: 0.75rem;
    position: relative;
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 36px;
    padding: 0.85rem;
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15),
      0 8px 24px rgba(0,0,0,0.20),
      0 2px 6px rgba(0,0,0,0.12);
  }
  .preview-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  }
  .preview-badge {
    font-family: 'Outfit', sans-serif;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: rgba(255, 255, 255, 0.5);
  }
  .preview-source-badge {
    font-size: 0.7rem;
    font-weight: 600;
    padding: 0.2rem 0.5rem;
    border-radius: 6px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .preview-source-badge.spotify {
    background: rgba(30, 215, 96, 0.15);
    color: #1ED760;
    border: 1px solid rgba(30, 215, 96, 0.3);
  }
  .preview-source-badge.ytmusic {
    background: rgba(255, 0, 0, 0.15);
    color: #FF3333;
    border: 1px solid rgba(255, 0, 0, 0.3);
  }
  .preview-source-badge.youtube {
    background: rgba(255, 0, 0, 0.15);
    color: #FF0000;
    border: 1px solid rgba(255, 0, 0, 0.3);
  }
  .preview-body {
    display: flex;
    gap: 0.75rem;
    align-items: center;
  }
  .preview-cover-img {
    width: 60px;
    height: 60px;
    border-radius: 16px;
    object-fit: cover;
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    border: 1px solid rgba(255,255,255,0.08);
  }
  .preview-cover-placeholder {
    width: 60px;
    height: 60px;
    border-radius: 16px;
    background: #1A1C23;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.5rem;
    color: #2A2D35;
    border: 1px solid rgba(255,255,255,0.08);
  }
  .preview-details {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }
  .preview-title {
    font-family: 'Inter', sans-serif;
    font-size: 0.95rem;
    font-weight: 600;
    color: #FFFFFF;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .preview-artist {
    font-family: 'Inter', sans-serif;
    font-size: 0.82rem;
    color: rgba(255, 255, 255, 0.7);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .preview-album, .preview-year {
    font-family: 'Inter', sans-serif;
    font-size: 0.78rem;
    color: rgba(255, 255, 255, 0.4);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .preview-status {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 0.5rem;
    font-size: 0.85rem;
    color: rgba(255, 255, 255, 0.5);
  }
  .spinner-icon {
    display: inline-block;
    animation: spin 1s linear infinite;
  }
  .preview-error {
    margin-top: 0.5rem;
    font-size: 0.85rem;
    color: #FF5555;
  }

  @media (max-width: 900px) {
    /* Compact Clock Widget */
    .clock-widget {
      left: 2rem;
      padding: 0.3rem 0.8rem;
      gap: 0.5rem;
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15);
  }
    .clock-month {
      font-size: 0.8rem;
    }
    .clock-day {
      font-size: 1.4rem;
    }
    .clock-divider {
      height: 28px;
    }
    .clock-time {
      font-size: 1.0rem;
    }

    /* Compact Profile Widget */
    .profile-widget {
      right: 2.4rem;
      padding: 0.3rem;
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15);
  }
    .profile-btn {
      padding: 0.2rem 0.8rem 0.2rem 0.8rem;
      gap: 0.6rem;
    }
    .profile-avatar {
      width: 36px;
      height: 36px;
    }
    .profile-name {
      font-size: 1.0rem;
    }
    .profile-divider {
      height: 24px;
      margin: 0 0.4rem;
    }
    .nav-btn {
      width: 36px;
      height: 36px;
      font-size: 1.5rem;
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15);
  }
    .nav-btn svg {
      width: 16px;
      height: 16px;
    }
    .nav-arrows-inline {
      gap: 0.3rem;
    }

    /* Adjust Header and keep it centered */
    header {
      text-align: center;
    }
    h1 {
      font-size: 2.8rem;
    }
    header.compact h1 {
      font-size: 1.8rem;
    }
  }



  @media (max-width: 650px) {
    header.compact {
      left: 11rem;
      right: 11rem;
    }
  }

  /* For extremely narrow screens */
  @media (max-width: 650px) {
    .profile-name,
    .profile-divider {
      display: none;
    }
    .profile-btn {
      padding: 0.2rem;
      width: auto;
      gap: 0;
    }
  }

  /* Custom checkbox styles */
  .track-check-wrapper {
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    width: 20px;
    height: 20px;
  }
  .custom-checkbox {
    width: 16px;
    height: 16px;
    border-radius: 12px;
    border: 1.5px solid rgba(255, 255, 255, 0.25);
    background: transparent;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.22s cubic-bezier(0.22, 1, 0.36, 1);
    box-sizing: border-box;
  }
  .custom-checkbox.checked {
    background: #E11D2E;
    border-color: #E11D2E;
    box-shadow: 0 0 8px rgba(225, 29, 46, 0.35);
  }
  .custom-checkbox svg {
    width: 11px;
    height: 11px;
    color: #FFFFFF;
    stroke-dasharray: 20;
    stroke-dashoffset: 0;
    animation: drawCheck 0.22s cubic-bezier(0.22, 1, 0.36, 1) forwards;
  }
  @keyframes drawCheck {
    from {
      stroke-dashoffset: 20;
      transform: scale(0.7);
    }
    to {
      stroke-dashoffset: 0;
      transform: scale(1);
    }
  }
  .track-row:hover .custom-checkbox:not(.checked) {
    border-color: rgba(225, 29, 46, 0.6);
  }

  /* Responsive Grid Stacking for Details Layout */
  @media (max-width: 850px) {
    .details-layout {
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
      padding: 1.5rem;
      overflow-y: auto;
      align-items: stretch;
      scrollbar-width: thin;
      scrollbar-color: rgba(225, 29, 46, 0.2) transparent;
    }
    .details-layout::-webkit-scrollbar {
      width: 5px;
    }
    .details-layout::-webkit-scrollbar-track {
      background: transparent;
    }
    .details-layout::-webkit-scrollbar-thumb {
      background: rgba(225, 29, 46, 0.2);
      border-radius: 99px;
    }
    .details-layout::-webkit-scrollbar-thumb:hover {
      background: rgba(225, 29, 46, 0.45);
    }
    .cover-col {
      width: clamp(160px, 22vh, 200px);
      margin: 0 auto;
      flex-shrink: 0;
      display: flex;
      flex-direction: column;
      align-items: center;
    }
    .meta-col {
      width: 100%;
      height: auto;
      flex: none;
      display: flex;
      flex-direction: column;
      overflow: visible;
    }
    .track-title {
      text-align: center;
      font-size: 1.3rem;
    }
    .track-artist {
      text-align: center;
      font-size: 0.9rem;
    }
    .playlist-controls {
      justify-content: center;
      margin-bottom: 0.25rem;
    }
    .meta-grid {
      grid-template-columns: 75px 1fr;
      row-gap: 0.35rem;
    }
    .meta-top {
      flex: none;
      overflow: visible;
      max-height: none;
      padding-right: 0;
    }
    .track-list {
      flex: none;
      min-height: 120px;
      max-height: 200px;
      overflow-y: auto;
    }
    .save-cover-btn {
      width: fit-content;
      margin: 0.5rem auto 0;
      padding: 0 1.25rem;
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15);
  }
    .meta-bottom {
      margin-top: 0.75rem;
      flex-shrink: 0;
    }
  }

  .custom-dropdown-container {
    position: relative;
    display: inline-block;
  }
  .custom-dropdown-menu {
    position: absolute;
    bottom: 100%;
    left: 0;
    margin-bottom: 8px;
    min-width: 100%;
    background: rgba(0, 0, 0, 0.45);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,0.15),
      inset 0 -1px 0 rgba(0,0,0,0.15),
      0 10px 40px rgba(0,0,0,0.35),
      0 2px 8px rgba(0,0,0,0.15);
    overflow: hidden;
    display: flex;
    flex-direction: column;
    z-index: 500;
    /* animation removed in favor of Svelte transition */
  }
  .custom-dropdown-item {
    width: 100%;
    text-align: left;
    padding: 0.75rem 1rem;
    background: transparent;
    border: none !important;
    border-radius: 12px;
    box-shadow: none !important;
    color: rgba(255, 255, 255, 0.9);
    font-size: 0.9rem;
    font-family: inherit;
    cursor: pointer;
    transition: background 0.2s;
  }
  .custom-dropdown-item:hover {
    background: rgba(255, 255, 255, 0.08);
    color: #fff;
    box-shadow: none !important;
    transform: none !important;
  }

</style>