<script lang="ts">
  import type { Project, ProjectSummary } from "../lib/types";

  let {
    project,
    onGoTab,
  }: {
    project: Project;
    onGoTab: (tab: "setup" | "endpoint" | "playground" | "usage") => void;
  } = $props();

  const s = $derived(project.summary);

  // Pipeline steps common to both project types
  type StepStatus = "done" | "partial" | "pending" | "blocked";
  interface PipelineStep {
    label: string;
    status: StepStatus;
    detail: string;
    action: string | null;
    tab: "setup" | "endpoint" | "playground" | "usage" | null;
  }

  const ragSteps = $derived<PipelineStep[]>([
    {
      label: "1 · Upload documents",
      status: !s ? "pending"
            : s.files.indexed > 0 ? "done"
            : s.files.total > 0 ? "partial"
            : "pending",
      detail: !s ? "" : s.files.total === 0 ? "No documents yet."
            : `${s.files.indexed} of ${s.files.total} indexed, ${s.files.chunks} chunks`,
      action: s && s.files.indexed === 0 ? "Upload documents →" : null,
      tab: "setup",
    },
    {
      label: "2 · Create endpoint",
      status: !s ? "pending"
            : s.endpoint.exists ? "done"
            : s.files.indexed > 0 ? "partial"
            : "pending",
      detail: !s ? "" : s.endpoint.exists
            ? `Endpoint active — slug: ${s.endpoint.slug}`
            : s.files.indexed > 0 ? "Ready — create an endpoint to serve answers."
            : "Index at least one document first.",
      action: !s?.endpoint.exists && s && s.files.indexed > 0 ? "Create endpoint →" : null,
      tab: "endpoint",
    },
    {
      label: "3 · Generate API keys",
      status: !s ? "pending"
            : s.keys_active > 0 ? "done"
            : s.endpoint.exists ? "partial"
            : "pending",
      detail: !s ? "" : s.keys_active > 0
            ? `${s.keys_active} active key${s.keys_active > 1 ? "s" : ""}`
            : s.endpoint.exists ? "Generate a key to start calling the API."
            : "Create an endpoint first.",
      action: s?.endpoint.exists && s.keys_active === 0 ? "Generate key →" : null,
      tab: "endpoint",
    },
  ]);

  const finetuneSteps = $derived<PipelineStep[]>([
    {
      label: "1 · Upload dataset",
      status: !s ? "pending"
            : s.datasets.valid > 0 ? "done"
            : s.datasets.total > 0 ? "partial"
            : "pending",
      detail: !s ? "" : s.datasets.total === 0 ? "No dataset yet."
            : `${s.datasets.valid} of ${s.datasets.total} valid`,
      action: s && s.datasets.valid === 0 ? "Upload dataset →" : null,
      tab: "setup",
    },
    {
      label: "2 · Train the model",
      status: !s ? "pending"
            : s.jobs.last_status === "succeeded" && s.jobs.gate_passed ? "done"
            : s.jobs.running > 0 ? "partial"
            : s.jobs.gate_passed === false ? "blocked"
            : s.jobs.total > 0 ? "partial"
            : "pending",
      detail: !s ? "" : s.jobs.running > 0 ? "Training job running…"
            : s.jobs.last_status === "succeeded" && s.jobs.gate_passed
              ? `Passed eval gate — score ${s.jobs.last_eval_score?.toFixed(2) ?? "–"}`
            : s.jobs.gate_passed === false
              ? `Gate blocked — score ${s.jobs.last_eval_score?.toFixed(2) ?? "–"} (below threshold)`
            : s.datasets.valid > 0 ? "Dataset ready — start a training job."
            : "Upload a valid dataset first.",
      action: s?.datasets.valid && s.jobs.running === 0 && s.jobs.last_status !== "succeeded"
            ? "Start training →" : null,
      tab: "setup",
    },
    {
      label: "3 · Create endpoint",
      status: !s ? "pending"
            : s.endpoint.exists ? "done"
            : s.jobs.gate_passed ? "partial"
            : "pending",
      detail: !s ? "" : s.endpoint.exists
            ? `Endpoint active — slug: ${s.endpoint.slug}`
            : s.jobs.gate_passed ? "Training passed the eval gate — create an endpoint."
            : "Training must pass the eval gate first.",
      action: !s?.endpoint.exists && s?.jobs.gate_passed ? "Create endpoint →" : null,
      tab: "endpoint",
    },
    {
      label: "4 · Generate API keys",
      status: !s ? "pending"
            : s.keys_active > 0 ? "done"
            : s.endpoint.exists ? "partial"
            : "pending",
      detail: !s ? "" : s.keys_active > 0
            ? `${s.keys_active} active key${s.keys_active > 1 ? "s" : ""}`
            : s.endpoint.exists ? "Generate a key to start calling the API."
            : "Create an endpoint first.",
      action: s?.endpoint.exists && s.keys_active === 0 ? "Generate key →" : null,
      tab: "endpoint",
    },
  ]);

  const steps = $derived(project.type === "rag" ? ragSteps : finetuneSteps);

  const STEP_COLOR: Record<StepStatus, string> = {
    done:    "step-done",
    partial: "step-partial",
    pending: "step-pending",
    blocked: "step-blocked",
  };
  const STEP_ICON: Record<StepStatus, string> = {
    done:    "✓",
    partial: "◑",
    pending: "○",
    blocked: "✕",
  };
</script>

<div class="overview">
  <!-- Pipeline checklist -->
  <section class="section">
    <h2 class="section-title">Pipeline</h2>
    <div class="pipeline">
      {#each steps as step}
        <div class="pipeline-step {STEP_COLOR[step.status]}">
          <span class="step-icon">{STEP_ICON[step.status]}</span>
          <div class="step-body">
            <div class="step-label">{step.label}</div>
            {#if step.detail}
              <div class="step-detail">{step.detail}</div>
            {/if}
            {#if step.action && step.tab}
              <button class="step-cta" onclick={() => step.tab && onGoTab(step.tab)}>
                {step.action}
              </button>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  </section>

  <!-- Endpoint + usage snapshot -->
  {#if s?.endpoint.exists}
    <section class="section">
      <h2 class="section-title">Endpoint</h2>
      <div class="snapshot-card">
        <div class="snapshot-row">
          <span class="snap-label">Slug</span>
          <code>{s.endpoint.slug}</code>
        </div>
        <div class="snapshot-row">
          <span class="snap-label">Status</span>
          <span>{s.endpoint.status}</span>
        </div>
        <div class="snapshot-row">
          <span class="snap-label">Active keys</span>
          <span>{s.keys_active}</span>
        </div>
        {#if s.usage_7d.requests > 0}
          <div class="snapshot-row">
            <span class="snap-label">Last 7 days</span>
            <span>{s.usage_7d.requests} requests · {(s.usage_7d.total_tokens / 1000).toFixed(1)}k tokens</span>
          </div>
        {/if}
        <div class="snapshot-actions">
          <button class="ghost sm" onclick={() => onGoTab("endpoint")}>Keys &amp; snippet →</button>
          <button class="ghost sm" onclick={() => onGoTab("playground")}>Playground →</button>
          <button class="ghost sm" onclick={() => onGoTab("usage")}>Usage →</button>
        </div>
      </div>
    </section>
  {/if}

  <!-- Docs / datasets quick summary -->
  {#if s && (s.files.total > 0 || s.datasets.total > 0)}
    <section class="section">
      <h2 class="section-title">Data</h2>
      <div class="data-chips">
        {#if s.files.total > 0}
          <span class="data-chip">
            <strong>{s.files.indexed}</strong>/{s.files.total} documents indexed
            {#if s.files.chunks > 0} · {s.files.chunks} chunks{/if}
          </span>
        {/if}
        {#if s.datasets.total > 0}
          <span class="data-chip">
            <strong>{s.datasets.valid}</strong>/{s.datasets.total} datasets valid
          </span>
        {/if}
      </div>
    </section>
  {/if}
</div>

<style>
  .overview { display: flex; flex-direction: column; gap: 1.5rem; padding-top: .75rem; }

  .section-title { font-size: .8rem; text-transform: uppercase; letter-spacing: .07em; color: var(--muted); margin: 0 0 .65rem; font-weight: 600; }

  /* Pipeline */
  .pipeline { display: flex; flex-direction: column; gap: .5rem; }
  .pipeline-step {
    display: flex; align-items: flex-start; gap: .75rem;
    padding: .65rem .85rem; border-radius: 7px; border: 1px solid var(--border, #2d3148);
  }
  .step-icon { font-size: 1rem; flex-shrink: 0; width: 1.1rem; text-align: center; margin-top: .05rem; }
  .step-body { display: flex; flex-direction: column; gap: .2rem; flex: 1; }
  .step-label { font-weight: 600; font-size: .875rem; }
  .step-detail { font-size: .8rem; color: var(--muted); }
  .step-cta {
    margin-top: .2rem; font-size: .78rem;
    background: none; border: none; padding: 0;
    color: var(--accent, #4a7cf7); cursor: pointer; text-align: left;
    text-decoration: underline;
  }
  .step-cta:hover { opacity: .8; }

  .step-done    { background: #0f2e1a18; }
  .step-done .step-icon { color: #4caf82; }
  .step-partial { background: #1e3a5f18; }
  .step-partial .step-icon { color: #7ec8f5; }
  .step-pending { background: transparent; }
  .step-pending .step-icon { color: var(--muted); }
  .step-blocked { background: #3d151518; border-color: #7f282855; }
  .step-blocked .step-icon { color: #f98080; }

  /* Snapshot */
  .snapshot-card {
    background: var(--surface-1, #161720);
    border: 1px solid var(--border, #2d3148);
    border-radius: 8px; padding: .85rem 1rem;
    display: flex; flex-direction: column; gap: .45rem;
  }
  .snapshot-row { display: flex; align-items: center; gap: .75rem; }
  .snap-label { font-size: .72rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); width: 80px; flex-shrink: 0; }
  .snapshot-row code { font-size: .8rem; }
  .snapshot-actions { display: flex; gap: .5rem; flex-wrap: wrap; margin-top: .3rem; }

  /* Data chips */
  .data-chips { display: flex; flex-wrap: wrap; gap: .5rem; }
  .data-chip {
    font-size: .8rem; padding: .35rem .65rem; border-radius: 5px;
    background: var(--panel-2, #1e2030); border: 1px solid var(--border, #2d3148);
    color: var(--muted);
  }
  .data-chip strong { color: var(--text); }
</style>
