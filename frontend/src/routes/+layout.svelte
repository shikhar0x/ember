<script lang="ts">
  import Titlebar from '$lib/Titlebar.svelte';
  import ResizeBorders from '$lib/ResizeBorders.svelte';
  import { onMount } from 'svelte';
  import type { Snippet } from 'svelte';
  import { isTauri } from '@tauri-apps/api/core';

  let { children }: { children: Snippet } = $props();

  let isTauriEnv = $state(false);
  let isMaximized = $state(false);

  $effect(() => {
    if (typeof document !== 'undefined') {
      document.documentElement.style.setProperty('--titlebar-offset', '0px');
    }
  });

  onMount(() => {
    isTauriEnv = isTauri();
    if (isTauriEnv) {
      import('@tauri-apps/api/window').then(async ({ getCurrentWindow }) => {
        const appWindow = getCurrentWindow();
        isMaximized = await appWindow.isMaximized();

        await appWindow.onResized(async () => {
          isMaximized = await appWindow.isMaximized();
        });
      });
    }
  });
</script>

<div data-tauri-drag-region class="app-root" class:is-floating={isTauriEnv && !isMaximized}>
  {#if isTauriEnv && !isMaximized}
    <ResizeBorders />
  {/if}
  <Titlebar />

  {@render children()}
</div>

<style>
  :global(:root) {
    --titlebar-offset: 0px;
    background-color: transparent !important;
  }

  :global(html, body) {
    margin: 0;
    padding: 0;
    background-color: transparent !important;
    background: transparent !important;
    overflow: hidden;
  }

  .app-root {
    width: 100vw;
    height: 100vh;
    box-sizing: border-box;
    overflow: hidden;
    transition: border-radius 0.2s ease, border-color 0.2s ease;
  }

  .app-root.is-floating {
    border-radius: 12px;
    overflow: hidden;
    contain: paint;
  }
</style>
