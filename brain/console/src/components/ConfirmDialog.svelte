<script lang="ts">
  import Modal from "./Modal.svelte";

  // Svelte 5 uses callback props rather than createEventDispatcher; callers pass
  // onconfirm / oncancel. Defaults make this a destructive-action confirm.
  let {
    title = "Are you sure?",
    message = "",
    confirmLabel = "Confirm",
    cancelLabel = "Cancel",
    danger = true,
    busy = false,
    onconfirm,
    oncancel,
  }: {
    title?: string;
    message?: string;
    confirmLabel?: string;
    cancelLabel?: string;
    danger?: boolean;
    busy?: boolean;
    onconfirm?: () => void;
    oncancel?: () => void;
  } = $props();
</script>

<Modal {title} onclose={() => oncancel?.()}>
  {#if message}<p>{message}</p>{/if}
  <div class="row between" style="margin-top: 18px;">
    <button class="ghost" onclick={() => oncancel?.()} disabled={busy}>{cancelLabel}</button>
    <button
      class={danger ? "danger" : "primary"}
      onclick={() => onconfirm?.()}
      disabled={busy}
    >
      {#if busy}<span class="spinner"></span>{/if}
      {confirmLabel}
    </button>
  </div>
</Modal>
