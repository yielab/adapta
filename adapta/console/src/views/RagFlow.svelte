<script lang="ts">
  // Knowledge (RAG) setup flow — upload documents → index → create endpoint.
  // The model's weights never change; answers are grounded in these documents
  // with citations. (TODO §5.5)
  import { onDestroy, untrack } from "svelte";
  import { api, ApiError } from "../lib/api";
  import { toastError, toastSuccess } from "../lib/toast";
  import type { Project, ProjectFile } from "../lib/types";
  import StatusBadge from "../components/StatusBadge.svelte";

  let { project }: { project: Project } = $props();

  import { BRAND } from "../lib/brand";
  const DOCS_URL = BRAND.docs;

  let files = $state<ProjectFile[]>([]);
  let loading = $state(true);
  let loadErr = $state(false);

  let uploading = $state(false);
  let dragOver = $state(false);
  let creatingEndpoint = $state(false);
  let endpointDone = $state(false);

  let fileInput: HTMLInputElement | null = null;
  let pollTimer: ReturnType<typeof setTimeout> | null = null;

  // At least one document must finish indexing before we can serve answers.
  const indexedCount = $derived(files.filter((f) => f.status === "indexed").length);
  const canCreateEndpoint = $derived(indexedCount >= 1);
  const anyInFlight = $derived(files.some((f) => f.status === "pending" || f.status === "processing"));

  function clearPoll() {
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  }

  // Keep a single pending timer alive while anything is still indexing.
  $effect(() => {
    if (anyInFlight && !pollTimer) {
      schedulePoll();
    } else if (!anyInFlight) {
      clearPoll();
    }
  });

  function schedulePoll() {
    clearPoll();
    pollTimer = setTimeout(async () => {
      pollTimer = null;
      await refresh(true);
      if (anyInFlight) schedulePoll();
    }, 2000);
  }

  onDestroy(clearPoll);

  async function refresh(silent = false) {
    if (!silent) loading = true;
    try {
      files = await api.listFiles(project.id);
      loadErr = false;
    } catch (e) {
      if (!silent) loadErr = true;
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else if (!silent) toastError("Could not load documents.");
    } finally {
      loading = false;
    }
  }

  // Initial load (re-runs if the project prop changes).
  let loadedId = $state<string | null>(null);
  $effect(() => {
    if (project.id === loadedId) return;
    loadedId = project.id;
    files = [];
    endpointDone = false;
    void refresh();
  });

  async function uploadFiles(list: FileList | File[]) {
    const arr = Array.from(list);
    if (arr.length === 0) return;
    uploading = true;
    try {
      for (const file of arr) {
        await api.uploadFile(project.id, file);
      }
      toastSuccess(
        arr.length === 1
          ? "Document uploaded — indexing started."
          : `${arr.length} documents uploaded — indexing started.`,
      );
      await refresh(true);
    } catch (e) {
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else toastError("Upload failed.");
    } finally {
      uploading = false;
    }
  }

  function onPick(e: Event) {
    const input = e.currentTarget as HTMLInputElement;
    if (input.files && input.files.length) {
      void uploadFiles(input.files);
    }
    input.value = ""; // allow re-picking the same file
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    dragOver = false;
    if (uploading) return;
    if (e.dataTransfer?.files?.length) {
      void uploadFiles(e.dataTransfer.files);
    }
  }

  function onDragOver(e: DragEvent) {
    e.preventDefault();
    dragOver = true;
  }

  function onDragLeave() {
    dragOver = false;
  }

  async function remove(f: ProjectFile) {
    if (!confirm(`Remove "${f.filename}"? Its indexed chunks will be deleted.`)) return;
    try {
      await api.deleteFile(project.id, f.id);
      toastSuccess("Document removed.");
      await refresh(true);
    } catch (e) {
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else toastError("Could not remove the document.");
    }
  }

  // (E5.4) Visual extraction: opt-in via a schema, then a per-file queued job (CPU, ~40 s per page).
  const SECONDS_PER_PAGE = 40;
  const SCHEMA_EXAMPLE = JSON.stringify(
    { title: "Invoice", properties: { vendor: { type: "string" }, date: { type: "string" }, total: { type: "string" } } },
    null,
    2,
  );
  // Seeded once from the project prop; later edits go through saveSchema().
  const initialSchema = untrack(() => project.extraction_schema ? JSON.stringify(project.extraction_schema, null, 2) : "");
  let schemaDraft = $state(initialSchema);
  let savedSchema = $state(initialSchema);
  let savingSchema = $state(false);
  let extracting = $state<string | null>(null);
  const canExtract = $derived(savedSchema !== "");
  const extractable = (f: ProjectFile) => /\.(pdf|png|jpe?g|tiff?)$/i.test(f.filename) && f.status === "indexed";

  async function saveSchema() {
    savingSchema = true;
    try {
      const text = schemaDraft.trim();
      const updated = await api.updateProject(project.id, { extraction_schema: text ? JSON.parse(text) : null });
      savedSchema = schemaDraft = updated.extraction_schema ? JSON.stringify(updated.extraction_schema, null, 2) : "";
      toastSuccess(updated.extraction_schema ? "Extraction schema saved." : "Extraction turned off.");
    } catch (e) {
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else toastError("The schema is not valid JSON.");
    } finally {
      savingSchema = false;
    }
  }

  async function extract(f: ProjectFile, allPages: boolean) {
    extracting = f.id;
    try {
      const r = await api.extractFile(project.id, f.id, allPages);
      toastSuccess(`Reading ${r.pages} page${r.pages === 1 ? "" : "s"} (about ${r.pages * SECONDS_PER_PAGE} s per vision call on CPU).`);
    } catch (e) {
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else toastError("Could not start the extraction.");
    } finally {
      extracting = null;
    }
  }

  async function downloadCsv() {
    try {
      const { blob, filename } = await api.downloadFieldsCsv(project.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else toastError("Could not download the fields.");
    }
  }

  async function createEndpoint() {
    if (!canCreateEndpoint || creatingEndpoint) return;
    creatingEndpoint = true;
    try {
      await api.createEndpoint(project.id);
      endpointDone = true;
      toastSuccess("Endpoint created. Open the “Endpoint & keys” tab to get an API key.");
    } catch (e) {
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else toastError("Could not create the endpoint.");
    } finally {
      creatingEndpoint = false;
    }
  }

  function fmtSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
</script>

<div class="card">
  <div class="row between" style="margin-bottom: 4px;">
    <h2 style="margin: 0; font-size: 16px;">1 · Documents</h2>
    {#if anyInFlight}
      <span class="row" style="gap: 6px;"><span class="spinner"></span><small class="muted">indexing…</small></span>
    {/if}
  </div>
  <p class="muted" style="margin: 0 0 12px;">
    Answers grounded in your documents, with citations — the model's weights don't change.
  </p>

  <!-- Collapsible: what to upload + best practices. Keeps the surface minimal. -->
  <details class="help" style="margin-bottom: 14px;">
    <summary>What to upload &amp; how to get good answers</summary>
    <div class="help-body">
      <h4>What this needs</h4>
      <p style="margin: 0;">
        Just your source material — no examples or labels. Each file is split into
        small chunks and embedded; at query time the closest chunks are retrieved
        and quoted back as citations.
      </p>

      <h4>Accepted files</h4>
      <ul>
        <li><strong>PDF, DOCX, Markdown, TXT, HTML, and images (PNG, JPG, TIFF).</strong>
          Scanned PDFs and images are read with OCR automatically — no pre-processing needed.</li>
        <li>Good fits: manuals, FAQs, policies, wikis, specs, support transcripts.</li>
      </ul>

      <h4>Best practices</h4>
      <ul>
        <li>Prefer several focused documents over one giant dump — retrieval stays sharper.</li>
        <li>Use clear headings and strip boilerplate (nav, repeated headers/footers) — it survives chunking and cuts noise.</li>
        <li>When content changes, remove the old file and re-upload — the index is not auto-refreshed.</li>
        <li>RAG teaches <em>facts</em>, not behavior. To change tone or format, use the
          fine-tuning path instead.</li>
      </ul>
      <p style="margin: 10px 0 0;">
        <a href={DOCS_URL} target="_blank" rel="noopener">Full guide →</a>
      </p>
    </div>
  </details>

  <!-- Drop zone / picker -->
  <div
    class="dropzone"
    class:over={dragOver}
    class:busy={uploading}
    role="button"
    tabindex="0"
    aria-label="Upload documents"
    ondrop={onDrop}
    ondragover={onDragOver}
    ondragleave={onDragLeave}
    onclick={() => !uploading && fileInput?.click()}
    onkeydown={(e) => (e.key === "Enter" || e.key === " ") && !uploading && fileInput?.click()}
  >
    {#if uploading}
      <span class="row" style="gap: 8px; justify-content: center;"><span class="spinner"></span><span>Uploading…</span></span>
    {:else}
      <div>Drag &amp; drop files here, or <span class="link">browse</span></div>
      <small class="muted">PDF, DOCX, Markdown, TXT, HTML or images</small>
    {/if}
    <input
      bind:this={fileInput}
      type="file"
      multiple
      accept=".pdf,.docx,.md,.markdown,.txt,.html,.htm,.png,.jpg,.jpeg,.tif,.tiff"
      style="display: none;"
      onchange={onPick}
    />
  </div>

  <!-- File list -->
  <div style="margin-top: 16px;">
    {#if loading}
      <span class="row" style="gap: 8px;"><span class="spinner"></span><small>Loading documents…</small></span>
    {:else if loadErr}
      <div class="empty">
        <p>Could not load documents.</p>
        <button class="ghost sm" onclick={() => refresh()}>Retry</button>
      </div>
    {:else if files.length === 0}
      <div class="empty">No documents yet. Upload one above to give your model knowledge.</div>
    {:else}
      <table>
        <thead>
          <tr>
            <th>File</th>
            <th>Status</th>
            <th>Size</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {#each files as f (f.id)}
            <tr>
              <td>
                <div class="mono">{f.filename}</div>
                {#if (f.pages_needing_review ?? 0) > 0}
                  <small style="color: var(--amber, var(--red));">
                    {f.pages_needing_review} page{f.pages_needing_review === 1 ? "" : "s"} low-confidence OCR — re-scan, or re-read it with the vision model (Extract fields).
                  </small>
                {/if}
                {#if f.status === "failed"}
                  <small style="color: var(--red);">Indexing failed — try removing and re-uploading.</small>
                {/if}
              </td>
              <td>
                <StatusBadge status={f.status} />
                {#if f.status === "indexed" && f.num_chunks != null}
                  <small
                    class="muted hint"
                    style="margin-left: 8px;"
                    title="A chunk is a short passage the document was split into so it can be searched. Answers quote the passages they used."
                  >{f.num_chunks} chunk{f.num_chunks === 1 ? "" : "s"}</small>
                {/if}
              </td>
              <td class="mono">{fmtSize(f.size_bytes)}</td>
              <td style="text-align: right;">
                {#if canExtract && extractable(f)}
                  <button
                    class="ghost sm"
                    disabled={extracting === f.id}
                    title="Vision model on CPU: about {SECONDS_PER_PAGE} s per page per call. Reads the low-confidence pages."
                    onclick={() => extract(f, (f.pages_needing_review ?? 0) === 0)}
                  >{(f.pages_needing_review ?? 0) > 0 ? `Extract fields (${f.pages_needing_review} p, ~${(f.pages_needing_review ?? 0) * SECONDS_PER_PAGE} s)` : "Extract fields (all pages)"}</button>
                {/if}
                <button class="danger ghost sm" onclick={() => remove(f)}>Remove</button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>

  <!-- (E5.4) Visual extraction schema: off until a schema is saved -->
  <details style="margin-top: 16px;">
    <summary>Visual extraction {canExtract ? "(on)" : "(off)"}</summary>
    <p class="muted" style="margin: 8px 0;">
      Optional. The vision model reads PDF/image pages into structured fields (vendor, date, total…) and
      re-reads low-confidence OCR pages. It runs on CPU, one queued job per file.
    </p>
    <textarea rows="8" class="mono" style="width: 100%;" bind:value={schemaDraft} placeholder={SCHEMA_EXAMPLE}></textarea>
    <div class="row" style="gap: 8px; margin-top: 8px;">
      <button class="sm" onclick={saveSchema} disabled={savingSchema || schemaDraft.trim() === savedSchema}>
        {schemaDraft.trim() === "" ? "Turn off" : "Save schema"}
      </button>
      {#if canExtract}<button class="ghost sm" onclick={downloadCsv}>Download fields (CSV)</button>{/if}
    </div>
  </details>
</div>

<!-- Endpoint creation -->
<div class="card">
  <h2 style="margin: 0 0 6px; font-size: 16px;">2 · Serve answers</h2>
  <p class="muted" style="margin: 0 0 14px;">
    {#if canCreateEndpoint}
      {indexedCount} document{indexedCount === 1 ? "" : "s"} indexed. Create an endpoint to query your knowledge base over an OpenAI-compatible API.
    {:else}
      Index at least one document before creating an endpoint.
    {/if}
  </p>
  <div class="row" style="gap: 12px;">
    <button class="primary" disabled={!canCreateEndpoint || creatingEndpoint} onclick={createEndpoint}>
      {#if creatingEndpoint}
        <span class="row" style="gap: 6px;"><span class="spinner"></span>Creating…</span>
      {:else}
        Create endpoint
      {/if}
    </button>
    {#if endpointDone}
      <small class="muted">Done — open the <strong>Endpoint &amp; keys</strong> tab to generate an API key.</small>
    {/if}
  </div>
</div>

<style>
  .dropzone {
    border: 1px dashed var(--border);
    border-radius: 8px;
    padding: 28px 16px;
    text-align: center;
    cursor: pointer;
    background: var(--panel-2);
    transition: border-color .15s, background .15s;
  }
  .dropzone:hover:not(.busy) { border-color: var(--accent); }
  .dropzone.over { border-color: var(--accent); background: var(--panel); }
  .dropzone.busy { cursor: default; opacity: .8; }
  .dropzone .link { color: var(--accent); text-decoration: underline; }
  .hint { cursor: help; border-bottom: 1px dotted var(--muted); }
</style>
