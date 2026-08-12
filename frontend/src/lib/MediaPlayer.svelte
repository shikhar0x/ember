<script lang="ts">
  import { onMount, onDestroy } from "svelte";

  export let currentTrackTitle = "No track loaded";
  export let currentArtist = "Ember Audio Studio";
  export let currentCoverUrl = "/favicon.png";
  export let audioUrl = "";
  export let isLocal = false;
  export let onSaveToLibrary: (() => void) | null = null;

  let audioElement: HTMLAudioElement;
  let canvasElement: HTMLCanvasElement;

  let audioCtx: AudioContext | null = null;
  let analyser: AnalyserNode | null = null;
  let eqFilters: BiquadFilterNode[] = [];
  let animFrameId: number;

  let isPlaying = false;
  let currentTime = 0;
  let duration = 0;
  let activeStyle = "flat";

  const EQ_BANDS = [60, 170, 310, 1000, 3000, 12000];

  const STYLE_PRESETS: Record<string, number[]> = {
    flat:       [ 0,  0,  0,  0,  0,  0],
    bass_boost: [ 7,  5,  2,  0, -1, -2],
    vocal:      [-2, -1,  2,  5,  4,  1],
    electronic: [ 5,  3,  0,  2,  4,  6],
  };

  function setupWebAudio() {
    if (audioCtx) {
      if (audioCtx.state === "suspended") {
        audioCtx.resume().then(() => {
          console.log("[Ember MediaPlayer] AudioContext resumed -> audio routed to speakers!");
        });
      }
      return;
    }

    try {
      audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
      const source = audioCtx.createMediaElementSource(audioElement);

      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 64;
      analyser.smoothingTimeConstant = 0.82;

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

      previousNode.connect(analyser);
      analyser.connect(audioCtx.destination);

      if (audioCtx.state === "suspended") {
        audioCtx.resume().then(() => {
          console.log("[Ember MediaPlayer] AudioContext resumed -> audio routed to speakers!");
        });
      }

      drawVisualizer();
      console.log("[Ember MediaPlayer] Web Audio API initialized, state:", audioCtx.state);
    } catch (e) {
      console.error("[Ember MediaPlayer] Web Audio API error:", e);
    }
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
      const barHeight = Math.max(3, (value / 255) * canvasElement.height);

      const red = 255;
      const green = Math.max(70, 160 - i * 4);
      const blue = 40;
      ctx.fillStyle = `rgb(${red}, ${green}, ${blue})`;

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

  $: if (audioUrl && audioElement) {
    console.log("[Ember MediaPlayer] new audioUrl requested:", audioUrl);
    audioElement.play().then(() => {
      console.log("[Ember MediaPlayer] audioElement.play() succeeded!");
      setupWebAudio();
      isPlaying = true;
    }).catch((e) => {
      console.error("[Ember MediaPlayer] audioElement.play() FAILED:", e);
    });
  }

  onDestroy(() => {
    if (animFrameId) cancelAnimationFrame(animFrameId);
    if (audioCtx) audioCtx.close();
  });
</script>

<div
  style="position: fixed; bottom: 0; left: 0; right: 0; height: 84px; z-index: 9999999 !important; background: rgba(18, 20, 26, 0.98); border-top: 1px solid rgba(255, 94, 98, 0.4); box-shadow: 0 -12px 35px rgba(0, 0, 0, 0.9);"
  class="px-6 flex items-center justify-between select-none"
>
  <audio
    bind:this={audioElement}
    src={audioUrl}
    autoplay
    crossorigin="anonymous"
    on:play={() => { console.log("[Ember MediaPlayer] on:play event"); setupWebAudio(); isPlaying = true; }}
    on:pause={() => { console.log("[Ember MediaPlayer] on:pause event"); isPlaying = false; }}
    on:waiting={() => console.log("[Ember MediaPlayer] on:waiting -> buffering audio stream...")}
    on:error={() => console.error("[Ember MediaPlayer] on:error -> HTMLAudioElement error:", audioElement?.error)}
    on:timeupdate={() => (currentTime = audioElement.currentTime)}
    on:loadedmetadata={() => { console.log("[Ember MediaPlayer] on:loadedmetadata -> duration:", audioElement.duration); duration = audioElement.duration; }}
    on:ended={() => (isPlaying = false)}
  ></audio>

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

  <div class="flex flex-col items-center justify-center flex-1 max-w-xl px-4">
    <div class="flex items-center gap-6 mb-1">
      <button
        on:click={togglePlay}
        class="w-10 h-10 rounded-full bg-gradient-to-tr from-amber-500 to-orange-600 flex items-center justify-center text-white shadow-lg hover:brightness-110 active:scale-95 transition"
      >
        <span class="text-lg ml-0.5">{isPlaying ? "⏸" : "▶"}</span>
      </button>

      <div class="w-48 h-9 bg-neutral-950/60 rounded-md border border-neutral-800/80 px-2 flex items-center justify-center">
        <canvas bind:this={canvasElement} width="180" height="28" class="w-full h-full"></canvas>
      </div>
    </div>

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

  <div class="flex items-center justify-end gap-4 w-1/4 min-w-[220px]">
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
