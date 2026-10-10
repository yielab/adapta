<script lang="ts">
  import { api, ApiError } from "../lib/api";
  import { navigate } from "../lib/router";
  import { toastError, toastSuccess } from "../lib/toast";
  import type { Project } from "../lib/types";

  import StatusBadge from "../components/StatusBadge.svelte";
  import Overview from "./Overview.svelte";
  import RagFlow from "./RagFlow.svelte";
  import AdapterFlow from "./AdapterFlow.svelte";
  import EndpointPanel from "./EndpointPanel.svelte";
  import Playground from "./Playground.svelte";
  import Usage from "./Usage.svelte";

  // The project id is routed in by App.svelte (parts[1] of the hash route).
  let { id }: { id: string } = $props();

  type Tab = "overview" | "setup" | "endpoint" | "playground" | "usage" | "settings";

  let project = $state<Project | null>(null);
  let loading = $state(false);
  let loadErr = $state(false);
  let tab = $state<Tab>("overview");

  // (E3.5) Project system prompt, edited in the Settings tab.
  let promptDraft = $state("");
  let savingPrompt = $state(false);

  async function savePrompt() {
    if (!project) return;
    savingPrompt = true;
    try {
      project = await api.updateProject(project.id, { system_prompt: promptDraft.trim() || null });
      promptDraft = project.system_prompt ?? "";
      toastSuccess("System prompt saved.");
    } catch (e) {
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else toastError("Could not save the system prompt.");
    } finally {
      savingPrompt = false;
    }
  }

  // Re-fetch whenever the routed id changes.
  let loadedId = $state<string | null>(null);

  $effect(() => {
    if (id === loadedId) return;
    loadedId = id;
    tab = "setup";
    void load(id);
  });

  async function load(pid: string) {
    loading = true;
    loadErr = false;
    try {
      project = await api.getProject(pid);
      promptDraft = project.system_prompt ?? "";
    } catch (e) {
      loadErr = true;
      project = null;
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else toastError("Could not load the project.");
    } finally {
      loading = false;
    }
  }

  function typeLabel(t: string) {
    return t === "rag" ? "Knowledge" : "Behavior";
  }
</script>

{#if loading}
  <div class="card">
    <span class="row" style="gap: 8px;"><span class="spinner"></span><small>Loading project…</small></span>
  </div>
{:else if loadErr || !project}
  <div class="card empty">
    <p>Could not load this project.</p>
    <div class="row" style="justify-content: center; gap: 10px;">
      <button class="ghost sm" onclick={() => load(id)}>Retry</button>
      <button class="ghost sm" onclick={() => navigate("/projects")}>Back to projects</button>
    </div>
  </div>
{:else}
  <div style="margin-bottom: 6px;">
    <button class="ghost sm" onclick={() => navigate("/projects")}>← Projects</button>
  </div>

  <div class="row between" style="margin-bottom: 16px;">
    <div>
      <div class="row" style="gap: 10px;">
        <h1 style="margin: 0;">{project.name}</h1>
        <span class="badge {project.type === 'rag' ? 'knowledge' : 'behavior'}">{typeLabel(project.type)}</span>
        <StatusBadge status={project.status} />
      </div>
      <p class="muted" style="margin: 6px 0 0;">
        Base model <span class="mono">{project.base_model}</span>
      </p>
    </div>
  </div>

  <div class="tabs" role="tablist">
    <button class="tab" class:active={tab === "overview"} role="tab" aria-selected={tab === "overview"} onclick={() => (tab = "overview")}>
      Overview
    </button>
    <button class="tab" class:active={tab === "setup"} role="tab" aria-selected={tab === "setup"} onclick={() => (tab = "setup")}>
      Setup
    </button>
    <button class="tab" class:active={tab === "endpoint"} role="tab" aria-selected={tab === "endpoint"} onclick={() => (tab = "endpoint")}>
      Endpoint &amp; keys
    </button>
    <button class="tab" class:active={tab === "playground"} role="tab" aria-selected={tab === "playground"} onclick={() => (tab = "playground")}>
      Playground
    </button>
    <button class="tab" class:active={tab === "settings"} role="tab" aria-selected={tab === "settings"} onclick={() => (tab = "settings")}>
      Settings
    </button>
    <button class="tab" class:active={tab === "usage"} role="tab" aria-selected={tab === "usage"} onclick={() => (tab = "usage")}>
      Usage
    </button>
  </div>

  {#if tab === "overview"}
    <Overview {project} onGoTab={(t) => (tab = t)} />
  {:else if tab === "setup"}
    {#if project.type === "rag"}
      <RagFlow {project} />
    {:else}
      <AdapterFlow {project} />
    {/if}
  {:else if tab === "endpoint"}
    <EndpointPanel {project} />
  {:else if tab === "playground"}
    <Playground {project} />
  {:else if tab === "settings"}
    <div class="card">
      <div class="field">
        <label for="proj-prompt">System prompt</label>
        <textarea
          id="proj-prompt"
          rows="6"
          maxlength="8000"
          placeholder="Optional. Tone, role or rules for every answer — placed before the retrieved documents."
          bind:value={promptDraft}
          disabled={savingPrompt}
        ></textarea>
        <small class="muted">
          Applied to every request on this project's endpoint. When the project has documents, the
          model is also told to say it can't find an answer rather than guess.
        </small>
      </div>
      <button onclick={savePrompt} disabled={savingPrompt || promptDraft === (project.system_prompt ?? "")}>
        {savingPrompt ? "Saving…" : "Save"}
      </button>
    </div>
  {:else}
    <Usage {project} />
  {/if}
{/if}
