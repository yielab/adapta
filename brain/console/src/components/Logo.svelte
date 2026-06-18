<script lang="ts">
  let { size = 24 }: { size?: number } = $props();
</script>

<!-- the "zero node" mark — three nodes (knowledge · brand · behavior)
     inside the ring. colors driven by CSS tokens so dark/light themes work. -->
<svg
  width={size}
  height={size}
  viewBox="0 0 64 64"
  fill="none"
  xmlns="http://www.w3.org/2000/svg"
  aria-hidden="true"
  class="logo-mark"
>
  <circle cx="32" cy="32" r="20" stroke="var(--brand)" stroke-width="3"/>
  <circle cx="32" cy="20" r="3.6" fill="var(--knowledge)"/>
  <circle cx="22" cy="40" r="3.6" fill="var(--brand)"/>
  <circle cx="42" cy="40" r="3.6" fill="var(--behavior)"/>
  <path
    d="M32 20 L22 40 M32 20 L42 40 M22 40 L42 40"
    stroke="var(--brand)"
    stroke-width="2"
    stroke-opacity="0.5"
    stroke-linecap="round"
  />
</svg>

<style>
  .logo-mark { flex-shrink: 0; }
</style>
