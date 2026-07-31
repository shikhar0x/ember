<script lang="ts">
  import Titlebar from '$lib/Titlebar.svelte';
  import ResizeBorders from '$lib/ResizeBorders.svelte';
  import { onMount } from 'svelte';
  import type { Snippet } from 'svelte';
  import { isTauri } from '@tauri-apps/api/core';

  let { children }: { children: Snippet } = $props();

  let isTauriEnv = $state(false);
  let isMaximized = $state(false);

  /** Tags and selectors that should NOT trigger window dragging */
  const INTERACTIVE_TAGS = new Set([
    'BUTTON', 'INPUT', 'TEXTAREA', 'SELECT', 'A',
    'IFRAME', 'VIDEO', 'AUDIO', 'CANVAS', 'LABEL',
    'DETAILS', 'SUMMARY'
  ]);

  const INTERACTIVE_ROLES = new Set([
    'button', 'link', 'textbox', 'slider', 'checkbox',
    'radio', 'switch', 'tab', 'menuitem', 'option',
    'combobox', 'spinbutton', 'scrollbar'
  ]);

  /** Check if an element or any ancestor up to the root is interactive */
  function isInteractiveElement(el: HTMLElement | null): boolean {
    while (el && el !== document.documentElement) {
      // Check tag
      if (INTERACTIVE_TAGS.has(el.tagName)) return true;

      // Check ARIA role
      const role = el.getAttribute('role');
      if (role && INTERACTIVE_ROLES.has(role)) return true;

      // Check contenteditable
      if (el.isContentEditable) return true;

      // Check resize borders/corners
      if (el.classList.contains('resize-edge') || el.classList.contains('resize-corner')) return true;

      // Check window control buttons
      if (el.classList.contains('win-btn')) return true;

      // Check elements that opt out of dragging
      if (el.dataset.noDrag !== undefined) return true;

      el = el.parentElement;
    }
    return false;
  }

  /** Check if the direct click target has an interactive cursor */
  function hasInteractiveCursor(el: HTMLElement): boolean {
    const style = getComputedStyle(el);
    return style.cursor === 'pointer' || style.cursor === 'text' ||
           style.cursor.includes('resize');
  }

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

        // Global mousedown handler for window dragging
        document.addEventListener('mousedown', (e: MouseEvent) => {
          // Only left mouse button
          if (e.button !== 0) return;

          const target = e.target as HTMLElement;
          if (!target) return;

          // Don't drag if clicking on an interactive element
          if (isInteractiveElement(target)) return;

          // Don't drag if the clicked element itself has an interactive cursor
          if (hasInteractiveCursor(target)) return;

          // Start dragging the window
          appWindow.startDragging();
        });
      });
    }
  });
</script>

<div class="app-root" class:is-floating={isTauriEnv && !isMaximized}>
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
