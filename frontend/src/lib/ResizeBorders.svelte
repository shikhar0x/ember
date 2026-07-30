<script lang="ts">
  import { isTauri } from '@tauri-apps/api/core';

  async function startResize(e: MouseEvent, direction: 'Top' | 'Bottom' | 'Left' | 'Right' | 'TopLeft' | 'TopRight' | 'BottomLeft' | 'BottomRight') {
    if (e.button !== 0) return; // Only left click
    if (isTauri()) {
      const { getCurrentWindow } = await import('@tauri-apps/api/window');
      const appWindow = getCurrentWindow();
      // @ts-ignore
      await appWindow.startResizing(direction);
    }
  }
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

<!-- Edge Resizers -->
<div class="resize-edge top" role="presentation" onmousedown={(e) => startResize(e, 'Top')} ondblclick={toggleMaximize}></div>
<div class="resize-edge bottom" role="presentation" onmousedown={(e) => startResize(e, 'Bottom')}></div>
<div class="resize-edge left" role="presentation" onmousedown={(e) => startResize(e, 'Left')}></div>
<div class="resize-edge right" role="presentation" onmousedown={(e) => startResize(e, 'Right')}></div>

<!-- Corner Resizers -->
<div class="resize-corner top-left" role="presentation" onmousedown={(e) => startResize(e, 'TopLeft')}></div>
<div class="resize-corner top-right" role="presentation" onmousedown={(e) => startResize(e, 'TopRight')}></div>
<div class="resize-corner bottom-left" role="presentation" onmousedown={(e) => startResize(e, 'BottomLeft')}></div>
<div class="resize-corner bottom-right" role="presentation" onmousedown={(e) => startResize(e, 'BottomRight')}></div>

<style>
  .resize-edge, .resize-corner {
    position: fixed;
    z-index: 9999;
    background: transparent;
  }

  /* Edges */
  .resize-edge.top {
    top: 0;
    left: 8px;
    right: 8px;
    height: 5px;
    cursor: n-resize;
  }
  .resize-edge.bottom {
    bottom: 0;
    left: 8px;
    right: 8px;
    height: 5px;
    cursor: s-resize;
  }
  .resize-edge.left {
    top: 8px;
    bottom: 8px;
    left: 0;
    width: 5px;
    cursor: w-resize;
  }
  .resize-edge.right {
    top: 8px;
    bottom: 8px;
    right: 0;
    width: 5px;
    cursor: e-resize;
  }

  /* Corners */
  .resize-corner.top-left {
    top: 0;
    left: 0;
    width: 8px;
    height: 8px;
    cursor: nw-resize;
  }
  .resize-corner.top-right {
    top: 0;
    right: 0;
    width: 8px;
    height: 8px;
    cursor: ne-resize;
  }
  .resize-corner.bottom-left {
    bottom: 0;
    left: 0;
    width: 8px;
    height: 8px;
    cursor: sw-resize;
  }
  .resize-corner.bottom-right {
    bottom: 0;
    right: 0;
    width: 8px;
    height: 8px;
    cursor: se-resize;
  }
</style>
