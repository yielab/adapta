<script lang="ts">
  // Behavior (fine-tune) setup flow — dataset → job → eval gate → endpoint.
  // TODO §5.6F. We NEVER call this "training" in the knowledge sense: this is
  // the "change how it behaves" path. Datasets and jobs are async; both are
  // polled so a button never sits frozen.
  import { api, ApiError } from "../lib/api";
  import { navigate } from "../lib/router";
  import { toastError, toastSuccess } from "../lib/toast";
  import type { Project, Dataset, TrainingJob } from "../lib/types";

  import StatusBadge from "../components/StatusBadge.svelte";

  let { project }: { project: Project } = $props();

  // The eval-gate threshold the backend enforces (EvalGateFailed at < 0.6).
  const EVAL_THRESHOLD = 0.6;
  const POLL_MS = 2000;

  // Minimum valid rows the backend accepts before a dataset can train.
  const MIN_SAMPLES = 10;
  const DOCS_URL =
    "https://github.com/santiagoyie/brainFromCero/blob/main/docs/user-guide/operator-console.md";

  // ---- Datasets -----------------------------------------------------------
  let datasets = $state<Dataset[]>([]);
  let dsLoading = $state(false);
  let dsLoadErr = $state(false);

  // ---- Jobs ---------------------------------------------------------------
  let jobs = $state<TrainingJob[]>([]);
  let jobsLoading = $state(false);
  let jobsLoadErr = $state(false);

  // ---- Endpoint existence (so we don't offer to create a second one) ------
  let endpointExists = $state(false);

  // Re-load when the routed project changes.
  let loadedId = $state<string | null>(null);
  $effect(() => {
    if (project.id === loadedId) return;
    loadedId = project.id;
    void loadDatasets();
    void loadJobs();
    void checkEndpoint();
  });

  // ---- Polling lifecycle --------------------------------------------------
  // A single interval drives both dataset-validation and job-progress polls.
  let poller: ReturnType<typeof setInterval> | null = null;

  const hasPendingDataset = $derived(
    datasets.some((d) => d.status === "uploaded" || d.status === "validating"),
  );
  const activeJob = $derived(
    jobs.find((j) => j.status === "queued" || j.status === "running") ?? null,
  );

  $effect(() => {
    const needPoll = hasPendingDataset || activeJob !== null;
    if (needPoll && poller === null) {
      poller = setInterval(() => {
        if (hasPendingDataset) void refreshPendingDatasets();
        if (activeJob) void refreshActiveJob(activeJob.id);
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

  async function loadJobs() {
    jobsLoading = true;
    jobsLoadErr = false;
    try {
      jobs = await api.listJobs(project.id);
    } catch (e) {
      jobsLoadErr = true;
      reportErr(e, "Could not load jobs.");
    } finally {
      jobsLoading = false;
    }
  }

  async function refreshActiveJob(jid: string) {
    try {
      const fresh = await api.getJob(project.id, jid);
      jobs = jobs.map((x) => (x.id === fresh.id ? fresh : x));
    } catch {
      // Transient poll error — swallow; the next tick retries.
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

  // ---- Start a training job ----------------------------------------------
  const validDatasets = $derived(datasets.filter((d) => d.status === "valid"));
  let selectedDatasetId = $state<string>("");
  let starting = $state(false);

  // Keep the selection pointing at a still-valid dataset.
  $effect(() => {
    if (selectedDatasetId && !validDatasets.some((d) => d.id === selectedDatasetId)) {
      selectedDatasetId = "";
    }
    if (!selectedDatasetId && validDatasets.length > 0) {
      selectedDatasetId = validDatasets[0].id;
    }
  });

  const canStart = $derived(
    selectedDatasetId !== "" && activeJob === null && !starting,
  );

  async function startJob() {
    if (!canStart) return;
    starting = true;
    try {
      const job = await api.createJob(project.id, selectedDatasetId);
      jobs = [job, ...jobs];
      toastSuccess("Fine-tune job queued.");
    } catch (e) {
      reportErr(e, "Could not start the job.");
    } finally {
      starting = false;
    }
  }

  // ---- Eval gate ----------------------------------------------------------
  // The latest finished job that produced an eval score is the one whose verdict
  // governs whether we may serve.
  const gateJob = $derived(
    jobs.find(
      (j) =>
        (j.status === "succeeded" || j.status === "failed") &&
        j.eval_score !== null,
    ) ?? null,
  );
  const servableJob = $derived(
    jobs.find((j) => j.status === "succeeded" && j.eval_passed === true) ?? null,
  );

  // ---- Create endpoint ----------------------------------------------------
  let creatingEndpoint = $state(false);
  const canCreateEndpoint = $derived(
    servableJob !== null && !endpointExists && !creatingEndpoint,
  );

  async function createEndpoint() {
    if (!canCreateEndpoint) return;
    creatingEndpoint = true;
    try {
      await api.createEndpoint(project.id);
      endpointExists = true;
      toastSuccess("Endpoint created — find the slug and keys under “Endpoint & keys”.");
    } catch (e) {
      reportErr(e, "Could not create the endpoint.");
    } finally {
      creatingEndpoint = false;
    }
  }

  // ---- helpers ------------------------------------------------------------
  function pct(p: number) {
    return Math.round(Math.max(0, Math.min(1, p)) * 100);
  }
  function score2(n: number) {
    return n.toFixed(2);
  }
  function fmtDate(iso: string) {
    const d = new Date(iso);
    return isNaN(d.getTime()) ? iso : d.toLocaleString();
  }
  function shortId(id: string) {
    return id.length > 8 ? id.slice(0, 8) : id;
  }
</script>

<div class="stack">
  <!-- What's an adapter? — explain the jargon inline. -->
  <aside class="card explainer">
    <h2 style="margin: 0 0 6px;">Change how your model behaves</h2>
    <p class="muted" style="margin: 0;">
      Fine-tuning teaches the model a style, format, or skill from examples. The
      result is a small <strong>adapter</strong> — a lightweight patch layered on
      the base model, rather than a whole new model. It only goes live after it
      passes the <strong>eval gate</strong> (an automatic quality check, below).
    </p>
    <p class="muted" style="margin: 8px 0 0;">
      The path is three steps: <strong>1</strong> give it a dataset, <strong>2</strong>
      run the fine-tune job, <strong>3</strong> serve it once the check passes.
    </p>
  </aside>

  <!-- ============================ DATASET ============================ -->
  <div class="card">
    <div class="row between" style="margin-bottom: 12px;">
      <h2 style="margin: 0;">1 · Dataset</h2>
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

    <p class="muted" style="margin: 0 0 12px;">
      Provide instruction examples as a <span class="mono">.jsonl</span> file, or
      generate Q/A pairs automatically from documents you've already indexed.
    </p>

    <!-- Collapsible: what a dataset is, its exact format, and where to get one. -->
    <details class="help" style="margin-bottom: 14px;">
      <summary>What a dataset is, the format, and where to get one</summary>
      <div class="help-body">
        <h4>What a dataset is</h4>
        <p style="margin: 0;">
          A set of example <strong>prompt → response</strong> pairs that show the
          model the behavior you want — a tone, a format, a way of answering. It
          learns the <em>pattern</em>, not the facts; for facts use the Knowledge
          (RAG) path instead.
        </p>

        <h4>Format — JSONL (one JSON object per line)</h4>
        <pre class="code" style="margin: 4px 0 8px; white-space: pre-wrap;">{`{"prompt": "Summarize this support ticket", "response": "Customer can't log in after the 2.3 update; cause is the expired token cache.", "system": "You are a concise support assistant."}`}</pre>
        <ul>
          <li><code>prompt</code> <strong>(required)</strong> — the instruction or question.</li>
          <li><code>response</code> <strong>(required)</strong> — the ideal answer.</li>
          <li><code>system</code> (optional) — persona / context for the turn.</li>
          <li><code>metadata</code> (optional) — free-form (source, quality score…).</li>
        </ul>

        <h4>Requirements</h4>
        <ul>
          <li>At least <strong>{MIN_SAMPLES} valid rows</strong>; aim for 50–500+ for a real effect.</li>
          <li>Every <code>prompt</code> and <code>response</code> non-empty; keep the style consistent across rows.</li>
          <li>The last ~20% is held out to score the result and is never trained on (the eval gate below).</li>
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
          bootstrap a dataset. Review the result before training on it.
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
          </tr>
        </thead>
        <tbody>
          {#each datasets as d (d.id)}
            <tr>
              <td class="mono">{d.name}</td>
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
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>

  <!-- ============================ JOB ============================ -->
  <div class="card">
    <div class="row between" style="margin-bottom: 12px;">
      <h2 style="margin: 0;">2 · Fine-tune job</h2>
    </div>

    <div class="row wrap" style="gap: 12px; align-items: flex-end; margin-bottom: 14px;">
      <div class="field" style="margin: 0; min-width: 240px;">
        <label for="job-dataset">Dataset</label>
        <select id="job-dataset" bind:value={selectedDatasetId} disabled={validDatasets.length === 0 || activeJob !== null}>
          {#if validDatasets.length === 0}
            <option value="">No valid dataset yet</option>
          {:else}
            {#each validDatasets as d (d.id)}
              <option value={d.id}>{d.name} ({d.num_samples} samples)</option>
            {/each}
          {/if}
        </select>
      </div>
      <button class="primary" onclick={startJob} disabled={!canStart}>
        {#if starting}<span class="spinner"></span>{/if}
        Start
      </button>
      {#if activeJob}
        <small class="muted">A job is already running — wait for it to finish.</small>
      {:else if validDatasets.length === 0}
        <small class="muted">You need a <strong>valid</strong> dataset before you can start.</small>
      {/if}
    </div>

    {#if jobsLoading}
      <div class="row" style="gap: 8px;">
        <span class="spinner"></span><small>Loading jobs…</small>
      </div>
    {:else if jobsLoadErr}
      <div class="empty">
        <p>Could not load jobs.</p>
        <button class="ghost sm" onclick={loadJobs}>Retry</button>
      </div>
    {:else if jobs.length === 0}
      <div class="empty">No jobs yet.</div>
    {:else}
      <div class="stack">
        {#each jobs as j (j.id)}
          <div class="muted-box job">
            <div class="row between">
              <div class="row" style="gap: 8px;">
                <span class="mono muted">#{shortId(j.id)}</span>
                <StatusBadge status={j.status} />
              </div>
              <small class="muted">{fmtDate(j.created_at)}</small>
            </div>

            {#if j.status === "queued" || j.status === "running"}
              <div class="progress" style="margin-top: 10px;">
                <div style={`width: ${pct(j.progress)}%`}></div>
              </div>
              <small class="muted">{pct(j.progress)}%</small>
            {/if}

            {#if j.error_message && j.status === "failed"}
              <div class="ds-err mono" style="margin-top: 10px;">{j.error_message}</div>
            {/if}

            {#if j.logs}
              <pre class="code logs">{j.logs}</pre>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  </div>

  <!-- ============================ EVAL GATE ============================ -->
  {#if gateJob}
    {@const passed = gateJob.eval_passed === true && gateJob.status === "succeeded"}
    <div class="card gate {passed ? 'gate-pass' : 'gate-fail'}">
      <div class="row between" style="margin-bottom: 10px;">
        <h2 style="margin: 0;">Eval gate</h2>
        {#if passed}
          <span class="badge green verdict">PASSED</span>
        {:else}
          <span class="badge red verdict">BLOCKED</span>
        {/if}
      </div>

      <div class="row wrap" style="gap: 28px; align-items: baseline;">
        <div>
          <div class="muted">Score</div>
          <div class="bignum">{gateJob.eval_score !== null ? score2(gateJob.eval_score) : "—"}</div>
        </div>
        <div>
          <div class="muted">Threshold to serve</div>
          <div class="bignum threshold">{score2(EVAL_THRESHOLD)}</div>
        </div>
      </div>

      {#if passed}
        <p style="margin: 14px 0 0;">
          This adapter scored at or above the threshold and is cleared to serve.
        </p>
      {:else}
        <p class="blocked-reason" style="margin: 14px 0 0;">
          {#if gateJob.eval_score !== null}
            Scored {score2(gateJob.eval_score)} &lt; {score2(EVAL_THRESHOLD)} — cannot serve.
          {:else}
            This run did not pass the eval gate — cannot serve.
          {/if}
          An unverified fine-tune is never served; fix the dataset or rerun, then start a new job.
        </p>
      {/if}
    </div>
  {/if}

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
      <p class="muted" style="margin: 0 0 12px;">
        Creating an endpoint exposes this model over the OpenAI-compatible API.
        Available once a job has <strong>passed</strong> the eval gate.
      </p>
      <button class="primary" onclick={createEndpoint} disabled={!canCreateEndpoint}>
        {#if creatingEndpoint}<span class="spinner"></span>{/if}
        Create endpoint
      </button>
      {#if !servableJob}
        <small class="muted" style="display: block; margin-top: 8px;">
          No eval-passed job yet — run a fine-tune and clear the gate first.
        </small>
      {/if}
    {/if}
  </div>
</div>

<style>
  .explainer { background: var(--panel-2); }

  .ds-err {
    margin-top: 6px;
    color: var(--red);
    font-size: 12px;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .job { padding: 12px 14px; }
  .logs {
    margin-top: 10px;
    max-height: 220px;
    overflow: auto;
    white-space: pre;
  }

  .gate { border-width: 2px; }
  .gate-pass { border-color: var(--green); background: var(--green-weak); }
  .gate-fail { border-color: var(--red); background: var(--red-weak); }
  .verdict { font-size: 14px; padding: 5px 14px; letter-spacing: .06em; }
  .bignum { font-size: 34px; font-weight: 700; font-family: var(--mono); line-height: 1.1; }
  .bignum.threshold { color: var(--muted); }
  .blocked-reason { color: var(--red); }

  /* Center inline spinners inside buttons (matches Projects.svelte). */
  button :global(.spinner) { margin-right: 6px; vertical-align: middle; }
</style>
