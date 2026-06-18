<script lang="ts">
  import { toasts, dismissToast } from "../lib/toast";

  let copiedId = $state<number | null>(null);

  async function copyCorrelationId(id: number, cid: string) {
    try {
      await navigator.clipboard.writeText(cid);
      copiedId = id;
      setTimeout(() => {
        if (copiedId === id) copiedId = null;
      }, 1500);
    } catch {
      // Clipboard can fail (insecure context / denied permission) — silently
      // ignore; the id is still visible on screen for manual copy.
    }
  }
</script>

<div class="toasts">
  {#each $toasts as t (t.id)}
    <div class="toast {t.kind}">
      <div class="grow">
        <div class="msg">{t.message}</div>
        {#if t.correlationId}
          <div class="row" style="gap: 8px; margin-top: 6px;">
            <code class="mono cid">{t.correlationId}</code>
            <button class="ghost sm" onclick={() => copyCorrelationId(t.id, t.correlationId!)}>
              {copiedId === t.id ? "copied" : "copy id"}
            </button>
          </div>
        {/if}
      </div>
      <button class="ghost sm close" aria-label="Dismiss" onclick={() => dismissToast(t.id)}>×</button>
    </div>
  {/each}
</div>

<style>
  .toasts {
    position: fixed;
    bottom: 18px;
    right: 18px;
    z-index: 1000;
    display: flex;
    flex-direction: column;
    gap: 10px;
    max-width: 420px;
  }
  .toast {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-left-width: 3px;
    border-radius: var(--radius);
    padding: 12px 14px;
    box-shadow: 0 6px 22px rgba(0, 0, 0, 0.4);
  }
  .toast.error { border-left-color: var(--red); }
  .toast.success { border-left-color: var(--green); }
  .toast.info { border-left-color: var(--accent); }
  .msg { font-size: 13.5px; }
  .cid {
    font-size: 11.5px;
    color: var(--muted);
    background: var(--panel-2);
    padding: 2px 6px;
    border-radius: 5px;
    word-break: break-all;
  }
  .close {
    font-size: 18px;
    line-height: 1;
    padding: 0 6px;
  }
</style>
