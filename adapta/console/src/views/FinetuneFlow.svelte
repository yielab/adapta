<script lang="ts">
  // Behavior (fine-tune) setup flow — documents → dataset review → endpoint.
  // This is the "change how it behaves" path. Dataset validation is async and
  // polled so a button never sits frozen. Adapters arrive by import (E4.2+).
  import { api, ApiError } from "../lib/api";
  import { navigate } from "../lib/router";
  import { toastError, toastSuccess } from "../lib/toast";
  import type { Project, ProjectFile, Dataset } from "../lib/types";

  import StatusBadge from "../components/StatusBadge.svelte";

  let { project }: { project: Project } = $props();

  const POLL_MS = 2000;

  // Minimum rows to keep when curating a dataset.
  const MIN_SAMPLES = 10;
  import { BRAND } from "../lib/brand";
  const DOCS_URL = BRAND.docs;

  // ---- Documents (optional knowledge + synthesis source) -------------------
  let files = $state<ProjectFile[]>([]);
  let filesLoading = $state(false);
  let filesLoadErr = $state(false);

  // ---- Datasets -----------------------------------------------------------
  let datasets = $state<Dataset[]>([]);
  let dsLoading = $state(false);
  let dsLoadErr = $state(false);

  // ---- Endpoint existence (so we don't offer to create a second one) ------
  let endpointExists = $state(false);

  // Re-load when the routed project changes.
  let loadedId = $state<string | null>(null);
  $effect(() => {
    if (project.id === loadedId) return;
    loadedId = project.id;
    void loadFiles();
    void loadDatasets();
    void checkEndpoint();
  });

  // ---- Polling lifecycle --------------------------------------------------
  // A single interval drives the dataset-validation and document-indexing polls.
  let poller: ReturnType<typeof setInterval> | null = null;

  const hasPendingDataset = $derived(
    datasets.some((d) => d.status === "uploaded" || d.status === "validating"),
  );
  const hasPendingFile = $derived(
    files.some((f) => f.status === "pending" || f.status === "processing"),
  );

  $effect(() => {
    const needPoll = hasPendingDataset || hasPendingFile;
    if (needPoll && poller === null) {
      poller = setInterval(() => {
        if (hasPendingDataset) void refreshPendingDatasets();
        if (hasPendingFile) void loadFiles(true);
      }, POLL_MS);
    } else if (!needPoll && poller !== null) {
      clearInterval(poller);
      poller = null;
    }
    return () => {
      if (poller !== null) {
        clearInterval(poller);
        poller = null;
      }
    };
  });

  async function loadFiles(quiet = false) {
    if (!quiet) {
      filesLoading = true;
      filesLoadErr = false;
    }
    try {
      files = await api.listFiles(project.id);
    } catch (e) {
      if (!quiet) {
        filesLoadErr = true;
        reportErr(e, "Could not load documents.");
      }
    } finally {
      if (!quiet) filesLoading = false;
    }
  }

  async function loadDatasets() {
    dsLoading = true;
    dsLoadErr = false;
    try {
      datasets = await api.listDatasets(project.id);
    } catch (e) {
      dsLoadErr = true;
      reportErr(e, "Could not load datasets.");
    } finally {
      dsLoading = false;
    }
  }

  // Poll only the in-flight datasets, then patch them into the list so the
  // others (and the UI's scroll/selection) don't flicker.
  async function refreshPendingDatasets() {
    const pending = datasets.filter(
      (d) => d.status === "uploaded" || d.status === "validating",
    );
    for (const d of pending) {
      try {
        const fresh = await api.getDataset(project.id, d.id);
        datasets = datasets.map((x) => (x.id === fresh.id ? fresh : x));
      } catch {
        // Transient poll error — swallow; the next tick retries.
      }
    }
  }

  async function checkEndpoint() {
    try {
      await api.getEndpoint(project.id);
      endpointExists = true;
    } catch (e) {
      // 404 just means "not created yet" — not an error worth surfacing.
      endpointExists = false;
    }
  }

  function reportErr(e: unknown, fallback: string) {
    if (e instanceof ApiError) toastError(e.message, e.correlationId);
    else toastError(fallback);
  }

  // ---- Upload documents (knowledge + synthesis source) --------------------
  let docUploading = $state(false);
  let docInput = $state<HTMLInputElement | null>(null);
  const indexedDocs = $derived(files.filter((f) => f.status === "indexed").length);

  async function onDocPicked(ev: Event) {
    const input = ev.target as HTMLInputElement;
    const picked = input.files ? Array.from(input.files) : [];
    if (picked.length === 0) return;
    docUploading = true;
    try {
      for (const f of picked) {
        await api.uploadFile(project.id, f);
      }
      toastSuccess(
        picked.length === 1
          ? "Document uploaded — indexing started."
          : `${picked.length} documents uploaded — indexing started.`,
      );
      await loadFiles();
    } catch (e) {
      reportErr(e, "Could not upload the document.");
    } finally {
      docUploading = false;
      if (docInput) docInput.value = "";
    }
  }

  async function removeDoc(f: ProjectFile) {
    try {
      await api.deleteFile(project.id, f.id);
      files = files.filter((x) => x.id !== f.id);
    } catch (e) {
      reportErr(e, "Could not remove the document.");
    }
  }

  function fmtSize(n: number) {
    if (n >= 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
    if (n >= 1024) return `${Math.round(n / 1024)} KB`;
    return `${n} B`;
  }

  // ---- Upload JSONL -------------------------------------------------------
  let uploading = $state(false);
  let fileInput = $state<HTMLInputElement | null>(null);

  async function onFilePicked(ev: Event) {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    uploading = true;
    try {
      await api.uploadDataset(project.id, file);
      toastSuccess("Dataset uploaded — validating against the schema…");
      await loadDatasets();
    } catch (e) {
      reportErr(e, "Could not upload the dataset.");
    } finally {
      uploading = false;
      if (fileInput) fileInput.value = "";
    }
  }

  // ---- Synthesize from documents -----------------------------------------
  let showSynth = $state(false);
  let nPairs = $state(2);
  let maxChunks = $state(50);
  let synthesizing = $state(false);

  async function submitSynthesize() {
    if (synthesizing) return;
    synthesizing = true;
    try {
      await api.synthesize(project.id, {
        n_pairs_per_chunk: nPairs,
        max_chunks: maxChunks,
      });
      showSynth = false;
      toastSuccess("Synthesis started — generating Q/A pairs from your documents.");
      await loadDatasets();
    } catch (e) {
      reportErr(e, "Could not start synthesis.");
    } finally {
      synthesizing = false;
    }
  }

  // ---- Dataset review (D6) -----------------------------------------------
  type ReviewRow = { row: Record<string, unknown>; dropped: boolean };
  let reviewDataset = $state<Dataset | null>(null);
  let reviewRows = $state<ReviewRow[]>([]);
  let reviewLoading = $state(false);
  let editingIdx = $state<number | null>(null);
  let editBuf = $state<Record<string, string>>({});
  let saving = $state(false);

  const keptRows = $derived(reviewRows.filter((r) => !r.dropped));

  // Datasets hold SFT rows only: prompt + response.
  function _textFields(_row: Record<string, unknown>): string[] {
    return ["prompt", "response"];
  }

  async function openReview(d: Dataset) {
    reviewDataset = d;
    reviewRows = [];
    reviewLoading = true;
    editingIdx = null;
    try {
      const resp = await api.getDatasetRows(project.id, d.id);
      reviewRows = resp.rows.map((r) => ({ row: r, dropped: false }));
    } catch (e) {
      reportErr(e, "Could not load dataset rows.");
      reviewDataset = null;
    } finally {
      reviewLoading = false;
    }
  }

  function closeReview() {
    reviewDataset = null;
    reviewRows = [];
    editingIdx = null;
  }

  function dropRow(i: number) {
    reviewRows = reviewRows.map((r, idx) => (idx === i ? { ...r, dropped: true } : r));
  }

  function undropRow(i: number) {
    reviewRows = reviewRows.map((r, idx) => (idx === i ? { ...r, dropped: false } : r));
  }

  function startEdit(i: number) {
    editingIdx = i;
    const fields = _textFields(reviewRows[i].row);
    editBuf = Object.fromEntries(fields.map((k) => [k, String(reviewRows[i].row[k] ?? "")]));
  }

  function cancelEdit() {
    editingIdx = null;
    editBuf = {};
  }

  function commitEdit(i: number) {
    const updated = { ...reviewRows[i].row, ...editBuf };
    reviewRows = reviewRows.map((r, idx) => (idx === i ? { ...r, row: updated } : r));
    editingIdx = null;
    editBuf = {};
  }

  async function saveCurated() {
    if (!reviewDataset) return;
    if (keptRows.length < MIN_SAMPLES) {
      toastError(`Keep at least ${MIN_SAMPLES} rows.`);
      return;
    }
    saving = true;
    try {
      const newDs = await api.curateDataset(
        project.id,
        reviewDataset.id,
        keptRows.map((r) => r.row),
      );
      toastSuccess(`Curated dataset saved — ${newDs.num_samples} rows.`);
      closeReview();
      await loadDatasets();
    } catch (e) {
      reportErr(e, "Could not save curated dataset.");
    } finally {
      saving = false;
    }
  }

  // ---- helpers ------------------------------------------------------------
  function fmtDate(iso: string) {
    const d = new Date(iso);
    return isNaN(d.getTime()) ? iso : d.toLocaleString();
  }
</script>

<div class="stack">
  <!-- What's an adapter? — explain the jargon inline. -->
  <aside class="card explainer">
    <h2 style="margin: 0 0 6px;">Change how your model behaves</h2>
    <p class="muted" style="margin: 0;">
      A fine-tune teaches the model a style, format, or skill from examples. The
      result is a small <strong>adapter</strong> — a lightweight patch layered on
      the base model, rather than a whole new model. Adapters are imported, not
      trained here.
    </p>
    <p class="muted" style="margin: 8px 0 0;">
      The path: <strong>1</strong> optionally index documents (knowledge + a
      source to synthesize examples from), <strong>2</strong> prepare and review
      a dataset. A served fine-tune endpoint <strong>also answers from any
      documents you index here</strong> — facts from your documents (with
      citations), tone and format from the fine-tune.
    </p>
    <div class="use-case-grid">
      <div class="use-case-item">
        <strong>Support voice</strong>
        <span class="muted">Ticket history or chat logs → answers in your team's tone, format, and escalation rules.</span>
      </div>
      <div class="use-case-item">
        <strong>Domain Q&amp;A</strong>
        <span class="muted">Product docs, handbooks, or policies → accurate on-brand answers. <em>Synthesize</em> skips manual labeling.</span>
      </div>
      <div class="use-case-item">
        <strong>Structured output</strong>
        <span class="muted">Free-form text → consistent JSON, tables, or a fixed report format. Consistency across rows is what the model learns.</span>
      </div>
      <div class="use-case-item">
        <strong>Code or writing style</strong>
        <span class="muted">Before/after pairs that enforce a house style, naming convention, or editorial voice.</span>
      </div>
    </div>
  </aside>

  <!-- ====================== DOCUMENTS (optional) ====================== -->
  <div class="card">
    <div class="row between" style="margin-bottom: 12px;">
      <h2 style="margin: 0;">1 · Documents <span class="muted" style="font-weight: 400;">(optional)</span></h2>
      <div class="row" style="gap: 8px;">
        <input
          bind:this={docInput}
          type="file"
          multiple
          accept=".pdf,.docx,.txt,.md,.html"
          onchange={onDocPicked}
          style="display: none;"
          id="ft-doc-file"
        />
        <button class="sm" onclick={() => docInput?.click()} disabled={docUploading}>
          {#if docUploading}<span class="spinner"></span>{/if}
          Upload documents
        </button>
      </div>
    </div>

    <p class="muted" style="margin: 0 0 12px;">
      Documents indexed here do two jobs: they are the source for
      <strong>“Synthesize from documents”</strong> below, and once your endpoint
      is live the model <strong>answers from them with citations</strong> —
      knowledge from the documents, behavior from the fine-tune. PDF, DOCX, TXT,
      MD or HTML.
    </p>

    {#if filesLoading}
      <div class="row" style="gap: 8px;">
        <span class="spinner"></span><small>Loading documents…</small>
      </div>
    {:else if filesLoadErr}
      <div class="empty">
        <p>Could not load documents.</p>
        <button class="ghost sm" onclick={() => loadFiles()}>Retry</button>
      </div>
    {:else if files.length === 0}
      <div class="empty">
        No documents yet — optional. Upload some to ground answers in your own
        material, or skip straight to the dataset.
      </div>
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
              <td class="mono">{f.filename}</td>
              <td>
                <div class="row" style="gap: 8px;">
                  {#if f.status === "pending" || f.status === "processing"}
                    <span class="spinner"></span>
                  {/if}
                  <StatusBadge status={f.status} />
                  {#if f.status === "indexed" && f.num_chunks != null}
                    <small class="muted">{f.num_chunks} chunk{f.num_chunks === 1 ? "" : "s"}</small>
                  {/if}
                </div>
              </td>
              <td class="mono">{fmtSize(f.size_bytes)}</td>
              <td style="text-align: right;">
                <button class="danger ghost sm" onclick={() => removeDoc(f)}>Remove</button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
      {#if indexedDocs > 0}
        <p class="muted" style="margin: 10px 0 0; font-size: 12px;">
          {indexedDocs} document{indexedDocs === 1 ? "" : "s"} indexed — your served
          endpoint will cite {indexedDocs === 1 ? "it" : "them"} when answering.
        </p>
      {/if}
    {/if}
  </div>

  <!-- ============================ DATASET ============================ -->
  <div class="card">
    <div class="row between" style="margin-bottom: 12px;">
      <h2 style="margin: 0;">2 · Dataset</h2>
      <div class="row" style="gap: 8px;">
        <input
          bind:this={fileInput}
          type="file"
          accept=".jsonl,application/jsonl,application/x-ndjson,text/plain"
          onchange={onFilePicked}
          style="display: none;"
          id="ds-file"
        />
        <button
          class="sm"
          onclick={() => fileInput?.click()}
          disabled={uploading}
        >
          {#if uploading}<span class="spinner"></span>{/if}
          Upload JSONL
        </button>
        <button class="sm" onclick={() => (showSynth = !showSynth)}>
          Synthesize from documents
        </button>
      </div>
    </div>

      <p class="muted" style="margin: 0 0 4px; font-size: 13px;">Choose your path based on what you have:</p>
      <ul class="approach-list">
        <li><strong>Have documents?</strong> Index them in step 1, then click <strong>Synthesize</strong> — fastest path to a first dataset.</li>
        <li><strong>Have logs or past examples?</strong> Export as prompt/response pairs and upload a <span class="mono">.jsonl</span> file.</li>
        <li><strong>Want exact output format?</strong> Hand-write 50–100 focused examples of the input → output pattern you need.</li>
      </ul>

    <!-- Collapsible: what a dataset is, its exact format, and where to get one. -->
    <details class="help" style="margin-bottom: 14px;">
      <summary>Use cases, format &amp; quality guide</summary>
      <div class="help-body">
        <h4>Common use cases</h4>
        <ul style="margin: 0 0 4px; padding-left: 18px; line-height: 1.8;">
          <li><strong>Support voice</strong> — export past tickets or chat logs as prompt/response pairs; the model learns your tone, format, and escalation rules.</li>
          <li><strong>Domain Q&amp;A</strong> — have product docs or handbooks? Use <em>Synthesize</em> to auto-generate Q/A pairs. No manual labeling needed.</li>
          <li><strong>Structured output</strong> — write focused examples of the exact input → JSON / table / report output you need. Consistency is what the model learns.</li>
          <li><strong>Code or writing style</strong> — before/after pairs demonstrating a house style, naming convention, or editorial voice.</li>
        </ul>

        <h4>What makes a good dataset</h4>
        <ul style="margin: 0 0 4px; padding-left: 18px; line-height: 1.8;">
          <li><strong>Focus on one task.</strong> Don't mix a support-voice dataset with a JSON-extraction task — use a separate adapter for each.</li>
          <li><strong>Consistent output format.</strong> If some responses are JSON and others are prose, the model learns the inconsistency too.</li>
          <li><strong>Coverage over perfection.</strong> 100 diverse examples of the same task outperform 10 polished ones.</li>
          <li><strong>Size matters for evaluation.</strong> Part of a dataset is held out to score an adapter, so keep enough rows for both.</li>
        </ul>

        <h4>Format — JSONL (one JSON object per line)</h4>
        <pre class="code" style="margin: 4px 0 8px; white-space: pre-wrap;">{`{"prompt": "Summarize this support ticket", "response": "Customer can't log in after the 2.3 update; cause is the expired token cache.", "system": "You are a concise support assistant."}`}</pre>
        <ul>
          <li><code>prompt</code> <strong>(required)</strong> — the instruction or question.</li>
          <li><code>response</code> <strong>(required)</strong> — the ideal answer.</li>
          <li><code>system</code> (optional) — persona / context for the turn.</li>
          <li><code>metadata</code> (optional) — free-form (source, quality score…).</li>
        </ul>

        <h4>Minimum requirements</h4>
        <ul>
          <li>At least <strong>{MIN_SAMPLES} valid rows</strong>; aim for 50–500+ for a noticeable effect.</li>
          <li>Every <code>prompt</code> and <code>response</code> must be non-empty.</li>
        </ul>

        <h4>Where to get one</h4>
        <ol>
          <li><strong>Synthesize from your documents</strong> — the button above turns indexed chunks into Q/A pairs. Fastest start.</li>
          <li><strong>Export from your own systems</strong> — support tickets, chat logs, past Q/A, reshaped into prompt/response pairs.</li>
          <li><strong>Hand-write</strong> a few dozen gold examples of exactly the behavior you want.</li>
          <li><strong>Public datasets</strong> — e.g. instruction sets on Hugging Face (Dolly, OpenAssistant); convert each row to the shape above.</li>
        </ol>
        <p style="margin: 10px 0 0;">
          <a href={DOCS_URL} target="_blank" rel="noopener">Full guide →</a>
        </p>
      </div>
    </details>

    {#if showSynth}
      <div class="muted-box" style="margin-bottom: 14px;">
        <h3>Synthesize a dataset</h3>
        <p class="muted" style="margin: 0 0 4px;">
          Reads passages from documents you've already indexed and asks the base
          model to draft example question/answer pairs from them — a quick way to
          bootstrap a dataset. Review the result before relying on it.
        </p>
        <p class="muted" style="margin: 0 0 12px; font-size: 12px;">
          <strong>Pairs per chunk</strong>: how many examples to draft from each passage.
          <strong>Max chunks</strong>: how many passages to use — higher means more data, but slower.
        </p>
        <div class="row wrap" style="gap: 14px; align-items: flex-end;">
          <div class="field" style="margin: 0; max-width: 180px;">
            <label for="synth-pairs">Pairs per chunk</label>
            <input
              id="synth-pairs"
              type="number"
              min="1"
              max="10"
              bind:value={nPairs}
              disabled={synthesizing}
            />
          </div>
          <div class="field" style="margin: 0; max-width: 180px;">
            <label for="synth-chunks">Max chunks</label>
            <input
              id="synth-chunks"
              type="number"
              min="1"
              max="500"
              bind:value={maxChunks}
              disabled={synthesizing}
            />
          </div>
          <div class="row" style="gap: 8px;">
            <button
              class="primary sm"
              onclick={submitSynthesize}
              disabled={synthesizing}
            >
              {#if synthesizing}<span class="spinner"></span>{/if}
              Start synthesis
            </button>
            <button
              class="ghost sm"
              onclick={() => (showSynth = false)}
              disabled={synthesizing}
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    {/if}

    {#if dsLoading}
      <div class="row" style="gap: 8px;">
        <span class="spinner"></span><small>Loading datasets…</small>
      </div>
    {:else if dsLoadErr}
      <div class="empty">
        <p>Could not load datasets.</p>
        <button class="ghost sm" onclick={loadDatasets}>Retry</button>
      </div>
    {:else if datasets.length === 0}
      <div class="empty">No datasets yet — upload or synthesize one to begin.</div>
    {:else}
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Status</th>
            <th>Samples</th>
            <th>Created</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {#each datasets as d (d.id)}
            <tr>
              <td class="mono">
                {d.name}
                {#if d.source_dataset_id}
                  <span class="badge-tag">curated</span>
                {/if}
              </td>
              <td>
                <div class="row" style="gap: 8px;">
                  {#if d.status === "uploaded" || d.status === "validating"}
                    <span class="spinner"></span>
                  {/if}
                  <StatusBadge status={d.status} />
                </div>
                {#if d.status === "invalid" && d.validation_error}
                  <div class="ds-err mono">{d.validation_error}</div>
                {/if}
              </td>
              <td>{d.status === "valid" && d.num_samples !== null ? d.num_samples : "—"}</td>
              <td class="muted">{fmtDate(d.created_at)}</td>
              <td>
                {#if d.status === "valid"}
                  <button
                    class="ghost sm"
                    onclick={() => openReview(d)}
                    disabled={reviewDataset !== null}
                  >Review</button>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}

    <!-- D6: inline dataset review panel -->
    {#if reviewDataset}
      <div class="muted-box" style="margin-top: 14px;">
        <div class="row between" style="margin-bottom: 10px;">
          <h3 style="margin: 0;">
            Reviewing <span class="mono">{reviewDataset.name}</span>
            {#if !reviewLoading}
              <span class="muted" style="font-weight: 400; font-size: 14px;">
                — {keptRows.length} / {reviewRows.length} rows kept
              </span>
            {/if}
          </h3>
          <button class="ghost sm" onclick={closeReview} disabled={saving}>Close</button>
        </div>

        {#if reviewLoading}
          <div class="row" style="gap: 8px;"><span class="spinner"></span><small>Loading rows…</small></div>
        {:else if reviewRows.length === 0}
          <div class="empty">No rows found in this dataset.</div>
        {:else}
          <p class="muted" style="margin: 0 0 10px; font-size: 13px;">
            Drop rows that are off-topic or low-quality. You can also edit a row inline.
            When done, save a curated version.
          </p>

          <div class="review-rows">
            {#each reviewRows as rr, i (i)}
              {@const fields = _textFields(rr.row)}
              <div class="review-row" class:dropped={rr.dropped}>
                <div class="review-row-body">
                  {#if editingIdx === i}
                    <!-- edit mode -->
                    {#each fields as fld}
                      <div class="field" style="margin: 0 0 6px;">
                        <label style="font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em;">{fld}</label>
                        <textarea
                          rows="3"
                          style="width: 100%; box-sizing: border-box; resize: vertical;"
                          bind:value={editBuf[fld]}
                        ></textarea>
                      </div>
                    {/each}
                    <div class="row" style="gap: 6px;">
                      <button class="primary sm" onclick={() => commitEdit(i)}>Save</button>
                      <button class="ghost sm" onclick={cancelEdit}>Cancel</button>
                    </div>
                  {:else}
                    <!-- view mode -->
                    {#each fields as fld}
                      <div style="margin-bottom: 4px;">
                        <span class="muted" style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em;">{fld}:</span>
                        <span class="review-cell">{String(rr.row[fld] ?? "")}</span>
                      </div>
                    {/each}
                  {/if}
                </div>
                <div class="review-row-actions">
                  {#if rr.dropped}
                    <button class="ghost sm" onclick={() => undropRow(i)}>Restore</button>
                  {:else}
                    {#if editingIdx !== i}
                      <button class="ghost sm" onclick={() => startEdit(i)}>Edit</button>
                    {/if}
                    <button class="ghost sm danger" onclick={() => dropRow(i)} disabled={editingIdx === i}>Drop</button>
                  {/if}
                </div>
              </div>
            {/each}
          </div>

          <div class="row" style="gap: 8px; margin-top: 14px; align-items: center;">
            <button
              class="primary sm"
              onclick={saveCurated}
              disabled={keptRows.length < MIN_SAMPLES || saving || editingIdx !== null}
            >
              {#if saving}<span class="spinner"></span>{/if}
              Save curated version ({keptRows.length} rows)
            </button>
            <button class="ghost sm" onclick={closeReview} disabled={saving}>Cancel</button>
            {#if keptRows.length < MIN_SAMPLES}
              <small class="muted">Keep at least {MIN_SAMPLES} rows.</small>
            {/if}
          </div>
        {/if}
      </div>
    {/if}
  </div>

  <!-- ============================ ENDPOINT ============================ -->
  <div class="card">
    <div class="row between" style="margin-bottom: 10px;">
      <h2 style="margin: 0;">3 · Serve</h2>
    </div>

    {#if endpointExists}
      <p class="muted" style="margin: 0 0 12px;">
        An endpoint exists for this project. Manage its slug and API keys under
        the <strong>Endpoint &amp; keys</strong> tab.
      </p>
      <button class="sm" onclick={() => navigate("/projects/" + project.id)}>
        Go to Endpoint &amp; keys
      </button>
    {:else}
      <p class="muted" style="margin: 0;">
        An endpoint is created once an adapter has been imported for this project.
      </p>
    {/if}
  </div>
</div>

<style>
  .explainer { background: var(--panel-2); }

  .use-case-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 8px;
    margin-top: 14px;
  }
  .use-case-item {
    display: flex;
    flex-direction: column;
    gap: 3px;
    padding: 10px 12px;
    background: var(--panel-1);
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 13px;
  }
  .use-case-item strong { font-size: 13px; }

  .approach-list {
    margin: 0 0 14px;
    padding-left: 20px;
    font-size: 14px;
    line-height: 1.9;
    color: var(--muted);
  }

  .ds-err {
    margin-top: 6px;
    color: var(--red);
    font-size: 12px;
    white-space: pre-wrap;
    word-break: break-word;
  }

  /* Center inline spinners inside buttons (matches Projects.svelte). */
  button :global(.spinner) { margin-right: 6px; vertical-align: middle; }

  /* D6: dataset review panel */
  .badge-tag {
    display: inline-block;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: 1px 5px;
    border-radius: 3px;
    background: var(--panel-3, #2a2a3a);
    color: var(--muted);
    margin-left: 6px;
    vertical-align: middle;
  }

  .review-rows {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-height: 540px;
    overflow-y: auto;
    padding-right: 4px;
  }

  .review-row {
    display: flex;
    gap: 10px;
    align-items: flex-start;
    padding: 10px 12px;
    background: var(--panel-1);
    border: 1px solid var(--border);
    border-radius: 6px;
    transition: opacity 0.15s;
  }

  .review-row.dropped {
    opacity: 0.4;
    border-style: dashed;
  }

  .review-row-body {
    flex: 1;
    min-width: 0;
    font-size: 13px;
    line-height: 1.5;
  }

  .review-cell {
    white-space: pre-wrap;
    word-break: break-word;
  }

  .review-row-actions {
    display: flex;
    flex-direction: column;
    gap: 4px;
    flex-shrink: 0;
  }

  button.danger { color: var(--red); }
</style>
