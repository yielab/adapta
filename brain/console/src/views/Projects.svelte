<script lang="ts">
  import { api, ApiError } from "../lib/api";
  import { session } from "../lib/session";
  import { navigate } from "../lib/router";
  import { toastError } from "../lib/toast";
  import type { Project, ProjectType } from "../lib/types";

  import Modal from "../components/Modal.svelte";
  import ConfirmDialog from "../components/ConfirmDialog.svelte";
  import StatusBadge from "../components/StatusBadge.svelte";

  // Curated Qwen2.5 list until §A3.3's base-model catalog lands; values are the
  // operator-facing strings the API expects verbatim.
  const BASE_MODELS = [
    "qwen2.5-3b-instruct",
    "qwen2.5-7b-instruct",
    "qwen2.5-coder-3b",
  ];

  let projects = $state<Project[]>([]);
  let loading = $state(false);
  let loadErr = $state(false);

  // Track which team we've loaded for so the $effect only re-fetches on change.
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

  // ---- Create flow --------------------------------------------------------
  let showCreate = $state(false);
  let createType = $state<ProjectType | null>(null);
  let name = $state("");
  let baseModel = $state(BASE_MODELS[0]);
  let description = $state("");
  let creating = $state(false);

  const createValid = $derived(createType !== null && name.trim() !== "" && baseModel !== "");

  function openCreate() {
    createType = null;
    name = "";
    baseModel = BASE_MODELS[0];
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
      <div class="card project">
        <button class="open" onclick={() => navigate("/projects/" + p.id)} aria-label={"Open " + p.name}>
          <div class="row between" style="margin-bottom: 8px;">
            <span class="name">{p.name}</span>
            <span class="badge {p.type === 'rag' ? 'blue' : 'amber'}">{typeLabel(p.type)}</span>
          </div>
          <div class="row" style="gap: 8px; margin-bottom: 10px;">
            <StatusBadge status={p.status} />
            <span class="mono muted">{p.base_model}</span>
          </div>
          <small class="muted">Created {fmtDate(p.created_at)}</small>
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
          class="choice"
          class:selected={createType === "rag"}
          aria-pressed={createType === "rag"}
          onclick={() => (createType = "rag")}
        >
          <div class="t">Give it knowledge</div>
          <div class="d">Answers grounded in your documents, with citations. The weights don't change.</div>
        </button>
        <button
          class="choice"
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
        <div class="field">
          <label for="proj-base">Base model</label>
          <select id="proj-base" bind:value={baseModel} disabled={creating}>
            {#each BASE_MODELS as m}
              <option value={m}>{m}</option>
            {/each}
          </select>
        </div>
        <div class="field">
          <label for="proj-desc">Description <span class="muted">(optional)</span></label>
          <textarea id="proj-desc" rows="2" bind:value={description} disabled={creating}></textarea>
        </div>
        <div class="row between" style="margin-top: 6px;">
          <button type="button" class="ghost" onclick={closeCreate} disabled={creating}>Cancel</button>
          <button type="submit" class="primary" disabled={!createValid || creating}>
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
  /* Center the create button's inline spinner. */
  button.primary :global(.spinner) { margin-right: 6px; vertical-align: middle; }
  @media (max-width: 560px) {
    .grid { grid-template-columns: 1fr; }
  }
</style>
