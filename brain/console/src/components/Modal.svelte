<script lang="ts">
  import type { Snippet } from "svelte";

  let {
    title = "",
    onclose,
    children,
  }: { title?: string; onclose?: () => void; children?: Snippet } = $props();

  function close() {
    onclose?.();
  }

  function onBackdrop(e: MouseEvent) {
    // Only close on a click that started and ended on the backdrop itself.
    if (e.target === e.currentTarget) close();
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === "Escape") close();
  }
</script>

<svelte:window onkeydown={onKey} />

<div
  class="backdrop"
  role="presentation"
  onclick={onBackdrop}
>
  <div class="card modal" role="dialog" aria-modal="true" aria-label={title || "Dialog"}>
    {#if title}
      <div class="row between" style="margin-bottom: 14px;">
        <h2 style="margin: 0;">{title}</h2>
        <button class="ghost sm" aria-label="Close" onclick={close}>×</button>
      </div>
    {/if}
    {@render children?.()}
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 900;
    background: rgba(0, 0, 0, 0.55);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
  }
  .modal {
    width: 100%;
    max-width: 480px;
    max-height: 88vh;
    overflow-y: auto;
  }
</style>
