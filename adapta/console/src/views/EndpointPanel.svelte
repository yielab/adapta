<script lang="ts">
  // Endpoint & API keys + the consumption snippet — the north-star handoff.
  // A customer gets: the endpoint slug (the OpenAI `model` value), a scoped
  // brn_ key (shown exactly once), and copy-paste OpenAI-SDK / curl snippets
  // pointed at this server. (TODO §5.7)
  import { onDestroy } from "svelte";
  import { api, ApiError } from "../lib/api";
  import { toastError, toastSuccess } from "../lib/toast";
  import { rememberKey } from "../lib/keyvault";
  import type { Project, Endpoint, ApiKey, ApiKeyCreated } from "../lib/types";
  import StatusBadge from "../components/StatusBadge.svelte";
  import Modal from "../components/Modal.svelte";
  import ConfirmDialog from "../components/ConfirmDialog.svelte";
  import CodeSnippet from "../components/CodeSnippet.svelte";

  let { project }: { project: Project } = $props();

  // ── endpoint ──────────────────────────────────────────────────────────────
  let endpoint = $state<Endpoint | null>(null);
  let noEndpoint = $state(false); // 404 — not created yet
  let loadingEndpoint = $state(true);
  let endpointErr = $state(false);

  // ── keys ──────────────────────────────────────────────────────────────────
  let keys = $state<ApiKey[]>([]);
  let loadingKeys = $state(true);
  let keysErr = $state(false);

  // ── generate-key flow ───────────────────────────────────────────────────────
  let showCreateModal = $state(false);
  let newKeyName = $state("");
  let creatingKey = $state(false);
  let createdKey = $state<ApiKeyCreated | null>(null); // full secret, shown once
  let secretCopied = $state(false);

  // ── revoke flow ─────────────────────────────────────────────────────────────
  let revokeTarget = $state<ApiKey | null>(null);
  let revoking = $state(false);

  // ── copy slug ────────────────────────────────────────────────────────────────
  let slugCopied = $state(false);

  // The base_url a customer plugs into the OpenAI SDK. Same server, /v1.
  const serverBaseUrl = `${location.origin}/v1`;

  // The active brn_ secret to embed in the snippet: prefer a just-created key
  // (the only time we ever hold the full secret); otherwise a clear placeholder.
  const KEY_PLACEHOLDER = "brn_YOUR_API_KEY";
  const snippetKey = $derived(createdKey?.key ?? KEY_PLACEHOLDER);
  const slug = $derived(endpoint?.slug ?? "");

  const pythonSnippet = $derived(
    `from openai import OpenAI\n\n` +
      `client = OpenAI(\n` +
      `    base_url="${serverBaseUrl}",\n` +
      `    api_key="${snippetKey}",\n` +
      `)\n\n` +
      `resp = client.chat.completions.create(\n` +
      `    model="${slug}",\n` +
      `    messages=[{"role": "user", "content": "Hello!"}],\n` +
      `)\n` +
      `print(resp.choices[0].message.content)\n`,
  );

  const curlSnippet = $derived(
    `curl ${serverBaseUrl}/chat/completions \\\n` +
      `  -H "Authorization: Bearer ${snippetKey}" \\\n` +
      `  -H "Content-Type: application/json" \\\n` +
      `  -d '{\n` +
      `    "model": "${slug}",\n` +
      `    "messages": [{"role": "user", "content": "Hello!"}]\n` +
      `  }'\n`,
  );

  // ── loading ───────────────────────────────────────────────────────────────
  let loadedId = $state<string | null>(null);
  $effect(() => {
    if (project.id === loadedId) return;
    loadedId = project.id;
    endpoint = null;
    keys = [];
    createdKey = null;
    void loadEndpoint();
    void loadKeys();
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

  async function loadKeys() {
    loadingKeys = true;
    keysErr = false;
    try {
      keys = await api.listKeys(project.id);
    } catch (e) {
      keysErr = true;
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else toastError("Could not load API keys.");
    } finally {
      loadingKeys = false;
    }
  }

  // ── copy helpers ────────────────────────────────────────────────────────────
  async function copyText(text: string, mark: (v: boolean) => void) {
    try {
      await navigator.clipboard.writeText(text);
      mark(true);
      setTimeout(() => mark(false), 1500);
    } catch {
      // Clipboard unavailable (insecure context) — the value stays selectable.
    }
  }

  // ── generate key ─────────────────────────────────────────────────────────────
  function openCreate() {
    newKeyName = "";
    showCreateModal = true;
  }

  async function doCreate() {
    const name = newKeyName.trim();
    if (!name || creatingKey) return;
    creatingKey = true;
    try {
      const created = await api.createKey(project.id, name);
      showCreateModal = false;
      createdKey = created; // surfaces the show-once secret modal
      secretCopied = false;
      // Hold it in memory for this tab so the Playground can prefill it.
      rememberKey(project.id, created.name, created.key);
      toastSuccess("API key created.");
      await loadKeys();
    } catch (e) {
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else toastError("Could not create the API key.");
    } finally {
      creatingKey = false;
    }
  }

  function dismissSecret() {
    createdKey = null;
    secretCopied = false;
  }

  // ── revoke key ───────────────────────────────────────────────────────────────
  async function doRevoke() {
    if (!revokeTarget || revoking) return;
    revoking = true;
    try {
      await api.revokeKey(project.id, revokeTarget.id);
      toastSuccess("API key revoked.");
      revokeTarget = null;
      await loadKeys();
    } catch (e) {
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else toastError("Could not revoke the API key.");
    } finally {
      revoking = false;
    }
  }

  function fmtDate(iso: string): string {
    try {
      return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
    } catch {
      return iso;
    }
  }

  onDestroy(() => {
    // Drop the in-memory secret as soon as the panel goes away.
    createdKey = null;
  });
</script>

<!-- ── Endpoint card ──────────────────────────────────────────────────────── -->
<div class="card">
  <h2 style="margin: 0 0 6px; font-size: 16px;">Endpoint</h2>
  {#if loadingEndpoint}
    <span class="row" style="gap: 8px;"><span class="spinner"></span><small>Loading endpoint…</small></span>
  {:else if noEndpoint}
    <div class="empty">
      <p>No endpoint yet.</p>
      <small class="muted">
        Create one from the <strong>Setup</strong> tab once your
        {project.type === "rag" ? "documents are indexed" : "fine-tune passes the eval gate"}.
      </small>
    </div>
  {:else if endpointErr}
    <div class="empty">
      <p>Could not load the endpoint.</p>
      <button class="ghost sm" onclick={() => loadEndpoint()}>Retry</button>
    </div>
  {:else if endpoint}
    <!-- Composition explainer -->
    <div class="composition">
      <span class="comp-base mono">{endpoint.base_model}</span>
      {#if endpoint.adapter}
        <span class="comp-sep">+</span>
        <span class="comp-adapter">
          fine-tuned adapter
          <span class="comp-score">eval {endpoint.adapter.eval_score.toFixed(3)}</span>
          {#if endpoint.adapter.score_delta != null}
            <span class="comp-delta {endpoint.adapter.gate === 'improvement' ? 'green' : ''}">
              +{endpoint.adapter.score_delta.toFixed(3)} vs base · passed via {endpoint.adapter.gate}
            </span>
          {/if}
        </span>
      {/if}
      {#if endpoint.retrieval}
        <span class="comp-sep">+</span>
        <span class="comp-retrieval">retrieval over {endpoint.retrieval.indexed_chunks.toLocaleString()} chunks</span>
      {/if}
    </div>
    <table>
      <tbody>
        <tr>
          <th style="width: 140px;">Model (slug)</th>
          <td>
            <span class="row" style="gap: 8px;">
              <span class="mono">{endpoint.slug}</span>
              <button class="ghost sm" onclick={() => copyText(endpoint!.slug, (v) => (slugCopied = v))}>
                {slugCopied ? "copied" : "copy"}
              </button>
            </span>
            <small class="muted">Pass this as the <span class="mono">model</span> in your requests.</small>
          </td>
        </tr>
        <tr>
          <th>Status</th>
          <td><StatusBadge status={endpoint.status} /></td>
        </tr>
        <tr>
          <th>Type</th>
          <td>{endpoint.project_type === "rag" ? "Knowledge (RAG)" : "Fine-tuned (LoRA)"}</td>
        </tr>
        <tr>
          <th>Base model</th>
          <td class="mono">{endpoint.base_model}</td>
        </tr>
        <tr>
          <th>Created</th>
          <td>{fmtDate(endpoint.created_at)}</td>
        </tr>
        {#if endpoint.adapter}
          <tr>
            <th>Adapter job</th>
            <td class="mono" style="font-size: 12px;">{endpoint.adapter.job_id}</td>
          </tr>
        {/if}
      </tbody>
    </table>
  {/if}
</div>

<!-- ── API keys ───────────────────────────────────────────────────────────── -->
{#if endpoint}
  <div class="card">
    <div class="row between" style="margin-bottom: 4px;">
      <h2 style="margin: 0; font-size: 16px;">API keys</h2>
      <button class="primary sm" onclick={openCreate}>Generate key</button>
    </div>
    <p class="muted" style="margin: 0 0 14px;">
      Scoped <span class="mono">brn_</span> keys authenticate calls to this endpoint. The full secret is shown only once.
    </p>

    {#if loadingKeys}
      <span class="row" style="gap: 8px;"><span class="spinner"></span><small>Loading keys…</small></span>
    {:else if keysErr}
      <div class="empty">
        <p>Could not load API keys.</p>
        <button class="ghost sm" onclick={() => loadKeys()}>Retry</button>
      </div>
    {:else if keys.length === 0}
      <div class="empty">No keys yet. Generate one to call your endpoint.</div>
    {:else}
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Key</th>
            <th>Status</th>
            <th>Created</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {#each keys as k (k.id)}
            <tr>
              <td>{k.name}</td>
              <td class="mono">{k.prefix}…</td>
              <td><StatusBadge status={k.is_active ? "active" : "revoked"} /></td>
              <td class="mono">{fmtDate(k.created_at)}</td>
              <td style="text-align: right;">
                {#if k.is_active}
                  <button class="danger ghost sm" onclick={() => (revokeTarget = k)}>Revoke</button>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>

  <!-- ── Consumption snippet — the north-star handoff ──────────────────────── -->
  <div class="card">
    <h2 style="margin: 0 0 6px; font-size: 16px;">Use your endpoint</h2>
    <p class="muted" style="margin: 0 0 14px;">
      OpenAI-compatible. Point any OpenAI client at <span class="mono">{serverBaseUrl}</span>, use
      <span class="mono">{slug}</span> as the model, and authenticate with a <span class="mono">brn_</span> key.
      {#if !createdKey}
        Replace <span class="mono">{KEY_PLACEHOLDER}</span> with a key you generate above.
      {:else}
        <span style="color: var(--green);">Your new key is embedded below — copy these now while the secret is visible.</span>
      {/if}
    </p>
    <div class="stack" style="gap: 16px;">
      <CodeSnippet title="OpenAI Python SDK" code={pythonSnippet} />
      <CodeSnippet title="curl" code={curlSnippet} />
    </div>
  </div>
{/if}

<!-- ── Generate-key modal (name input) ──────────────────────────────────────── -->
{#if showCreateModal}
  <Modal title="Generate API key" onclose={() => !creatingKey && (showCreateModal = false)}>
    <div class="field">
      <label for="key-name">Key name</label>
      <input
        id="key-name"
        type="text"
        placeholder="e.g. production-backend"
        bind:value={newKeyName}
        disabled={creatingKey}
        onkeydown={(e) => e.key === "Enter" && doCreate()}
      />
      <small class="muted">A label to recognise this key later — it isn't part of the secret.</small>
    </div>
    <div class="row between" style="margin-top: 18px;">
      <button class="ghost" onclick={() => (showCreateModal = false)} disabled={creatingKey}>Cancel</button>
      <button class="primary" onclick={doCreate} disabled={creatingKey || !newKeyName.trim()}>
        {#if creatingKey}<span class="spinner"></span>{/if}
        Generate
      </button>
    </div>
  </Modal>
{/if}

<!-- ── Show-once secret modal ───────────────────────────────────────────────── -->
{#if createdKey}
  <Modal title="Copy your API key" onclose={dismissSecret}>
    <p class="muted" style="margin: 0 0 12px;">
      Copy it now — <strong style="color: var(--amber);">it won't be shown again.</strong> Store it somewhere safe.
    </p>
    <div class="muted-box mono" style="word-break: break-all; margin-bottom: 12px;">{createdKey.key}</div>
    <div class="row between">
      <button class="primary" onclick={() => copyText(createdKey!.key, (v) => (secretCopied = v))}>
        {secretCopied ? "Copied" : "Copy key"}
      </button>
      <button class="ghost" onclick={dismissSecret}>Done</button>
    </div>
  </Modal>
{/if}

<!-- ── Revoke confirm ───────────────────────────────────────────────────────── -->
{#if revokeTarget}
  <ConfirmDialog
    title="Revoke this key?"
    message={`"${revokeTarget.name}" (${revokeTarget.prefix}…) will stop working immediately. Any app using it will be rejected.`}
    confirmLabel="Revoke key"
    busy={revoking}
    onconfirm={doRevoke}
    oncancel={() => !revoking && (revokeTarget = null)}
  />
{/if}

<style>
  .composition {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 6px;
    padding: 8px 12px;
    background: var(--panel-2);
    border-radius: 6px;
    border: 1px solid var(--border);
    margin-bottom: 14px;
    font-size: 13px;
  }
  .comp-sep { color: var(--muted); font-weight: 600; }
  .comp-base { font-weight: 600; }
  .comp-adapter { color: var(--text); }
  .comp-score {
    display: inline-block;
    background: var(--brand-weak);
    color: var(--brand);
    border-radius: 4px;
    padding: 1px 6px;
    font-size: 11px;
    font-weight: 700;
    margin-left: 4px;
  }
  .comp-delta {
    font-size: 11px;
    color: var(--muted);
    margin-left: 4px;
  }
  .comp-delta.green { color: var(--green); }
  .comp-retrieval { color: var(--text); }
</style>
