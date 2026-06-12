<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "../lib/api";
  import type { BaseModelInfo, BestFor } from "../lib/types";
  import Spinner from "../components/Spinner.svelte";

  let models: BaseModelInfo[] = [];
  let loading = true;
  let error = "";

  onMount(async () => {
    try {
      models = await api.listModels();
    } catch (e: any) {
      error = e.message ?? "Failed to load model catalog";
    } finally {
      loading = false;
    }
  });

  const MODEL_TYPE_LABEL: Record<string, string> = {
    chat: "General chat",
    code: "Code specialist",
    reasoning: "Reasoning",
  };

  const BEST_FOR_LABEL: Record<BestFor, string> = {
    knowledge: "Knowledge (RAG)",
    behavior: "Behavior (fine-tune)",
    code: "Code",
    vision: "Vision",
  };

  const BEST_FOR_COLOR: Record<BestFor, string> = {
    knowledge: "chip-blue",
    behavior: "chip-purple",
    code: "chip-green",
    vision: "chip-orange",
  };
</script>

<div class="models-page">
  <header class="page-header">
    <h1>Model Catalog</h1>
    <p class="page-sub">
      The base models available on this server for RAG and fine-tuning.
      Models must be downloaded to disk before they can serve or train.
    </p>
  </header>

  {#if loading}
    <div class="center"><Spinner /></div>
  {:else if error}
    <div class="error-box">{error}</div>
  {:else}
    <div class="picker-guide">
      <strong>Which model should I pick?</strong>
      Use <em>0.5B</em> for quick local experiments.
      <em>3B-Instruct</em> is the default for RAG + general fine-tuning.
      <em>Coder-3B</em> for code understanding or generation tasks.
      <em>7B-Instruct</em> for the highest output quality (requires ≥16 GB VRAM to train).
      <em>VL-3B</em> for image + text understanding.
    </div>

    <div class="model-grid">
      {#each models as m}
        <div class="model-card" class:unavailable={!m.available}>
          <div class="card-top">
            <div class="card-identity">
              <span class="model-name">{m.name}</span>
              <span class="modality-badge" class:vision={m.modality === "vision"}>
                {m.modality === "vision" ? "Vision" : "Text"}
              </span>
              <span class="type-badge">{MODEL_TYPE_LABEL[m.model_type] ?? m.model_type}</span>
            </div>
            <div class="avail-badge" class:available={m.available} class:missing={!m.available}>
              {m.available ? "Ready" : "Not downloaded"}
            </div>
          </div>

          <p class="use-case">{m.use_case}</p>

          {#if m.best_for.length > 0}
            <div class="chips">
              {#each m.best_for as bf}
                <span class="chip {BEST_FOR_COLOR[bf]}">{BEST_FOR_LABEL[bf]}</span>
              {/each}
            </div>
          {/if}

          <div class="resources">
            {#if m.train_vram_gb != null}
              <span class="resource-item">
                <span class="resource-label">Trains on</span>
                <span class="resource-val">~{m.train_vram_gb} GB VRAM</span>
              </span>
            {/if}
            {#if m.serve_ram_gb != null}
              <span class="resource-item">
                <span class="resource-label">Serves in</span>
                <span class="resource-val">~{m.serve_ram_gb} GB RAM</span>
              </span>
            {/if}
          </div>

          {#if m.notes}
            <p class="notes">{m.notes}</p>
          {/if}

          {#if !m.available}
            <p class="download-hint">
              GGUF not on this server — see
              <a href="https://brain-from-cero.readthedocs.io/en/latest/reference/OPERATIONS/" target="_blank" rel="noopener">
                Operations §6.3
              </a>
              for download instructions.
            </p>
          {/if}

          <div class="hf-id">
            <span class="resource-label">HuggingFace</span>
            <code>{m.hf_repo_id}</code>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .models-page { max-width: 900px; margin: 0 auto; padding: 2rem 1.5rem; }

  .page-header { margin-bottom: 1.5rem; }
  .page-header h1 { font-size: 1.5rem; font-weight: 700; margin: 0 0 .4rem; }
  .page-sub { color: var(--text-muted); margin: 0; font-size: .875rem; }

  .center { display: flex; justify-content: center; padding: 3rem; }
  .error-box { background: #3d1515; border: 1px solid #7f2828; color: #f98080; padding: .75rem 1rem; border-radius: 6px; }

  .picker-guide {
    background: var(--surface-2, #1e2030);
    border: 1px solid var(--border, #2d3148);
    border-radius: 8px;
    padding: .85rem 1.1rem;
    font-size: .85rem;
    color: var(--text-muted);
    margin-bottom: 1.5rem;
    line-height: 1.6;
  }
  .picker-guide strong { color: var(--text); }
  .picker-guide em { color: var(--text); font-style: normal; font-weight: 500; }

  .model-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 1rem; }

  .model-card {
    background: var(--surface-1, #161720);
    border: 1px solid var(--border, #2d3148);
    border-radius: 10px;
    padding: 1.1rem 1.2rem;
    display: flex;
    flex-direction: column;
    gap: .6rem;
  }
  .model-card.unavailable { opacity: .7; }

  .card-top { display: flex; justify-content: space-between; align-items: flex-start; gap: .5rem; }
  .card-identity { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem; }

  .model-name { font-weight: 600; font-size: .95rem; font-family: monospace; }

  .modality-badge {
    font-size: .7rem; padding: .15rem .45rem; border-radius: 4px;
    background: #1e3a5f; color: #7ec8f5;
    text-transform: uppercase; letter-spacing: .04em;
  }
  .modality-badge.vision { background: #3d2b00; color: #f5c842; }

  .type-badge {
    font-size: .7rem; padding: .15rem .45rem; border-radius: 4px;
    background: var(--surface-2, #1e2030); color: var(--text-muted);
    border: 1px solid var(--border, #2d3148);
  }

  .avail-badge {
    font-size: .72rem; font-weight: 600; padding: .2rem .55rem; border-radius: 5px;
    white-space: nowrap; flex-shrink: 0;
  }
  .avail-badge.available { background: #0f2e1a; color: #4caf82; border: 1px solid #1e5c38; }
  .avail-badge.missing   { background: #2e1a0f; color: #e0936a; border: 1px solid #5c3a1e; }

  .use-case { margin: 0; font-size: .875rem; color: var(--text); line-height: 1.5; }

  .chips { display: flex; flex-wrap: wrap; gap: .35rem; }
  .chip {
    font-size: .7rem; padding: .18rem .5rem; border-radius: 4px; font-weight: 500;
  }
  .chip-blue   { background: #1e3a5f; color: #7ec8f5; }
  .chip-purple { background: #2e1a5c; color: #b89df5; }
  .chip-green  { background: #0f2e1a; color: #4caf82; }
  .chip-orange { background: #3d2b00; color: #f5c842; }

  .resources { display: flex; flex-wrap: wrap; gap: .75rem; }
  .resource-item { display: flex; flex-direction: column; gap: .1rem; }
  .resource-label { font-size: .68rem; text-transform: uppercase; letter-spacing: .06em; color: var(--text-muted); }
  .resource-val { font-size: .8rem; font-weight: 600; color: var(--text); }

  .notes { margin: 0; font-size: .78rem; color: var(--text-muted); font-style: italic; }

  .download-hint {
    margin: 0; font-size: .78rem;
    background: #2e1a0f; border: 1px solid #5c3a1e; color: #e0936a;
    padding: .5rem .75rem; border-radius: 5px;
  }
  .download-hint a { color: #f5a87c; }

  .hf-id { display: flex; align-items: center; gap: .5rem; }
  .hf-id code { font-size: .75rem; color: var(--text-muted); }
</style>
