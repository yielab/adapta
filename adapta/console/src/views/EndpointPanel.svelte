<script lang="ts">
  // Endpoint & API keys + the consumption snippet — the north-star handoff.
  // A customer gets: the endpoint slug (the OpenAI `model` value), a scoped
  // adp_ key (shown exactly once), and copy-paste OpenAI-SDK / curl snippets
  // pointed at this server. (TODO §5.7)
  import { onDestroy } from "svelte";
  import { api, ApiError } from "../lib/api";
  import { toastError, toastSuccess } from "../lib/toast";
  import { rememberKey } from "../lib/keyvault";
  import type { Project, Endpoint, Adapter, AdapterEvent, ApiKey, ApiKeyCreated, GoldenResults } from "../lib/types";
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

  // ── adapters + audit trail (fine-tune endpoints, E4.5) ─────────────────────
  let adapters = $state<Adapter[]>([]);
  let history = $state<AdapterEvent[]>([]);
  let promoteTarget = $state<Adapter | null>(null);
  let promoting = $state(false);
  const passedAdapters = $derived(adapters.filter((a) => a.status === "passed"));
  // The newest history row is what the endpoint serves; a rollback restores an earlier one.
  const previousAdapterId = $derived(
    history.slice(1).find((e) => e.adapter_id && e.adapter_id !== endpoint?.adapter?.id)?.adapter_id ?? null,
  );

  // ── RAG gate: golden set + recall@5 runs (E5.2) ────────────────────────────
  let golden = $state<GoldenResults | null>(null);
  let goldenBusy = $state(false);
  let goldenPoll: ReturnType<typeof setInterval> | null = null;
  const quality = $derived(endpoint?.retrieval?.quality ?? null);
  const latestRun = $derived(golden?.runs[0] ?? null);
  const runInFlight = $derived(latestRun?.status === "queued" || latestRun?.status === "running");

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

  // The active adp_ secret to embed in the snippet: prefer a just-created key
  // (the only time we ever hold the full secret); otherwise a clear placeholder.
  const KEY_PLACEHOLDER = "adp_YOUR_API_KEY";
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
    adapters = [];
    history = [];
    golden = null;
    stopGoldenPoll();
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
      if (endpoint.project_type === "finetune") void loadAdapterState();
      void loadGolden();
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

  function stopGoldenPoll() {
    if (goldenPoll) clearInterval(goldenPoll);
    goldenPoll = null;
  }

  async function loadGolden() {
    try {
      golden = await api.goldenResults(project.id);
    } catch {
      return; // the tile is optional; the rest of the panel works without it
    }
    if (runInFlight && !goldenPoll) {
      goldenPoll = setInterval(async () => {
        try {
          golden = await api.goldenResults(project.id);
        } catch {
          return;
        }
        if (!runInFlight) {
          stopGoldenPoll();
          try {
            endpoint = await api.getEndpoint(project.id); // refresh the tile
          } catch {
            /* keep the previous tile */
          }
        }
      }, 3000);
    }
  }

  async function onGoldenFile(e: Event) {
    const input = e.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    input.value = "";
    if (!file || goldenBusy) return;
    goldenBusy = true;
    try {
      const set = await api.uploadGolden(project.id, file);
      toastSuccess(`Golden set stored: ${set.num_questions} questions.`);
      await loadGolden();
    } catch (err) {
      if (err instanceof ApiError) toastError(err.message, err.correlationId);
      else toastError("Could not store the golden set.");
    } finally {
      goldenBusy = false;
    }
  }

  async function runGolden() {
    if (goldenBusy) return;
    goldenBusy = true;
    try {
      await api.runGolden(project.id);
      toastSuccess("Retrieval check queued.");
      await loadGolden();
    } catch (err) {
      if (err instanceof ApiError) toastError(err.message, err.correlationId);
      else toastError("Could not start the retrieval check.");
    } finally {
      goldenBusy = false;
    }
  }

  const pct = (x: number) => `${(x * 100).toFixed(0)}%`;
  const signedPts = (d: number) => `${d >= 0 ? "+" : "−"}${Math.abs(d * 100).toFixed(0)} pts`;

  async function loadAdapterState() {
    try {
      [adapters, history] = await Promise.all([api.listAdapters(project.id), api.endpointHistory(project.id)]);
    } catch (e) {
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else toastError("Could not load the adapters.");
    }
  }

  async function doPromote() {
    if (!promoteTarget || promoting) return;
    promoting = true;
    try {
      endpoint = await api.promoteAdapter(project.id, promoteTarget.id);
      toastSuccess(`Now serving "${promoteTarget.name}". The next request uses it; no restart needed.`);
      promoteTarget = null;
      await loadAdapterState();
    } catch (e) {
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else toastError("Could not switch the adapter.");
    } finally {
      promoting = false;
    }
  }

  // "adapter vs base" on the task metric, e.g. "0.92 vs 0.40 (+0.52)".
  function scoreLine(m: Adapter["eval_metrics"]): string {
    if (!m || m.adapter_score === undefined || m.base_score === undefined) return "—";
    const d = m.adapter_score - m.base_score;
    return `${m.adapter_score.toFixed(2)} vs ${m.base_score.toFixed(2)} (${d >= 0 ? "+" : ""}${d.toFixed(2)})`;
  }

  let exporting = $state(false);
  async function exportOllama() {
    if (exporting) return;
    exporting = true;
    try {
      const { blob, filename } = await api.exportOllama(project.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else toastError("Could not export the adapter.");
    } finally {
      exporting = false;
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
    stopGoldenPoll();
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
        {project.type === "rag" ? "documents are indexed" : "an adapter is imported"}.
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
        <span class="comp-adapter">LoRA adapter: {endpoint.adapter.name} ({endpoint.adapter.status})</span>
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
      </tbody>
    </table>
  {/if}
</div>

<!-- ── Retrieval quality (RAG gate, E5.2) ─────────────────────────────────── -->
{#if endpoint}
  <div class="card">
    <div class="row between" style="margin-bottom: 4px;">
      <h2 style="margin: 0; font-size: 16px;">Retrieval quality</h2>
      <span class="row" style="gap: 8px;">
        <label class="ghost sm file-btn">
          {golden?.golden_set ? "Replace golden set" : "Upload golden set"}
          <input type="file" accept=".jsonl" onchange={onGoldenFile} disabled={goldenBusy} hidden />
        </label>
        {#if golden?.golden_set}
          <button class="primary sm" onclick={runGolden} disabled={goldenBusy || runInFlight}>
            {runInFlight ? "Running…" : "Run now"}
          </button>
        {/if}
      </span>
    </div>
    <small class="muted">
      A golden set is a list of questions with the document that answers each (one JSON line:
      <span class="mono">&#123;"q", "expected_file"&#125;</span>). The check retrieves every question the way the
      endpoint does and reports how often the right document is in the top 5. It re-runs after each document is
      indexed, and warns if quality drops; it never blocks serving.
    </small>
    {#if !golden?.golden_set}
      <p class="muted">No golden set yet.</p>
    {:else if quality}
      <div class="quality">
        <div class="tile">
          <div class="tile-v">{pct(quality.recall_at_5)}</div>
          <div class="muted">recall@5 · {quality.n_questions} questions</div>
        </div>
        <div class="tile">
          <div class="tile-v">{quality.mrr.toFixed(2)}</div>
          <div class="muted">MRR</div>
        </div>
        <div class="tile">
          <div class="tile-v">
            {#if quality.delta !== null}{signedPts(quality.delta)}{:else}—{/if}
          </div>
          <div class="muted">vs previous runs · {fmtDate(quality.run_at)}</div>
        </div>
        {#if quality.regression}
          <span class="chip-warn" title="Recall fell by more than one question and 5 points against the median of the last runs.">
            Retrieval got worse
          </span>
        {/if}
      </div>
    {:else if latestRun?.status === "failed"}
      <p class="muted">The last check failed: {latestRun.error}</p>
    {:else}
      <p class="muted">{runInFlight ? "First check running…" : "Run the check to see recall@5."}</p>
    {/if}
    {#if golden?.golden_set && golden.runs.some((r) => r.status === "succeeded")}
      <h3 style="margin: 14px 0 4px; font-size: 14px;">Runs</h3>
      <table>
        <thead><tr><th>When</th><th>Trigger</th><th>recall@5</th><th>MRR</th><th>vs previous</th></tr></thead>
        <tbody>
          {#each golden.runs.filter((r) => r.status === "succeeded") as r (r.id)}
            <tr>
              <td>{fmtDate(r.finished_at ?? r.created_at)}</td>
              <td>{r.trigger === "index" ? "after indexing" : "manual"}</td>
              <td class="mono">{r.recall_at_5 !== null ? pct(r.recall_at_5) : "—"}</td>
              <td class="mono">{r.mrr !== null ? r.mrr.toFixed(2) : "—"}</td>
              <td class="mono">
                {r.delta !== null ? signedPts(r.delta) : "—"}
                {#if r.regression}<span class="chip-warn">worse</span>{/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>
{/if}

<!-- ── Adapters (fine-tune endpoints): promote / roll back, with the audit trail ── -->
{#if endpoint && endpoint.project_type === "finetune"}
  <div class="card">
    <h2 style="margin: 0 0 6px; font-size: 16px;">Adapters</h2>
    <small class="muted">
      Only adapters that passed the eval gate can be served. Switching takes effect on the next request;
      no restart.
    </small>
    {#if passedAdapters.length === 0}
      <p class="muted">No passed adapters.</p>
    {:else}
      <table>
        <thead>
          <tr><th>Adapter</th><th>Task score vs base</th><th>Imported</th><th></th></tr>
        </thead>
        <tbody>
          {#each passedAdapters as a (a.id)}
            <tr>
              <td>
                {a.name}
                {#if a.id === endpoint.adapter?.id}<span class="badge-current">current</span>{/if}
              </td>
              <td class="mono">{scoreLine(a.eval_metrics)}</td>
              <td>{fmtDate(a.created_at)}</td>
              <td>
                {#if a.id !== endpoint.adapter?.id}
                  <button class="ghost sm" onclick={() => (promoteTarget = a)}>
                    {a.id === previousAdapterId ? "Roll back" : "Promote"}
                  </button>
                {:else}
                  <button class="ghost sm" onclick={exportOllama} disabled={exporting}>
                    {exporting ? "Exporting…" : "Export for Ollama"}
                  </button>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}

    {#if history.length > 0}
      <h3 style="margin: 14px 0 4px; font-size: 14px;">History</h3>
      <table>
        <thead>
          <tr><th>When</th><th>Action</th><th>Adapter</th><th>Score vs base</th><th>By</th></tr>
        </thead>
        <tbody>
          {#each history as e (e.id)}
            <tr>
              <td>{fmtDate(e.created_at)}</td>
              <td>{e.action}</td>
              <td>{e.adapter_name ?? "(deleted)"}</td>
              <td class="mono">{scoreLine(e.eval_metrics)}</td>
              <td>{e.actor_email ?? "—"}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>
{/if}

<!-- ── API keys ───────────────────────────────────────────────────────────── -->
{#if endpoint}
  <div class="card">
    <div class="row between" style="margin-bottom: 4px;">
      <h2 style="margin: 0; font-size: 16px;">API keys</h2>
      <button class="primary sm" onclick={openCreate}>Generate key</button>
    </div>
    <p class="muted" style="margin: 0 0 14px;">
      Scoped <span class="mono">adp_</span> keys authenticate calls to this endpoint. The full secret is shown only once.
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
      <span class="mono">{slug}</span> as the model, and authenticate with a <span class="mono">adp_</span> key.
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
  .badge-current { margin-left: 6px; padding: 1px 6px; border-radius: 8px; font-size: 11px; background: var(--accent-soft, rgba(80, 160, 120, 0.18)); color: var(--text); }
  .comp-retrieval { color: var(--text); }
  .quality { display: flex; flex-wrap: wrap; align-items: center; gap: 24px; margin-top: 12px; }
  .tile-v { font-family: var(--display); font-size: 26px; }
  .chip-warn { margin-left: 6px; padding: 2px 8px; border-radius: 8px; font-size: 12px; background: var(--amber-weak); color: var(--amber); border: 1px solid var(--amber); }
  .file-btn { cursor: pointer; }
</style>

{#if promoteTarget}
  <ConfirmDialog
    title={promoteTarget.id === previousAdapterId ? "Roll back to this adapter?" : "Serve this adapter?"}
    message={`"${promoteTarget.name}" will answer every request to this endpoint from now on, replacing "${endpoint?.adapter?.name ?? "the current adapter"}". The change is logged.`}
    confirmLabel={promoteTarget.id === previousAdapterId ? "Roll back" : "Promote"}
    busy={promoting}
    onconfirm={doPromote}
    oncancel={() => !promoting && (promoteTarget = null)}
  />
{/if}
