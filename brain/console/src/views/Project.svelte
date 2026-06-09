<script lang="ts">
  import { api, ApiError } from "../lib/api";
  import { navigate } from "../lib/router";
  import { toastError } from "../lib/toast";
  import type { Project } from "../lib/types";

  import StatusBadge from "../components/StatusBadge.svelte";
  import RagFlow from "./RagFlow.svelte";
  import FinetuneFlow from "./FinetuneFlow.svelte";
  import EndpointPanel from "./EndpointPanel.svelte";
  import Playground from "./Playground.svelte";
  import Usage from "./Usage.svelte";

  // The project id is routed in by App.svelte (parts[1] of the hash route).
  let { id }: { id: string } = $props();

  type Tab = "setup" | "endpoint" | "playground" | "usage";

  let project = $state<Project | null>(null);
  let loading = $state(false);
  let loadErr = $state(false);
  let tab = $state<Tab>("setup");

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
        <span class="badge {project.type === 'rag' ? 'blue' : 'amber'}">{typeLabel(project.type)}</span>
        <StatusBadge status={project.status} />
      </div>
      <p class="muted" style="margin: 6px 0 0;">
        Base model <span class="mono">{project.base_model}</span>
      </p>
    </div>
  </div>

  <div class="tabs" role="tablist">
    <button class="tab" class:active={tab === "setup"} role="tab" aria-selected={tab === "setup"} onclick={() => (tab = "setup")}>
      Setup
    </button>
    <button class="tab" class:active={tab === "endpoint"} role="tab" aria-selected={tab === "endpoint"} onclick={() => (tab = "endpoint")}>
      Endpoint &amp; keys
    </button>
    <button class="tab" class:active={tab === "playground"} role="tab" aria-selected={tab === "playground"} onclick={() => (tab = "playground")}>
      Playground
    </button>
    <button class="tab" class:active={tab === "usage"} role="tab" aria-selected={tab === "usage"} onclick={() => (tab = "usage")}>
      Usage
    </button>
  </div>

  {#if tab === "setup"}
    {#if project.type === "rag"}
      <RagFlow {project} />
    {:else}
      <FinetuneFlow {project} />
    {/if}
  {:else if tab === "endpoint"}
    <EndpointPanel {project} />
  {:else if tab === "playground"}
    <Playground {project} />
  {:else}
    <Usage {project} />
  {/if}
{/if}
