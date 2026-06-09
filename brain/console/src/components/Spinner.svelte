<script lang="ts">
  // Minimal spinner — wraps the .spinner design-system class so callers don't
  // hand-roll the markup. Optional inline label for "loading…" affordances.
  let { label = "" }: { label?: string } = $props();
</script>

<span class="row" style="gap: 8px;">
  <span class="spinner"></span>
  {#if label}<small>{label}</small>{/if}
</span>
