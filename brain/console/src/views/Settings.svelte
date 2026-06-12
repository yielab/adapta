<script lang="ts">
  import { session } from "../lib/session";
  import { navigate } from "../lib/router";
  import { api, ApiError } from "../lib/api";
  import { toastError, toastSuccess } from "../lib/toast";

  let { tab = "account" }: { tab?: string } = $props();

  const user = $derived($session.user);
  const activeTeam = $derived($session.activeTeam);
  const isAdmin = $derived(
    user?.teams.find((t) => t.id === activeTeam?.id)?.role === "admin"
  );

  const TABS = $derived([
    { id: "account",  label: "Account" },
    { id: "team",     label: "Team & Members" },
    ...(isAdmin ? [
      { id: "platform", label: "Platform" },
      { id: "system",   label: "System" },
    ] : []),
  ]);

  function goTab(id: string) { navigate(`/settings/${id}`); }

  // ── Platform settings ─────────────────────────────────────────────────────
  import type { SettingEntry } from "../lib/types";
  let platformSettings = $state<SettingEntry[]>([]);
  let platformLoading = $state(false);
  let platformErr = $state(false);
  let platformLoadedFor = $state<string | null>(null);
  // Pending edits: key → string (raw input), saved once explicitly
  let pendingEdits = $state<Record<string, string>>({});
  let savingKeys = $state<Set<string>>(new Set());

  const GROUPS: { id: string; label: string }[] = [
    { id: "generation", label: "Generation defaults" },
    { id: "retrieval",  label: "Retrieval & chunking" },
    { id: "synthesis",  label: "Synthesis" },
    { id: "limits",     label: "Request limits" },
  ];

  const settingsByGroup = $derived.by(() => {
    const groups: Record<string, SettingEntry[]> = {};
    for (const s of platformSettings) {
      if (!groups[s.group]) groups[s.group] = [];
      groups[s.group].push(s);
    }
    return groups;
  });

  $effect(() => {
    if (tab !== "platform") return;
    const tid = activeTeam?.id;
    if (!tid || tid === platformLoadedFor) return;
    platformLoadedFor = tid;
    platformLoading = true; platformErr = false;
    api.getSettings(tid)
      .then((s) => { platformSettings = s; pendingEdits = {}; })
      .catch(() => { platformErr = true; })
      .finally(() => { platformLoading = false; });
  });

  async function saveSetting(key: string) {
    if (!activeTeam) return;
    const raw = pendingEdits[key];
    if (raw === undefined) return;
    savingKeys = new Set([...savingKeys, key]);
    try {
      const updated = await api.putSetting(activeTeam.id, key, parseFloat(raw) || parseInt(raw, 10) || 0);
      platformSettings = platformSettings.map((s) => s.key === key ? { ...s, ...updated } : s);
      const { [key]: _, ...rest } = pendingEdits;
      pendingEdits = rest;
      toastSuccess("Setting saved.");
    } catch (e) {
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else toastError("Could not save setting.");
    } finally {
      const s = new Set(savingKeys); s.delete(key); savingKeys = s;
    }
  }

  async function resetSetting(key: string) {
    if (!activeTeam) return;
    savingKeys = new Set([...savingKeys, key]);
    try {
      await api.deleteSetting(activeTeam.id, key);
      // re-fetch to get updated provenance
      const updated = await api.getSettings(activeTeam.id);
      platformSettings = updated;
      const { [key]: _, ...rest } = pendingEdits;
      pendingEdits = rest;
      toastSuccess("Setting reset to default.");
    } catch (e) {
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else toastError("Could not reset setting.");
    } finally {
      const s = new Set(savingKeys); s.delete(key); savingKeys = s;
    }
  }

  // ── System status ─────────────────────────────────────────────────────────
  type DeepHealth = { status: string; checks?: Record<string, { status: string; detail?: string }> };
  type GpuInfo = { available: boolean; type?: string; device_count?: number; devices?: { name: string; memory_total_mb: number; memory_free_mb: number }[] };
  let systemHealth = $state<DeepHealth | null>(null);
  let systemGpu = $state<GpuInfo | null>(null);
  let systemLoading = $state(false);
  let systemErr = $state(false);

  $effect(() => {
    if (tab !== "system") return;
    if (systemHealth) return;
    systemLoading = true; systemErr = false;
    Promise.all([
      fetch("/health/deep").then((r) => r.json() as Promise<DeepHealth>),
      fetch("/gpu").then((r) => r.json() as Promise<GpuInfo>),
    ]).then(([h, g]) => { systemHealth = h; systemGpu = g; })
      .catch(() => { systemErr = true; })
      .finally(() => { systemLoading = false; });
  });

  function refreshSystem() { systemHealth = null; systemGpu = null; }

  // ── Team members ──────────────────────────────────────────────────────────
  type Member = { user_id: string; email: string; role: string; joined_at: string };
  let members = $state<Member[]>([]);
  let membersLoading = $state(false);
  let membersErr = $state(false);
  let membersLoadedFor = $state<string | null>(null);

  $effect(() => {
    if (tab !== "team") return;
    const tid = activeTeam?.id;
    if (!tid || tid === membersLoadedFor) return;
    membersLoadedFor = tid;
    membersLoading = true; membersErr = false;
    api.listTeamMembers(tid)
      .then((m) => { members = m; })
      .catch(() => { membersErr = true; })
      .finally(() => { membersLoading = false; });
  });

  // ── Invite ─────────────────────────────────────────────────────────────────
  let inviteEmail = $state("");
  let inviteRole = $state("member");
  let inviteBusy = $state(false);
  let inviteToken = $state<string | null>(null);
  let tokenCopied = $state(false);

  async function doInvite() {
    if (inviteBusy || !inviteEmail.trim() || !activeTeam) return;
    inviteBusy = true; inviteToken = null;
    try {
      const res = await api.invite(activeTeam.id, inviteEmail.trim(), inviteRole);
      inviteToken = res.token ?? null;
      inviteEmail = "";
      toastSuccess("Invitation created.");
      membersLoadedFor = null; // force members reload
    } catch (e) {
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else toastError("Could not create invitation.");
    } finally {
      inviteBusy = false;
    }
  }

  async function copyToken() {
    if (!inviteToken) return;
    try {
      await navigator.clipboard.writeText(inviteToken);
      tokenCopied = true; setTimeout(() => { tokenCopied = false; }, 1500);
    } catch { /* clipboard unavailable */ }
  }

  // ── Change password ────────────────────────────────────────────────────────
  let cpCurrent = $state("");
  let cpNew = $state("");
  let cpConfirm = $state("");
  let cpBusy = $state(false);

  const cpError = $derived(
    cpNew.length > 0 && cpNew.length < 8 ? "New password must be at least 8 characters." :
    cpConfirm.length > 0 && cpNew !== cpConfirm ? "Passwords do not match." :
    null
  );

  async function doChangePassword() {
    if (cpBusy || cpError || !cpCurrent || !cpNew || !cpConfirm) return;
    cpBusy = true;
    try {
      await api.changePassword(cpCurrent, cpNew);
      toastSuccess("Password updated.");
      cpCurrent = ""; cpNew = ""; cpConfirm = "";
    } catch (e) {
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else toastError("Could not update password.");
    } finally {
      cpBusy = false;
    }
  }
</script>

<div class="settings-page">
  <header class="page-header">
    <h1>Settings</h1>
  </header>

  <div class="settings-shell">
    <nav class="settings-nav">
      {#each TABS as t}
        <button
          class="tab-btn"
          class:active={tab === t.id}
          onclick={() => goTab(t.id)}
        >{t.label}</button>
      {/each}
    </nav>

    <div class="tab-content">
      {#if tab === "account"}
        <h2 class="section-h">Account</h2>
        {#if user}
          <div class="info-row">
            <span class="info-label">Email</span>
            <span class="mono">{user.email}</span>
          </div>
        {/if}

        <h3 class="sub-h">Change password</h3>
        <div class="form-stack">
          <div class="field">
            <label for="cp-current">Current password</label>
            <input id="cp-current" type="password" bind:value={cpCurrent} disabled={cpBusy} autocomplete="current-password" />
          </div>
          <div class="field">
            <label for="cp-new">New password</label>
            <input id="cp-new" type="password" bind:value={cpNew} disabled={cpBusy} autocomplete="new-password" />
          </div>
          <div class="field">
            <label for="cp-confirm">Confirm new password</label>
            <input id="cp-confirm" type="password" bind:value={cpConfirm} disabled={cpBusy} autocomplete="new-password"
              onkeydown={(e) => e.key === "Enter" && doChangePassword()} />
          </div>
          {#if cpError}
            <p class="field-error">{cpError}</p>
          {/if}
          <div style="display: flex; justify-content: flex-end;">
            <button class="primary sm" onclick={doChangePassword}
              disabled={cpBusy || !!cpError || !cpCurrent || !cpNew || !cpConfirm}>
              {#if cpBusy}<span class="spinner"></span>{/if}
              Update password
            </button>
          </div>
        </div>
      {:else if tab === "team"}
        <h2 class="section-h">Team &amp; Members</h2>
        {#if activeTeam}
          <div class="info-row" style="margin-bottom: 1rem;">
            <span class="info-label">Team</span>
            <span>{activeTeam.name}</span>
          </div>
        {/if}

        {#if membersLoading}
          <span class="row" style="gap: 8px;"><span class="spinner"></span><small>Loading members…</small></span>
        {:else if membersErr}
          <p class="field-error">Could not load members.</p>
        {:else if members.length > 0}
          <table class="members-table">
            <thead>
              <tr><th>Email</th><th>Role</th><th>Joined</th></tr>
            </thead>
            <tbody>
              {#each members as m (m.user_id)}
                <tr>
                  <td class="mono" style="font-size: .8rem;">{m.email}</td>
                  <td><span class="role-badge role-{m.role}">{m.role}</span></td>
                  <td style="font-size: .75rem; color: var(--muted);">{new Date(m.joined_at).toLocaleDateString(undefined, {year:"numeric",month:"short",day:"numeric"})}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        {:else}
          <p class="coming-soon">No members found.</p>
        {/if}

        {#if isAdmin && activeTeam}
          <h3 class="sub-h">Invite a user</h3>
          <div class="form-stack">
            <div class="field">
              <label for="inv-email">Email address</label>
              <input id="inv-email" type="email" bind:value={inviteEmail} disabled={inviteBusy}
                placeholder="colleague@example.com"
                onkeydown={(e) => e.key === "Enter" && doInvite()} />
            </div>
            <div class="field">
              <label for="inv-role">Role</label>
              <select id="inv-role" bind:value={inviteRole} disabled={inviteBusy}>
                <option value="member">Member</option>
                <option value="viewer">Viewer</option>
                <option value="admin">Admin</option>
              </select>
            </div>
            <div style="display: flex; justify-content: flex-end;">
              <button class="primary sm" onclick={doInvite} disabled={inviteBusy || !inviteEmail.trim()}>
                {#if inviteBusy}<span class="spinner"></span>{/if}
                Send invite
              </button>
            </div>
          </div>

          {#if inviteToken}
            <div class="token-box">
              <div class="token-label">Share this invite token — it is shown once only</div>
              <div class="token-value mono">{inviteToken}</div>
              <button class="ghost sm" onclick={copyToken}>{tokenCopied ? "Copied" : "Copy token"}</button>
            </div>
          {/if}
        {/if}
      {:else if tab === "platform" && isAdmin}
        <h2 class="section-h">Platform settings</h2>
        <p class="section-note">
          These override the defaults for your team. Changes to <em>Retrieval &amp; chunking</em> apply to <strong>future</strong> document indexing only — already-indexed documents are unaffected.
        </p>

        {#if platformLoading}
          <span class="row" style="gap: 8px;"><span class="spinner"></span><small>Loading…</small></span>
        {:else if platformErr}
          <p class="field-error">Could not load platform settings.</p>
        {:else}
          {#each GROUPS as grp}
            {#if settingsByGroup[grp.id]?.length}
              <h3 class="sub-h">{grp.label}</h3>
              {#each settingsByGroup[grp.id] as s (s.key)}
                <div class="setting-row">
                  <div class="setting-meta">
                    <div class="setting-label">{s.label}
                      <span class="source-badge source-{s.source}">{s.source}</span>
                      {#if s.source === "env"}
                        <span class="env-lock" title="Set by the host environment — see OPERATIONS">🔒</span>
                      {/if}
                    </div>
                    <div class="setting-desc">{s.description}</div>
                    <div class="setting-bounds">Range: {s.min} – {s.max} · Default: {s.default}</div>
                  </div>
                  <div class="setting-ctrl">
                    {#if s.source === "env"}
                      <span class="mono" style="font-size:.8rem;">{s.value}</span>
                    {:else}
                      <input
                        type="number"
                        class="setting-input"
                        min={s.min}
                        max={s.max}
                        step={typeof s.default === "number" && !Number.isInteger(s.default) ? 0.01 : 1}
                        value={pendingEdits[s.key] !== undefined ? pendingEdits[s.key] : s.value}
                        oninput={(e) => { pendingEdits = { ...pendingEdits, [s.key]: (e.currentTarget as HTMLInputElement).value }; }}
                        disabled={savingKeys.has(s.key)}
                      />
                      {#if pendingEdits[s.key] !== undefined}
                        <button class="primary sm" onclick={() => saveSetting(s.key)} disabled={savingKeys.has(s.key)}>
                          {#if savingKeys.has(s.key)}<span class="spinner"></span>{/if}Save
                        </button>
                      {/if}
                      {#if s.source === "override"}
                        <button class="ghost sm" onclick={() => resetSetting(s.key)} disabled={savingKeys.has(s.key)}>Reset</button>
                      {/if}
                    {/if}
                  </div>
                </div>
              {/each}
            {/if}
          {/each}
        {/if}
      {:else if tab === "system" && isAdmin}
        <div class="row between" style="align-items: center; margin-bottom: 1rem;">
          <h2 class="section-h" style="margin: 0;">System status</h2>
          <button class="ghost sm" onclick={refreshSystem}>Refresh</button>
        </div>

        {#if systemLoading}
          <span class="row" style="gap: 8px;"><span class="spinner"></span><small>Loading…</small></span>
        {:else if systemErr}
          <p class="field-error">Could not load system status.</p>
        {:else if systemHealth}
          <h3 class="sub-h" style="margin-top: 0;">Services</h3>
          <table class="members-table">
            <tbody>
              {#each Object.entries(systemHealth.checks ?? {}) as [name, check]}
                <tr>
                  <td style="font-size: .8rem; text-transform: capitalize;">{name.replace(/_/g, " ")}</td>
                  <td>
                    <span class="role-badge role-{check.status === 'ok' ? 'admin' : 'viewer'}"
                      style={check.status !== 'ok' ? 'background:#3d1515;color:#f98080;' : ''}>
                      {check.status}
                    </span>
                  </td>
                  {#if check.detail}
                    <td style="font-size: .75rem; color: var(--muted);">{check.detail}</td>
                  {:else}
                    <td></td>
                  {/if}
                </tr>
              {/each}
            </tbody>
          </table>

          {#if systemGpu}
            <h3 class="sub-h">GPU</h3>
            <div class="info-row">
              <span class="info-label">Available</span>
              <span>{systemGpu.available ? "Yes" : "No (CPU-only)"}</span>
            </div>
            {#if systemGpu.type}
              <div class="info-row">
                <span class="info-label">Type</span>
                <span class="mono">{systemGpu.type}</span>
              </div>
            {/if}
            {#if systemGpu.devices?.length}
              {#each systemGpu.devices as dev}
                <div class="info-row">
                  <span class="info-label">Device</span>
                  <span class="mono">{dev.name}</span>
                  <span class="muted" style="font-size:.75rem; margin-left: .5rem;">
                    {((dev.memory_free_mb ?? 0) / 1024).toFixed(1)} GB free / {((dev.memory_total_mb ?? 0) / 1024).toFixed(1)} GB total
                  </span>
                </div>
              {/each}
            {/if}
          {/if}
        {:else}
          <p class="coming-soon">No data yet.</p>
        {/if}
      {:else}
        <p class="coming-soon">Select a section from the left.</p>
      {/if}
    </div>
  </div>
</div>

<style>
  .settings-page { max-width: 860px; margin: 0 auto; padding: 2rem 1.5rem; }
  .page-header { margin-bottom: 1.5rem; }
  .page-header h1 { font-size: 1.5rem; font-weight: 700; margin: 0; }

  .settings-shell {
    display: grid;
    grid-template-columns: 180px 1fr;
    gap: 1.5rem;
    align-items: start;
  }

  .settings-nav {
    display: flex;
    flex-direction: column;
    gap: .25rem;
    background: var(--surface-1, #161720);
    border: 1px solid var(--border, #2d3148);
    border-radius: 8px;
    padding: .5rem;
  }

  .tab-btn {
    text-align: left;
    background: none;
    border: none;
    padding: .55rem .8rem;
    border-radius: 6px;
    cursor: pointer;
    color: var(--muted);
    font-size: .875rem;
    transition: background .15s, color .15s;
  }
  .tab-btn:hover { background: var(--panel-2, #1e2030); color: var(--text); }
  .tab-btn.active { background: var(--accent-weak, #1e2a50); color: var(--text); font-weight: 600; }

  .tab-content {
    background: var(--surface-1, #161720);
    border: 1px solid var(--border, #2d3148);
    border-radius: 8px;
    padding: 1.5rem;
    min-height: 200px;
  }

  .coming-soon { color: var(--text-muted, #888); font-size: .875rem; }

  .section-h { font-size: 1rem; font-weight: 700; margin: 0 0 1rem; }
  .sub-h { font-size: .875rem; font-weight: 600; margin: 1.25rem 0 .65rem; color: var(--text); }

  .info-row {
    display: flex; align-items: center; gap: .75rem;
    padding: .55rem 0; border-bottom: 1px solid var(--border, #2d3148); margin-bottom: .5rem;
  }
  .info-label { font-size: .72rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); width: 80px; flex-shrink: 0; }

  .form-stack { display: flex; flex-direction: column; gap: .75rem; max-width: 380px; }
  .field { display: flex; flex-direction: column; gap: .3rem; }
  .field label { font-size: .8rem; color: var(--muted); }
  .field-error { font-size: .78rem; color: #f98080; margin: -.3rem 0 0; }

  .members-table { width: 100%; border-collapse: collapse; margin-bottom: .75rem; }
  .members-table th { font-size: .72rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); padding: .4rem .5rem; text-align: left; border-bottom: 1px solid var(--border, #2d3148); }
  .members-table td { padding: .5rem; border-bottom: 1px solid var(--border, #2d314820); }
  .role-badge { font-size: .72rem; padding: .15rem .45rem; border-radius: 4px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }
  .role-admin  { background: #1a2a1a; color: #6fcf97; }
  .role-member { background: #1e2030; color: var(--muted); }
  .role-viewer { background: #1e2030; color: var(--muted); opacity: .7; }

  .token-box {
    margin-top: 1rem; padding: .85rem 1rem;
    background: #1c1a0e; border: 1px solid #5c4a0055; border-radius: 8px;
    display: flex; flex-direction: column; gap: .55rem;
  }
  .token-label { font-size: .75rem; color: #e2c97e; font-weight: 600; }
  .token-value { font-size: .78rem; word-break: break-all; color: var(--text); }

  /* Platform settings */
  .section-note { font-size: .8rem; color: var(--muted); margin: -.25rem 0 1.25rem; line-height: 1.5; }
  .setting-row {
    display: flex; align-items: flex-start; gap: .85rem;
    padding: .65rem 0; border-bottom: 1px solid var(--border, #2d314820);
  }
  .setting-meta { flex: 1; }
  .setting-label { font-size: .82rem; font-weight: 600; display: flex; align-items: center; gap: .45rem; }
  .setting-desc  { font-size: .75rem; color: var(--muted); margin-top: .15rem; }
  .setting-bounds{ font-size: .72rem; color: var(--muted); opacity: .7; margin-top: .1rem; }
  .setting-ctrl  { display: flex; align-items: center; gap: .4rem; flex-shrink: 0; }
  .setting-input {
    width: 80px; padding: .3rem .45rem; border-radius: 5px; font-size: .82rem;
    background: var(--surface-2, #1e2030); border: 1px solid var(--border, #2d3148);
    color: var(--text); text-align: right;
  }
  .source-badge {
    font-size: .65rem; padding: .1rem .35rem; border-radius: 3px;
    font-weight: 600; text-transform: uppercase; letter-spacing: .04em;
  }
  .source-default  { background: #1e2030; color: var(--muted); }
  .source-env      { background: #1e2a0e; color: #a6d477; }
  .source-override { background: #1e1e3a; color: #7ec8f5; }
  .env-lock { font-size: .75rem; }

  @media (max-width: 640px) {
    .settings-shell { grid-template-columns: 1fr; }
    .settings-nav { flex-direction: row; flex-wrap: wrap; }
  }
</style>
