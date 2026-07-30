<script lang="ts">
  import { isTauri } from '@tauri-apps/api/core';

  async function toggleMaximize() {
    if (isTauri()) {
      const { getCurrentWindow } = await import('@tauri-apps/api/window');
      const appWindow = getCurrentWindow();
      if (await appWindow.isMaximized()) {
        await appWindow.unmaximize();
      } else {
        await appWindow.maximize();
      }
    }
  }
</script>

<div data-tauri-drag-region class="titlebar" role="toolbar" tabindex="-1" on:dblclick={toggleMaximize}></div>

<style>
  .titlebar {
    height: 28px;
    background: transparent;
    user-select: none;
    -webkit-user-select: none;
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 999;
    pointer-events: auto;
  }
</style>
