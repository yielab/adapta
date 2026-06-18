<script lang="ts">
  import { api, ApiError } from "../lib/api";
  import { session } from "../lib/session";
  import { navigate } from "../lib/router";
  import { toastError } from "../lib/toast";
  import type { BaseModelInfo, Project, ProjectType } from "../lib/types";

  import Modal from "../components/Modal.svelte";
  import ConfirmDialog from "../components/ConfirmDialog.svelte";
  import StatusBadge from "../components/StatusBadge.svelte";

  let baseModels = $state<BaseModelInfo[]>([]);
  $effect(() => {
    void api
      .listModels()
      .then((m) => {
        baseModels = m;
        if (!baseModel && m.length > 0) baseModel = defaultBase(m);
      })
      .catch(() => {});
  });

  function defaultBase(models: BaseModelInfo[]): string {
    return models.find((m) => m.name === "qwen2.5-3b-instruct")?.name ?? models[0].name;
  }

  // ── C1.3: selected model info for the detail panel ────────────────────────
  const selectedModel = $derived(baseModels.find((m) => m.name === baseModel) ?? null);

  const BEST_FOR_LABEL: Record<string, string> = {
    knowledge: "Knowledge",
    behavior: "Behavior",
    code: "Code",
    vision: "Vision",
  };

  let projects = $state<Project[]>([]);
  let loading = $state(false);
  let loadErr = $state(false);
  let loadedTeamId = $state<string | null>(null);

  const activeTeam = $derived($session.activeTeam);

  $effect(() => {
    const team = activeTeam;
    if (!team) {
      projects = [];
      loadedTeamId = null;
      return;
    }
    if (team.id === loadedTeamId) return;
    loadedTeamId = team.id;
    void load(team.id);
  });

  async function load(teamId: string) {
    loading = true;
    loadErr = false;
    try {
      projects = await api.listProjects(teamId);
    } catch (e) {
      loadErr = true;
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else toastError("Could not load projects.");
    } finally {
      loading = false;
    }
  }

  // ── C2.2: stage display helpers ───────────────────────────────────────────
  function stageLabel(stage: string | undefined): string {
    switch (stage) {
      case "live":            return "Live";
      case "ready_to_serve":  return "Ready to serve";
      case "training":        return "Training";
      case "gate_blocked":    return "Gate blocked";
      case "indexing":        return "Indexing";
      case "awaiting_data":   return "Awaiting data";
      default:                return "Setting up";
    }
  }

  function stageHint(p: Project): string {
    const s = p.summary;
    const stage = s?.stage;
    switch (stage) {
      case "live":
        if (s?.usage_7d?.requests) return `${s.usage_7d.requests.toLocaleString()} requests this week`;
        return "Endpoint is active";
      case "ready_to_serve":  return "Create an endpoint to start serving";
      case "training": {
        const pct = p.status === "training" ? "" : "";
        return `Training in progress${pct}`;
      }
      case "gate_blocked": {
        const score = s?.jobs?.last_eval_score;
        return score != null ? `Eval score ${score.toFixed(3)} — below gate threshold` : "Eval gate not passed";
      }
      case "indexing":        return "Documents are being indexed";
      case "awaiting_data":
        if (p.type === "rag")      return "Upload documents to index";
        if (s?.datasets?.valid ?? 0 > 0) return "Dataset ready — start training";
        return "Upload a dataset to train";
      default:                return "";
    }
  }

  function stageCls(stage: string | undefined): string {
    switch (stage) {
      case "live":            return "stage-live";
      case "ready_to_serve":  return "stage-ready";
      case "training":        return "stage-training";
      case "gate_blocked":    return "stage-blocked";
      case "indexing":        return "stage-indexing";
      default:                return "stage-waiting";
    }
  }

  // ---- Create flow --------------------------------------------------------
  let showCreate = $state(false);
  let createType = $state<ProjectType | null>(null);
  let name = $state("");
  let baseModel = $state("");
  let description = $state("");
  let creating = $state(false);

  const createValid = $derived(createType !== null && name.trim() !== "" && baseModel !== "");

  function openCreate() {
    createType = null;
    name = "";
    baseModel = baseModels.length > 0 ? defaultBase(baseModels) : "";
    description = "";
    showCreate = true;
  }

  function closeCreate() {
    if (creating) return;
    showCreate = false;
  }

  async function submitCreate() {
    if (!createValid || creating) return;
    const team = activeTeam;
    if (!team) return;
    creating = true;
    try {
      const project = await api.createProject({
        name: name.trim(),
        type: createType as ProjectType,
        base_model: baseModel,
        description: description.trim() || undefined,
        team_id: team.id,
      });
      showCreate = false;
      navigate("/projects/" + project.id);
    } catch (e) {
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else toastError("Could not create the project.");
    } finally {
      creating = false;
    }
  }

  // ---- Delete flow --------------------------------------------------------
  let deleteTarget = $state<Project | null>(null);
  let deleting = $state(false);

  async function confirmDelete() {
    const target = deleteTarget;
    if (!target || deleting) return;
    deleting = true;
    try {
      await api.deleteProject(target.id);
      deleteTarget = null;
      if (loadedTeamId) await load(loadedTeamId);
    } catch (e) {
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else toastError("Could not delete the project.");
    } finally {
      deleting = false;
    }
  }

  function typeLabel(t: ProjectType) {
    return t === "rag" ? "Knowledge" : "Behavior";
  }

  function fmtDate(iso: string) {
    const d = new Date(iso);
    return isNaN(d.getTime()) ? iso : d.toLocaleDateString();
  }
</script>

<div class="row between" style="margin-bottom: 18px;">
  <div>
    <h1>Projects</h1>
    <p class="muted" style="margin: 0;">
      {#if activeTeam}Team <span class="mono">{activeTeam.name}</span>{/if}
    </p>
  </div>
  <button class="primary" onclick={openCreate} disabled={!activeTeam}>New project</button>
</div>

{#if loading}
  <div class="card">
    <span class="row" style="gap: 8px;"><span class="spinner"></span><small>Loading projects…</small></span>
  </div>
{:else if loadErr}
  <div class="card empty">
    <p>Could not load projects.</p>
    {#if loadedTeamId}
      <button class="ghost sm" onclick={() => load(loadedTeamId!)}>Retry</button>
    {/if}
  </div>
{:else if projects.length === 0}
  <div class="card empty">
    <p>No projects yet — create one to give a model knowledge or change its behavior.</p>
    <button class="primary" onclick={openCreate} disabled={!activeTeam}>New project</button>
  </div>
{:else}
  <div class="grid">
    {#each projects as p (p.id)}
      {@const stage = p.summary?.stage}
      {@const hint = stageHint(p)}
      <div class="card project {p.type}">
        <button class="open" onclick={() => navigate("/projects/" + p.id)} aria-label={"Open " + p.name}>
          <div class="row between" style="margin-bottom: 8px;">
            <span class="name">{p.name}</span>
            <span class="badge {p.type === 'rag' ? 'knowledge' : 'behavior'}">{typeLabel(p.type)}</span>
          </div>
          <!-- C2.2: stage as primary status line -->
          <div class="stage-row {stageCls(stage)}">
            <span class="stage-dot"></span>
            <span class="stage-label">{stageLabel(stage)}</span>
          </div>
          {#if hint}
            <p class="hint">{hint}</p>
          {/if}
          <!-- Compact counts -->
          {#if p.summary}
            {@const s = p.summary}
            <div class="counts">
              {#if s.files.total > 0}
                <span>{s.files.indexed}/{s.files.total} docs indexed</span>
              {/if}
              {#if p.type === "finetune" && s.datasets.total > 0}
                <span>{s.datasets.valid}/{s.datasets.total} datasets valid</span>
              {/if}
              {#if s.keys_active > 0}
                <span>{s.keys_active} key{s.keys_active !== 1 ? "s" : ""}</span>
              {/if}
            </div>
          {/if}
          <small class="muted" style="margin-top: 6px; display: block;">
            <span class="mono">{p.base_model}</span> · Created {fmtDate(p.created_at)}
          </small>
        </button>
        <div class="row between" style="margin-top: 12px;">
          <button class="ghost sm" onclick={() => navigate("/projects/" + p.id)}>Open</button>
          <button class="danger sm" onclick={() => (deleteTarget = p)}>Delete</button>
        </div>
      </div>
    {/each}
  </div>
{/if}

{#if showCreate}
  <Modal title="New project" onclose={closeCreate}>
    <div class="stack">
      <h2 style="margin: 0;">How do you want to specialize your model?</h2>
      <div class="choice-grid">
        <button
          class="choice knowledge"
          class:selected={createType === "rag"}
          aria-pressed={createType === "rag"}
          onclick={() => (createType = "rag")}
        >
          <div class="t">Give it knowledge</div>
          <div class="d">Answers grounded in your documents, with citations. The weights don't change.</div>
        </button>
        <button
          class="choice behavior"
          class:selected={createType === "finetune"}
          aria-pressed={createType === "finetune"}
          onclick={() => (createType = "finetune")}
        >
          <div class="t">Change how it behaves</div>
          <div class="d">Teach it a style, format, or skill by fine-tuning.</div>
        </button>
      </div>

      <form onsubmit={(e) => { e.preventDefault(); submitCreate(); }}>
        <div class="field">
          <label for="proj-name">Name</label>
          <input id="proj-name" type="text" bind:value={name} disabled={creating} />
        </div>

        <!-- C1.3: Informative base-model picker -->
        <div class="field">
          <label for="proj-base">
            Base model
            <a href="#/models" class="compare-link" tabindex="-1">Compare models →</a>
          </label>
          <select id="proj-base" bind:value={baseModel} disabled={creating || baseModels.length === 0}>
            {#if baseModels.length === 0}
              <option value="">Could not load the model catalog — reload the page</option>
            {:else}
              {#each baseModels as m (m.name)}
                <option value={m.name} disabled={!m.available}>
                  {m.name}{m.modality === "vision" ? " — vision" : ""}{!m.available ? " (not downloaded)" : ""}
                </option>
              {/each}
            {/if}
          </select>

          <!-- Live detail panel for the selected model -->
          {#if selectedModel}
            <div class="model-detail">
              {#if !selectedModel.available}
                <div class="avail-warn">
                  GGUF not on this server — <a href="#/models">see Models page</a> for download instructions.
                </div>
              {:else}
                <span class="avail-ok">Ready</span>
              {/if}
              {#if selectedModel.use_case}
                <p class="use-case-line">{selectedModel.use_case}</p>
              {/if}
              <div class="model-meta">
                {#if selectedModel.best_for?.length > 0}
                  <span class="meta-group">Best for:
                    {#each selectedModel.best_for as bf}
                      <span class="chip">{BEST_FOR_LABEL[bf] ?? bf}</span>
                    {/each}
                  </span>
                {/if}
                {#if selectedModel.train_vram_gb}
                  <span class="meta-item">~{selectedModel.train_vram_gb} GB VRAM to train</span>
                {/if}
                {#if selectedModel.serve_ram_gb}
                  <span class="meta-item">{selectedModel.serve_ram_gb} GB RAM to serve</span>
                {/if}
              </div>
              {#if selectedModel.modality === "vision"}
                <small class="muted">
                  Vision base: fine-tune on image + text examples (zip bundle) and send images to the endpoint.
                  Image <em>understanding</em> only — never generation.
                </small>
              {/if}
            </div>
          {/if}
        </div>

        <div class="field">
          <label for="proj-desc">Description <span class="muted">(optional)</span></label>
          <textarea id="proj-desc" rows="2" bind:value={description} disabled={creating}></textarea>
        </div>
        <div class="row between" style="margin-top: 6px;">
          <button type="button" class="ghost" onclick={closeCreate} disabled={creating}>Cancel</button>
          <button type="submit" class="primary" disabled={!createValid || creating || (selectedModel != null && !selectedModel.available)}>
            {#if creating}<span class="spinner"></span>{/if}
            Create project
          </button>
        </div>
      </form>
    </div>
  </Modal>
{/if}

{#if deleteTarget}
  <ConfirmDialog
    title="Delete project?"
    message={`"${deleteTarget.name}" and all its data will be permanently removed. This cannot be undone.`}
    confirmLabel="Delete project"
    busy={deleting}
    onconfirm={confirmDelete}
    oncancel={() => { if (!deleting) deleteTarget = null; }}
  />
{/if}

<style>
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 14px;
  }
  .project { padding: 16px; }
  /* mode left-border stripe — the visual signature of knowledge vs behavior */
  .project.rag      { border-left: 3px solid var(--knowledge); }
  .project.finetune { border-left: 3px solid var(--behavior); }
  .open {
    display: block;
    width: 100%;
    text-align: left;
    background: none;
    border: none;
    padding: 0;
    border-radius: 0;
  }
  .open:hover:not(:disabled) { border-color: transparent; }
  .name { font-size: 15px; font-weight: 600; }

  /* Stage row (C2.2) — colors aligned to brand tokens */
  .stage-row {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 4px;
  }
  .stage-dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
    background: currentColor;
  }
  .stage-label { font-size: 12px; font-weight: 600; }
  .stage-live      { color: var(--green); }
  .stage-ready     { color: var(--brand); }
  .stage-training  { color: var(--behavior); }
  .stage-blocked   { color: var(--red); }
  .stage-indexing  { color: var(--amber); }
  .stage-waiting   { color: var(--muted); }

  .hint {
    font-size: 11.5px;
    color: var(--muted);
    margin: 2px 0 6px;
  }
  .counts {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin: 4px 0;
  }
  .counts span {
    font-size: 11px;
    color: var(--muted);
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 1px 6px;
  }

  /* C1.3: model detail panel */
  .compare-link {
    font-size: 11px;
    font-weight: 400;
    margin-left: 8px;
    color: var(--accent);
    text-decoration: none;
  }
  .model-detail {
    margin-top: 8px;
    padding: 10px 12px;
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 12.5px;
  }
  .avail-ok {
    display: inline-block;
    background: var(--green-weak);
    color: var(--green);
    border: 1px solid var(--green);
    border-radius: 4px;
    padding: 1px 7px;
    font-size: 11px;
    font-weight: 700;
    margin-bottom: 6px;
  }
  .avail-warn {
    background: var(--red-weak);
    color: var(--red);
    border: 1px solid var(--red);
    border-radius: 4px;
    padding: 5px 8px;
    font-size: 11.5px;
    margin-bottom: 6px;
  }
  .use-case-line { margin: 0 0 6px; color: var(--text); }
  .model-meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }
  .meta-group { display: flex; align-items: center; gap: 4px; color: var(--muted); }
  .meta-item { color: var(--muted); }
  .chip {
    display: inline-block;
    background: var(--brand-weak);
    color: var(--brand);
    border-radius: 4px;
    padding: 1px 6px;
    font-size: 11px;
    font-weight: 600;
  }

  button.primary :global(.spinner) { margin-right: 6px; vertical-align: middle; }
  @media (max-width: 560px) {
    .grid { grid-template-columns: 1fr; }
  }
</style>
