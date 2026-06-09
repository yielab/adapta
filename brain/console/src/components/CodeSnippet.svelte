<script lang="ts">
  let { code, title = "" }: { code: string; title?: string } = $props();

  let copied = $state(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      copied = true;
      setTimeout(() => (copied = false), 1500);
    } catch {
      // Clipboard unavailable (insecure context) — the code stays selectable.
    }
  }
</script>

<div class="snippet">
  <div class="row between bar">
    {#if title}<h3 style="margin: 0;">{title}</h3>{:else}<span></span>{/if}
    <button class="ghost sm" onclick={copy}>{copied ? "copied" : "copy"}</button>
  </div>
  <pre class="code">{code}</pre>
</div>

<style>
  .snippet { width: 100%; }
  .bar { margin-bottom: 6px; }
</style>
