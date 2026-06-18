<script lang="ts">
  // Daily token-usage rollup for the endpoint: lifetime totals up top, then a
  // per-day table (newest first). Until any traffic flows the API returns zeroed
  // totals and an empty `days` array → show a friendly empty state. (TODO §5.9)
  import { api, ApiError } from "../lib/api";
  import { toastError } from "../lib/toast";
  import type { Project, UsageResponse } from "../lib/types";

  let { project }: { project: Project } = $props();

  let usage = $state<UsageResponse | null>(null);
  let loading = $state(true);
  let loadErr = $state(false);

  // Reload whenever we switch to a different project.
  let loadedId = $state<string | null>(null);
  $effect(() => {
    if (project.id === loadedId) return;
    loadedId = project.id;
    usage = null;
    void load();
  });

  async function load() {
    loading = true;
    loadErr = false;
    try {
      usage = await api.getUsage(project.id);
    } catch (e) {
      loadErr = true;
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else toastError("Could not load usage.");
    } finally {
      loading = false;
    }
  }

  // No traffic yet: zero requests and no day buckets.
  const hasTraffic = $derived(!!usage && (usage.total_requests > 0 || usage.days.length > 0));

  // Newest first — don't assume the API ordering.
  const days = $derived(usage ? [...usage.days].sort((a, b) => b.day.localeCompare(a.day)) : []);

  function fmtNum(n: number): string {
    return n.toLocaleString();
  }

  function fmtDay(iso: string): string {
    try {
      // Day buckets are date-only (YYYY-MM-DD); parse as UTC midnight so the
      // label doesn't shift across timezones.
      return new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
    } catch {
      return iso;
    }
  }
</script>

<div class="card">
  <div class="row between" style="margin-bottom: 4px;">
    <h2 style="margin: 0; font-size: 16px;">Usage</h2>
    {#if usage && !loading}
      <button class="ghost sm" onclick={() => load()}>Refresh</button>
    {/if}
  </div>
  <p class="muted" style="margin: 0 0 14px;">Token consumption for this project's endpoint.</p>

  {#if loading}
    <span class="row" style="gap: 8px;"><span class="spinner"></span><small>Loading usage…</small></span>
  {:else if loadErr}
    <div class="empty">
      <p>Could not load usage.</p>
      <button class="ghost sm" onclick={() => load()}>Retry</button>
    </div>
  {:else if !hasTraffic}
    <div class="empty">
      <p>No usage yet.</p>
      <small class="muted">Once apps call this endpoint, daily token totals will show up here.</small>
    </div>
  {:else if usage}
    <!-- ── Lifetime totals ──────────────────────────────────────────────────── -->
    <div class="choice-grid" style="margin-bottom: 18px;">
      <div class="muted-box">
        <small class="muted">Requests</small>
        <div class="mono" style="font-size: 20px; margin-top: 4px;">{fmtNum(usage.total_requests)}</div>
      </div>
      <div class="muted-box">
        <small class="muted">Prompt tokens</small>
        <div class="mono" style="font-size: 20px; margin-top: 4px;">{fmtNum(usage.total_prompt_tokens)}</div>
      </div>
      <div class="muted-box">
        <small class="muted">Completion tokens</small>
        <div class="mono" style="font-size: 20px; margin-top: 4px;">{fmtNum(usage.total_completion_tokens)}</div>
      </div>
      <div class="muted-box">
        <small class="muted">Total tokens</small>
        <div class="mono" style="font-size: 20px; margin-top: 4px;">{fmtNum(usage.total_tokens)}</div>
      </div>
    </div>

    <!-- ── Per-day breakdown ────────────────────────────────────────────────── -->
    {#if days.length === 0}
      <div class="empty">No daily breakdown available yet.</div>
    {:else}
      <table>
        <thead>
          <tr>
            <th>Day</th>
            <th style="text-align: right;">Requests</th>
            <th style="text-align: right;">Prompt</th>
            <th style="text-align: right;">Completion</th>
            <th style="text-align: right;">Total</th>
          </tr>
        </thead>
        <tbody>
          {#each days as d (d.day)}
            <tr>
              <td class="mono">{fmtDay(d.day)}</td>
              <td class="mono" style="text-align: right;">{fmtNum(d.request_count)}</td>
              <td class="mono" style="text-align: right;">{fmtNum(d.prompt_tokens)}</td>
              <td class="mono" style="text-align: right;">{fmtNum(d.completion_tokens)}</td>
              <td class="mono" style="text-align: right;">{fmtNum(d.total_tokens)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  {/if}
</div>
