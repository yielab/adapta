<script lang="ts">
  // Maps any backend status/lifecycle string onto a design-system badge color.
  // Covers file/dataset/job/endpoint statuses plus the eval-gate verdicts
  // (PASSED/BLOCKED). Unknown values fall through to the neutral blue badge.
  let { status, label }: { status: string; label?: string } = $props();

  const GREEN = new Set([
    "indexed", "valid", "succeeded", "active", "passed", "ready", "uploaded",
  ]);
  const RED = new Set([
    "failed", "invalid", "cancelled", "blocked", "revoked", "error",
  ]);
  const AMBER = new Set([
    "pending", "processing", "validating", "queued", "running", "synthesizing",
  ]);

  const color = $derived.by(() => {
    const s = (status ?? "").toLowerCase();
    if (GREEN.has(s)) return "green";
    if (RED.has(s)) return "red";
    if (AMBER.has(s)) return "amber";
    return "blue";
  });

  const text = $derived(label ?? status ?? "unknown");
</script>

<span class="badge {color}">
  <span class="dot"></span>{text}
</span>
