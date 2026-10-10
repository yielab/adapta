<script lang="ts">
  // Behavior (fine-tune) flow — eval set → import adapter → verification → serve.
  // Adapters are trained elsewhere and imported; the eval gate scores them against
  // the base model on the chosen eval set. Dataset validation, document indexing
  // and adapter gating are all async and polled so a button never sits frozen.
  import { api, ApiError } from "../lib/api";
  import { navigate } from "../lib/router";
  import { toastError, toastSuccess } from "../lib/toast";
  import type { Project, ProjectFile, Dataset, Adapter } from "../lib/types";

  import StatusBadge from "../components/StatusBadge.svelte";

  let { project }: { project: Project } = $props();

  const POLL_MS = 2000;

  // Minimum rows to keep when curating a dataset (the server's eval-set floor).
  const MIN_SAMPLES = 20;
  import { BRAND } from "../lib/brand";
  const DOCS_URL = BRAND.docs;
  const IMPORT_GUIDE_URL =
    "https://github.com/yielab/adapta/blob/main/docs/user-guide/bring-your-own-adapter.md";

  // ---- Documents (optional knowledge + synthesis source) -------------------
  let files = $state<ProjectFile[]>([]);
  let filesLoading = $state(false);
  let filesLoadErr = $state(false);

  // ---- Datasets -----------------------------------------------------------
  let datasets = $state<Dataset[]>([]);
  let dsLoading = $state(false);
  let dsLoadErr = $state(false);

  // ---- Adapters (declared early: derived/poll state below reads it) --------
  let adapters = $state<Adapter[]>([]);

  // ---- Endpoint existence (so we don't offer to create a second one) ------
  let endpointExists = $state(false);

  // Re-load when the routed project changes.
  let loadedId = $state<string | null>(null);
  $effect(() => {
    if (project.id === loadedId) return;
    loadedId = project.id;
    void loadFiles();
    void loadDatasets();
    void loadAdapters();
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
  const hasPendingAdapter = $derived(
    adapters.some((a) => a.status === "uploaded" || a.status === "processing"),
  );

  $effect(() => {
    const needPoll = hasPendingDataset || hasPendingFile || hasPendingAdapter;
    if (needPoll && poller === null) {
      poller = setInterval(() => {
        if (hasPendingDataset) void refreshPendingDatasets();
        if (hasPendingFile) void loadFiles(true);
        if (hasPendingAdapter) void refreshPendingAdapters();
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
  let evalTask = $state("classify");
  const TASK_HINTS: Record<string, string> = {
    classify: "classify: the response is a label; scored by exact label match",
    extract: "extract: the response is a JSON object; scored by JSON parse rate and per-key match",
    freeform: "freeform: free text; cannot gate an adapter (an adapter evaluated on it ends failed); use classify or extract",
  };

  async function onFilePicked(ev: Event) {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    uploading = true;
    try {
      await api.uploadDataset(project.id, file, evalTask);
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
  // rag_eval (default): retrieval questions for the RAG golden harness.
  // behavior: prompt/response rows usable as an adapter eval set.
  let synthMode = $state<"rag_eval" | "behavior">("rag_eval");
  let synthTask = $state<"classify" | "extract" | "freeform">("extract");
  let synthStyle = $state("");

  async function submitSynthesize() {
    if (synthesizing) return;
    synthesizing = true;
    try {
      await api.synthesize(project.id, {
        n_pairs_per_chunk: nPairs,
        max_chunks: maxChunks,
        mode: synthMode,
        ...(synthMode === "behavior"
          ? { task: synthTask, ...(synthStyle.trim() ? { style_instructions: synthStyle.trim() } : {}) }
          : {}),
      });
      showSynth = false;
      toastSuccess("Synthesis started — generating questions from your documents.");
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
  // ---- Adapters (E4.6) ----------------------------------------------------
  let adLoading = $state(false);
  let adLoadErr = $state(false);
  let adUploading = $state(false);
  let adInput = $state<HTMLInputElement | null>(null);
  let adEvalId = $state("");
  let adName = $state("");
  let selectedAdapterId = $state<string | null>(null);
  let creatingEndpoint = $state(false);

  const validDatasets = $derived(datasets.filter((d) => d.status === "valid"));
  // Default the eval-set picker to the newest valid set; keep the user's choice.
  $effect(() => {
    if (validDatasets.length > 0 && !validDatasets.some((d) => d.id === adEvalId)) {
      adEvalId = validDatasets[validDatasets.length - 1].id;
    }
  });

  // API order is not guaranteed — sort newest first.
  const sortedAdapters = $derived(
    [...adapters].sort((a, b) => b.created_at.localeCompare(a.created_at)),
  );
  const selectedAdapter = $derived(
    sortedAdapters.find((a) => a.id === selectedAdapterId) ?? sortedAdapters[0] ?? null,
  );
  const latestPassed = $derived(sortedAdapters.find((a) => a.status === "passed") ?? null);

  async function loadAdapters(quiet = false) {
    if (!quiet) {
      adLoading = true;
      adLoadErr = false;
    }
    try {
      adapters = await api.listAdapters(project.id);
    } catch (e) {
      if (!quiet) {
        adLoadErr = true;
        reportErr(e, "Could not load adapters.");
      }
    } finally {
      if (!quiet) adLoading = false;
    }
  }

  // Poll only the in-flight adapters (uploaded/processing) and patch them in.
  async function refreshPendingAdapters() {
    const pending = adapters.filter((a) => a.status === "uploaded" || a.status === "processing");
    for (const a of pending) {
      try {
        const fresh = await api.getAdapter(project.id, a.id);
        adapters = adapters.map((x) => (x.id === fresh.id ? fresh : x));
      } catch {
        // Transient poll error — the next tick retries.
      }
    }
  }

  async function onAdapterPicked(ev: Event) {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file || !adEvalId) return;
    adUploading = true;
    try {
      const created = await api.uploadAdapter(project.id, file, adEvalId, adName.trim() || undefined);
      adapters = [created, ...adapters.filter((a) => a.id !== created.id)];
      selectedAdapterId = created.id;
      adName = "";
      toastSuccess("Adapter imported — the eval gate is scoring it against the base model.");
    } catch (e) {
      reportErr(e, "Could not import the adapter.");
    } finally {
      adUploading = false;
      if (adInput) adInput.value = "";
    }
  }

  async function removeAdapter(a: Adapter) {
    try {
      await api.deleteAdapter(project.id, a.id);
      adapters = adapters.filter((x) => x.id !== a.id);
      if (selectedAdapterId === a.id) selectedAdapterId = null;
    } catch (e) {
      // 409 while an endpoint is bound to it — the server message says so.
      reportErr(e, "Could not delete the adapter.");
    }
  }

  async function createEndpoint() {
    if (creatingEndpoint) return;
    creatingEndpoint = true;
    try {
      await api.createEndpoint(project.id);
      endpointExists = true;
      toastSuccess("Endpoint created — it serves the adapter that passed the gate.");
    } catch (e) {
      reportErr(e, "Could not create the endpoint.");
    } finally {
      creatingEndpoint = false;
    }
  }

  function fmtScore(n: number) {
    return n.toFixed(3);
  }
  function fmtDelta(n: number | undefined) {
    if (n == null) return "—";
    return `${n > 0 ? "+" : ""}${n.toFixed(3)}`;
  }
</script>

<div class="stack">
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
      source to synthesize examples from), <strong>2</strong> pick an eval set,
      <strong>3</strong> import your adapter, <strong>4</strong> read the verdict
      against the base model, <strong>5</strong> serve it. A served endpoint
      <strong>also answers from any documents you index here</strong> — facts from
      your documents (with citations), tone and format from the adapter.
    </p>
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
      <h2 style="margin: 0;">2 · Eval set</h2>
      <div class="row" style="gap: 8px;">
        <select bind:value={evalTask} title={TASK_HINTS[evalTask]} disabled={uploading} aria-label="Task">
          <option value="classify">classify</option>
          <option value="extract">extract</option>
          <option value="freeform">freeform (cannot gate)</option>
        </select>
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
          Upload eval set (JSONL, 20–200 rows)
        </button>
        <button class="sm" onclick={() => (showSynth = !showSynth)}>
          Synthesize from documents
        </button>
      </div>
    </div>

    <p class="muted" style="margin: 0 0 8px; font-size: 13px;">
      The eval set is the held-out test an adapter must pass: 20–200 JSONL rows of
      <span class="mono">{`{"prompt": "...", "response": "..."}`}</span>, with a task that decides how answers are scored.
    </p>
    <ul class="approach-list">
      <li><strong>classify</strong> — the response is a label; scored by exact match. Recommended.</li>
      <li><strong>extract</strong> — the response is a JSON object; scored by parse rate and per-key match. Recommended.</li>
      <li><strong>freeform</strong> — cannot gate an adapter: an adapter evaluated on a freeform set ends failed. Use classify or extract.</li>
    </ul>
    <p class="muted" style="margin: 0 0 14px; font-size: 13px;">
      No labelled rows? Index documents above and use <strong>Synthesize</strong> for a first set, then review it.
      Use rows the adapter did not train on.
      <a href={DOCS_URL} target="_blank" rel="noopener">Full guide →</a>
    </p>

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
        <fieldset class="field" style="margin: 0 0 12px; border: 0; padding: 0;" disabled={synthesizing}>
          <legend>What to generate</legend>
          <label style="display: block;">
            <input type="radio" bind:group={synthMode} value="rag_eval" />
            <strong>Retrieval questions</strong> (default) — questions a user could ask of your
            documents, to measure how well search finds the right file.
          </label>
          <label style="display: block;">
            <input type="radio" bind:group={synthMode} value="behavior" />
            <strong>Adapter eval set</strong> — prompt/response rows, with facts quoted from your
            documents, to test an adapter against the base model.
          </label>
        </fieldset>
        {#if synthMode === "behavior"}
          <div class="row wrap" style="gap: 14px; margin-bottom: 12px;">
            <div class="field" style="margin: 0; max-width: 180px;">
              <label for="synth-task">Task</label>
              <select id="synth-task" bind:value={synthTask} disabled={synthesizing}>
                <option value="extract">extract (JSON fields)</option>
                <option value="classify">classify (yes/no)</option>
                <option value="freeform">freeform (cannot gate)</option>
              </select>
            </div>
            <div class="field" style="margin: 0; flex: 1; min-width: 220px;">
              <label for="synth-style">Style (optional)</label>
              <input id="synth-style" type="text" maxlength="1000" bind:value={synthStyle} disabled={synthesizing} />
            </div>
          </div>
        {/if}
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
      <div class="empty">No eval sets yet — upload one or synthesize from your documents to begin.</div>
    {:else}
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Status</th>
            <th>Task</th>
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
              <td>{d.task ?? "—"}</td>
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
                        <label for={`edit-${fld}`} style="font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em;">{fld}</label>
                        <textarea
                          id={`edit-${fld}`}
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

  <!-- ============================ ADAPTER ============================ -->
  <div class="card">
    <div class="row between" style="margin-bottom: 10px;">
      <h2 style="margin: 0;">3 · Adapter</h2>
    </div>
    <p class="muted" style="margin: 0 0 12px;">
      Drop the LoRA you trained elsewhere: a <span class="mono">.gguf</span> adapter, or a
      <span class="mono">.zip</span> holding exactly <span class="mono">adapter_model.safetensors</span>
      and <span class="mono">adapter_config.json</span>. It must target
      <strong class="mono">{project.base_model}</strong>. It is scored against the base model on the
      eval set you pick; it can only be served if it passes.
    </p>
    <p class="muted" style="margin: 0 0 12px; font-size: 13px;">
      Where do I train it? Adapta does not train. Train a LoRA with any tool, then import it here.
      <a href={IMPORT_GUIDE_URL} target="_blank" rel="noopener">Import guide →</a>
    </p>

    {#if validDatasets.length === 0}
      <div class="empty">Add a valid eval set in step 2 first — the adapter is scored on it.</div>
    {:else}
      <div class="row wrap" style="gap: 14px; align-items: flex-end;">
        <div class="field" style="margin: 0; min-width: 220px;">
          <label for="ad-eval">Eval set</label>
          <select id="ad-eval" bind:value={adEvalId} disabled={adUploading}>
            {#each validDatasets as d (d.id)}
              <option value={d.id}>{d.name} · {d.task ?? "?"} · {d.num_samples ?? "?"} rows</option>
            {/each}
          </select>
        </div>
        <div class="field" style="margin: 0; min-width: 180px;">
          <label for="ad-name">Name (optional)</label>
          <input id="ad-name" type="text" maxlength="128" bind:value={adName} disabled={adUploading} placeholder="defaults to the file name" />
        </div>
        <input
          bind:this={adInput}
          type="file"
          accept=".gguf,.zip"
          onchange={onAdapterPicked}
          style="display: none;"
          id="ad-file"
        />
        <button class="primary sm" onclick={() => adInput?.click()} disabled={adUploading || !adEvalId}>
          {#if adUploading}<span class="spinner"></span>{/if}
          Import adapter (.gguf or .zip)
        </button>
      </div>
    {/if}

    {#if adLoading}
      <div class="row" style="gap: 8px; margin-top: 12px;"><span class="spinner"></span><small>Loading adapters…</small></div>
    {:else if adLoadErr}
      <div class="empty" style="margin-top: 12px;">
        <p>Could not load adapters.</p>
        <button class="ghost sm" onclick={() => loadAdapters()}>Retry</button>
      </div>
    {:else if sortedAdapters.length > 0}
      <table style="margin-top: 14px;">
        <thead>
          <tr><th>Name</th><th>Format</th><th>Size</th><th>Status</th><th>Imported</th><th></th></tr>
        </thead>
        <tbody>
          {#each sortedAdapters as a (a.id)}
            <tr>
              <td class="mono">{a.name}</td>
              <td>{a.format}</td>
              <td class="mono">{fmtSize(a.size_bytes)}</td>
              <td>
                <div class="row" style="gap: 8px;">
                  {#if a.status === "uploaded" || a.status === "processing"}<span class="spinner"></span>{/if}
                  <StatusBadge status={a.status} />
                </div>
              </td>
              <td class="muted">{fmtDate(a.created_at)}</td>
              <td style="text-align: right; white-space: nowrap;">
                <button class="ghost sm" onclick={() => (selectedAdapterId = a.id)} disabled={a.id === selectedAdapter?.id}>View</button>
                <button class="danger ghost sm" onclick={() => removeAdapter(a)}>Delete</button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>

  <!-- ========================== VERIFICATION ========================== -->
  <div class="card">
    <div class="row between" style="margin-bottom: 10px;">
      <h2 style="margin: 0;">4 · Verification</h2>
    </div>

    {#if !selectedAdapter}
      <div class="empty">Import an adapter to see how it scores against the base model.</div>
    {:else if selectedAdapter.status === "uploaded" || selectedAdapter.status === "processing"}
      <div class="row" style="gap: 8px;">
        <span class="spinner"></span>
        <span>
          {selectedAdapter.status === "uploaded" ? "Queued for the eval gate…" : "Scoring the adapter and the base model on the eval set…"}
        </span>
      </div>
      <p class="muted" style="margin: 8px 0 0; font-size: 12px;">
        Both models answer every held-out row on CPU, so this takes a while. The page updates by itself.
      </p>
    {:else}
      {@const m = selectedAdapter.eval_metrics}
      <div class="row" style="gap: 10px; margin-bottom: 12px;">
        <StatusBadge status={selectedAdapter.status} label={selectedAdapter.status === "passed" ? "Passed the gate" : "Failed the gate"} />
        <span class="mono">{selectedAdapter.name}</span>
      </div>

      {#if selectedAdapter.failure_reason}
        <div class="ds-err mono" style="margin: 0 0 12px;">{selectedAdapter.failure_reason}</div>
      {/if}

      {#if m && m.adapter_score != null && m.base_score != null}
        <div class="score-grid">
          <div class="score-tile">
            <span class="muted score-label">Adapter</span>
            <span class="score-val">{fmtScore(m.adapter_score)}</span>
          </div>
          <div class="score-tile">
            <span class="muted score-label">Base model</span>
            <span class="score-val">{fmtScore(m.base_score)}</span>
          </div>
          <div class="score-tile">
            <span class="muted score-label">Difference</span>
            <span class="score-val" class:good={(m.delta ?? 0) > 0} class:bad={(m.delta ?? 0) < 0}>{fmtDelta(m.delta)}</span>
          </div>
        </div>
        <p class="muted" style="margin: 10px 0 0; font-size: 13px;">
          Task <strong>{m.task ?? "?"}</strong> on {m.n_rows ?? "?"} held-out rows.
          {#if m.rule}<strong>Rule:</strong> {m.rule}{/if}
          {#if m.absolute_floor != null || m.min_improvement != null}
            <span class="mono">
              (floor {m.absolute_floor != null ? fmtScore(m.absolute_floor) : "—"},
              min. improvement {m.min_improvement != null ? fmtScore(m.min_improvement) : "—"})
            </span>
          {/if}
        </p>
        {#if m.adapter_seconds_per_row != null && m.base_seconds_per_row != null}
          <p class="muted" style="margin: 4px 0 0; font-size: 12px;">
            Speed on CPU: adapter {m.adapter_seconds_per_row.toFixed(1)} s/row · base {m.base_seconds_per_row.toFixed(1)} s/row.
          </p>
        {/if}

        {#if m.samples && m.samples.length > 0}
          <h3 style="margin: 16px 0 8px;">Sample predictions</h3>
          <div class="review-rows">
            {#each m.samples as s, i (i)}
              <div class="review-row">
                <div class="review-row-body">
                  <div><span class="sample-key">Prompt</span> <span class="review-cell">{s.prompt}</span></div>
                  <div><span class="sample-key">Expected</span> <span class="review-cell">{s.reference}</span></div>
                  <div><span class="sample-key">Base</span> <span class="review-cell">{s.base}</span></div>
                  <div><span class="sample-key">Adapter</span> <span class="review-cell">{s.adapter}</span></div>
                </div>
              </div>
            {/each}
          </div>
        {/if}
      {:else if selectedAdapter.status === "failed" && !selectedAdapter.failure_reason}
        <p class="muted" style="margin: 0;">The adapter failed before it could be scored.</p>
      {/if}
    {/if}
  </div>

  <!-- ============================ ENDPOINT ============================ -->
  <div class="card">
    <div class="row between" style="margin-bottom: 10px;">
      <h2 style="margin: 0;">5 · Serve</h2>
    </div>

    {#if endpointExists}
      <p class="muted" style="margin: 0 0 12px;">
        An endpoint exists for this project. Manage its slug, API keys and the adapter it serves
        under the <strong>Endpoint &amp; keys</strong> tab.
      </p>
      <button class="sm" onclick={() => navigate("/projects/" + project.id)}>
        Go to Endpoint &amp; keys
      </button>
    {:else if latestPassed}
      <p class="muted" style="margin: 0 0 12px;">
        <span class="mono">{latestPassed.name}</span> passed the gate. Creating the endpoint serves it on
        <span class="mono">{project.base_model}</span>{#if indexedDocs > 0}, answering from your indexed documents with citations{/if}.
      </p>
      <button class="primary sm" onclick={createEndpoint} disabled={creatingEndpoint}>
        {#if creatingEndpoint}<span class="spinner"></span>{/if}
        Create endpoint
      </button>
    {:else}
      <p class="muted" style="margin: 0;">
        An endpoint is created from the latest adapter that has passed the eval gate. None has yet.
      </p>
    {/if}
  </div>
</div>

<style>
  .explainer { background: var(--panel-2); }

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

  /* E4.6: eval-gate verdict */
  .score-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 10px;
  }
  .score-tile {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 10px 12px;
    background: var(--panel-1);
    border: 1px solid var(--border);
    border-radius: 6px;
  }
  .score-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }
  .score-val { font-size: 22px; font-weight: 600; font-family: var(--mono); }
  .score-val.good { color: var(--green); }
  .score-val.bad { color: var(--red); }
  .sample-key {
    display: inline-block;
    min-width: 62px;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
  }
</style>
