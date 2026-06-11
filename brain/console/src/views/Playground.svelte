<script lang="ts">
  // Test playground — the exact path a customer app takes: POST /v1/chat/completions
  // with the endpoint slug as `model` and a scoped brn_ key as the bearer token.
  // The console JWT does NOT work here, so the operator must supply a brn_ key.
  // We prefill the last key generated in the Endpoint tab (held in memory only),
  // and otherwise accept a pasted one. (TODO §5.8)
  import { onDestroy } from "svelte";
  import { api, ApiError } from "../lib/api";
  import { toastError } from "../lib/toast";
  import { getRememberedKey } from "../lib/keyvault";
  import type {
    Project,
    Endpoint,
    ChatCompletion,
    ChatContentPart,
    Citation,
    WireChatMessage,
  } from "../lib/types";

  let { project }: { project: Project } = $props();

  interface ChatMsg {
    role: "user" | "assistant";
    content: string;
    imageUrl?: string; // data URL of the image sent with this turn (vision)
    citations?: Citation[];
    usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
  }

  // ── vision (§V5.2) ─────────────────────────────────────────────────────────
  // Modality follows the endpoint's base model, resolved from the catalog.
  let isVision = $state(false);
  $effect(() => {
    const base = endpoint?.base_model;
    if (!base) {
      isVision = false;
      return;
    }
    void api
      .listModels()
      .then((models) => {
        isVision = models.find((m) => m.name === base)?.modality === "vision";
      })
      .catch(() => {
        /* fall back to text-only UI; the server enforces modality anyway */
      });
  });

  const MAX_IMAGE_MB = 10; // mirrors the server's per-image cap
  let attachedImage = $state<string | null>(null); // data URL
  let attachedName = $state("");
  let imgInput = $state<HTMLInputElement | null>(null);

  function onImagePicked(ev: Event) {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    if (file.size > MAX_IMAGE_MB * 1024 * 1024) {
      toastError(`Image exceeds the ${MAX_IMAGE_MB} MB limit.`);
      input.value = "";
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      attachedImage = reader.result as string; // data:image/...;base64,...
      attachedName = file.name;
    };
    reader.readAsDataURL(file);
    input.value = "";
  }

  function clearImage() {
    attachedImage = null;
    attachedName = "";
  }

  // ── endpoint ────────────────────────────────────────────────────────────────
  let endpoint = $state<Endpoint | null>(null);
  let noEndpoint = $state(false); // 404 — not created yet
  let loadingEndpoint = $state(true);
  let endpointErr = $state(false);

  // ── key + conversation ───────────────────────────────────────────────────────
  let apiKey = $state("");
  let prefilled = $state(false); // true when key came from the in-memory vault
  let draft = $state("");
  let messages = $state<ChatMsg[]>([]);
  let sending = $state(false);

  const slug = $derived(endpoint?.slug ?? "");
  const keyLooksValid = $derived(apiKey.trim().startsWith("brn_"));
  const canSend = $derived(
    !!endpoint && !sending && keyLooksValid && draft.trim().length > 0,
  );

  // ── load per-project ──────────────────────────────────────────────────────────
  let loadedId = $state<string | null>(null);
  $effect(() => {
    if (project.id === loadedId) return;
    loadedId = project.id;
    endpoint = null;
    messages = [];
    draft = "";
    // Prefill a key remembered from this tab's Endpoint flow, if any.
    const remembered = getRememberedKey(project.id);
    apiKey = remembered ?? "";
    prefilled = !!remembered;
    void loadEndpoint();
  });

  async function loadEndpoint() {
    loadingEndpoint = true;
    endpointErr = false;
    noEndpoint = false;
    try {
      endpoint = await api.getEndpoint(project.id);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        noEndpoint = true;
      } else {
        endpointErr = true;
        if (e instanceof ApiError) toastError(e.message, e.correlationId);
        else toastError("Could not load the endpoint.");
      }
    } finally {
      loadingEndpoint = false;
    }
  }

  async function send() {
    if (!canSend || !endpoint) return;
    const text = draft.trim();
    const key = apiKey.trim();
    const image = attachedImage;

    // Build the wire payload from the conversation so far + this turn. We send
    // only role/content (what an OpenAI client would), not our UI annotations.
    // Earlier image turns are sent as their text only — resending every data
    // URL each turn would bloat requests; the current turn carries its image.
    messages = [...messages, { role: "user", content: text, imageUrl: image ?? undefined }];
    draft = "";
    clearImage();
    sending = true;
    const wire: WireChatMessage[] = messages.map((m, i) => {
      if (m.imageUrl && i === messages.length - 1) {
        const parts: ChatContentPart[] = [
          { type: "image_url", image_url: { url: m.imageUrl } },
          { type: "text", text: m.content },
        ];
        return { role: m.role, content: parts };
      }
      return { role: m.role, content: m.content };
    });

    try {
      const resp: ChatCompletion = await api.chat(slug, key, wire);
      const reply = resp.choices?.[0]?.message?.content ?? "";
      messages = [
        ...messages,
        {
          role: "assistant",
          content: reply,
          citations: resp.citations,
          usage: resp.usage,
        },
      ];
    } catch (e) {
      // Roll the failed user turn back out so they can retry/edit it.
      messages = messages.slice(0, -1);
      draft = text;
      if (image) {
        attachedImage = image;
        attachedName = attachedName || "image";
      }
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else toastError("The chat request failed.");
    } finally {
      sending = false;
    }
  }

  function onKeydown(e: KeyboardEvent) {
    // Enter sends; Shift+Enter inserts a newline.
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  }

  function clearChat() {
    messages = [];
  }

  function citationLabel(c: Citation, i: number): string {
    const n = c.index ?? i + 1;
    return c.source ? `[${n}] ${c.source}` : `[${n}]`;
  }

  onDestroy(() => {
    // Never leave the secret lingering in this component's state.
    apiKey = "";
  });
</script>

<!-- ── Header / framing ─────────────────────────────────────────────────────── -->
<div class="card">
  <h2 style="margin: 0 0 4px; font-size: 16px;">Test playground</h2>
  <p class="muted" style="margin: 0;">
    Same endpoint your app would call —
    <code class="mono">POST {location.origin}/v1/chat/completions</code>
    with model <span class="mono">{slug || project.id}</span> and a
    <span class="mono">brn_</span> key. The console login does not authenticate here.
  </p>
</div>

{#if loadingEndpoint}
  <div class="card">
    <span class="row" style="gap: 8px;"><span class="spinner"></span><small>Loading endpoint…</small></span>
  </div>
{:else if noEndpoint}
  <div class="card">
    <div class="empty">
      <p>No endpoint yet.</p>
      <small class="muted">
        Create one from the <strong>Setup</strong> tab once your
        {project.type === "rag" ? "documents are indexed" : "fine-tune passes the eval gate"},
        then come back here to test it.
      </small>
    </div>
  </div>
{:else if endpointErr}
  <div class="card">
    <div class="empty">
      <p>Could not load the endpoint.</p>
      <button class="ghost sm" onclick={() => loadEndpoint()}>Retry</button>
    </div>
  </div>
{:else if endpoint}
  <!-- ── Key selector ───────────────────────────────────────────────────────── -->
  <div class="card">
    <div class="field" style="margin-bottom: 6px;">
      <label for="pg-key">API key (<span class="mono">brn_…</span>)</label>
      <input
        id="pg-key"
        type="password"
        autocomplete="off"
        placeholder="brn_…"
        bind:value={apiKey}
        oninput={() => (prefilled = false)}
        disabled={sending}
      />
      {#if prefilled}
        <small class="muted">Prefilled with the key you just generated (held in memory only — never stored).</small>
      {:else if apiKey && !keyLooksValid}
        <small style="color: var(--amber);">A scoped key starts with <span class="mono">brn_</span>. Generate one in the <strong>Endpoint &amp; keys</strong> tab.</small>
      {:else}
        <small class="muted">Paste a key, or generate one in the <strong>Endpoint &amp; keys</strong> tab. The JWT you logged in with won't work here.</small>
      {/if}
    </div>
  </div>

  <!-- ── Conversation ───────────────────────────────────────────────────────── -->
  <div class="card">
    <div class="row between" style="margin-bottom: 10px;">
      <h2 style="margin: 0; font-size: 16px;">Chat</h2>
      {#if messages.length > 0}
        <button class="ghost sm" onclick={clearChat} disabled={sending}>Clear</button>
      {/if}
    </div>

    {#if messages.length === 0}
      <div class="empty">
        {#if project.type === "rag"}
          Ask a question — answers are grounded in your indexed documents, with citations.
        {:else}
          Send a message to test how your fine-tuned model responds.
        {/if}
      </div>
    {:else}
      <div class="stack" style="gap: 14px;">
        {#each messages as m, i (i)}
          <div class="msg {m.role}">
            <div class="msg-role mono">{m.role === "user" ? "you" : "assistant"}</div>
            {#if m.imageUrl}
              <img class="msg-img" src={m.imageUrl} alt="attached" />
            {/if}
            <div class="msg-body">{m.content}</div>

            {#if m.role === "assistant" && m.citations && m.citations.length > 0}
              <div class="msg-meta">
                <div class="muted" style="font-size: 12px; margin-bottom: 4px;">Citations</div>
                <div class="stack" style="gap: 6px;">
                  {#each m.citations as c, ci (ci)}
                    <div class="muted-box" style="padding: 8px 10px;">
                      <span class="mono" style="font-size: 12px;">{citationLabel(c, ci)}</span>
                      {#if c.text}
                        <div class="muted" style="font-size: 12px; margin-top: 4px;">{c.text}</div>
                      {/if}
                    </div>
                  {/each}
                </div>
              </div>
            {/if}

            {#if m.role === "assistant" && m.usage}
              <div class="msg-meta">
                <span class="badge blue">prompt {m.usage.prompt_tokens}</span>
                <span class="badge blue">completion {m.usage.completion_tokens}</span>
                <span class="badge blue">total {m.usage.total_tokens}</span>
              </div>
            {/if}
          </div>
        {/each}

        {#if sending}
          <div class="msg assistant">
            <div class="msg-role mono">assistant</div>
            <div class="msg-body row" style="gap: 8px; color: var(--muted);">
              <span class="spinner"></span> thinking…
            </div>
          </div>
        {/if}
      </div>
    {/if}

    <!-- ── Composer ─────────────────────────────────────────────────────────── -->
    {#if isVision}
      <div class="row" style="gap: 8px; margin: 14px 0 0; align-items: center;">
        <input
          bind:this={imgInput}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          onchange={onImagePicked}
          style="display: none;"
          id="pg-image"
        />
        <button class="ghost sm" onclick={() => imgInput?.click()} disabled={sending || !keyLooksValid}>
          Attach image
        </button>
        {#if attachedImage}
          <img class="attach-thumb" src={attachedImage} alt="to send" />
          <span class="mono" style="font-size: 12px;">{attachedName}</span>
          <button class="danger ghost sm" onclick={clearImage} disabled={sending}>Remove</button>
        {:else}
          <small class="muted">PNG, JPEG or WebP, ≤ {MAX_IMAGE_MB} MB — sent inline with your next message.</small>
        {/if}
      </div>
    {/if}
    <div class="field" style="margin: {isVision ? '8px' : '14px'} 0 0;">
      <label for="pg-input">Message</label>
      <textarea
        id="pg-input"
        rows="3"
        placeholder={keyLooksValid ? "Type a message — Enter to send, Shift+Enter for a new line" : "Add a brn_ key above to start"}
        bind:value={draft}
        onkeydown={onKeydown}
        disabled={sending || !keyLooksValid}
      ></textarea>
    </div>
    <div class="row between">
      <small class="muted">
        {#if isVision}
          Vision endpoint — attach an image and ask about it.
        {:else if project.type === "rag"}
          Retrieval-augmented — cited from your documents.
        {:else}
          Served by your fine-tuned model.
        {/if}
      </small>
      <button class="primary" onclick={send} disabled={!canSend}>
        {#if sending}<span class="spinner"></span>{/if}
        Send
      </button>
    </div>
  </div>
{/if}

<style>
  .msg {
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 12px;
    background: var(--panel-2);
  }
  .msg.user {
    border-color: var(--accent);
    background: var(--accent-weak);
  }
  .msg-role {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    margin-bottom: 4px;
  }
  .msg-body {
    white-space: pre-wrap;
    word-break: break-word;
    line-height: 1.5;
  }
  .msg-meta {
    margin-top: 10px;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  textarea {
    width: 100%;
    resize: vertical;
    font: inherit;
  }
  .msg-img {
    max-width: 220px;
    max-height: 160px;
    border-radius: 6px;
    border: 1px solid var(--border);
    margin-bottom: 6px;
    display: block;
  }
  .attach-thumb {
    width: 36px;
    height: 36px;
    object-fit: cover;
    border-radius: 4px;
    border: 1px solid var(--border);
  }
</style>
