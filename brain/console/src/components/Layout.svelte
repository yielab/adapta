<script lang="ts">
  import type { Snippet } from "svelte";
  import { session, setActiveTeam, clearSession } from "../lib/session";
  import { route, navigate } from "../lib/router";
  import type { TeamSummary } from "../lib/types";
  import Logo from "./Logo.svelte";

  let { children }: { children?: Snippet } = $props();

  const user = $derived($session.user);
  const teams = $derived(user?.teams ?? []);
  const activeTeam = $derived($session.activeTeam);

  // Highlight nav items by active route prefix.
  const onProjects = $derived($route.path === "/projects" || $route.parts[0] === "projects");
  const onModels   = $derived($route.parts[0] === "models");
  const onSettings = $derived($route.parts[0] === "settings");

  function onTeamChange(e: Event) {
    const id = (e.currentTarget as HTMLSelectElement).value;
    const team = teams.find((t: TeamSummary) => t.id === id);
    if (team) {
      setActiveTeam(team);
      // Team scopes the project list — bounce back to it so the view reloads.
      navigate("/projects");
    }
  }

  function logout() {
    clearSession();
    navigate("/login");
  }
</script>

<div class="shell">
  <aside class="sidebar">
    <a href="#/projects" class="brand" aria-label="Brain From Cero — home">
      <Logo size={22} />
      <span class="wordmark">Brain <span class="sub">From Cero</span></span>
    </a>
    <nav class="stack">
      <a href="#/projects" class="navlink" class:active={onProjects}>Projects</a>
      <a href="#/models"   class="navlink" class:active={onModels}>Models</a>
      <a href="#/settings" class="navlink" class:active={onSettings}>Settings</a>
    </nav>
  </aside>

  <div class="main">
    <header class="topbar row between">
      <div class="row" style="gap: 10px;">
        {#if teams.length > 1}
          <label class="teamlabel" for="team-switcher">Team</label>
          <select id="team-switcher" class="team" value={activeTeam?.id ?? ""} onchange={onTeamChange}>
            {#each teams as t (t.id)}
              <option value={t.id}>{t.name}</option>
            {/each}
          </select>
        {:else if activeTeam}
          <span class="badge blue"><span class="dot"></span>{activeTeam.name}</span>
        {/if}
      </div>

      <div class="row" style="gap: 12px;">
        {#if user}
          <span class="chip mono">{user.email}</span>
        {/if}
        <button class="ghost sm" onclick={logout}>Log out</button>
      </div>
    </header>

    <main class="content">
      {@render children?.()}
    </main>
  </div>
</div>

<style>
  .shell {
    display: grid;
    grid-template-columns: 220px 1fr;
    min-height: 100vh;
  }
  .sidebar {
    background: var(--panel);
    border-right: 1px solid var(--border);
    padding: 20px 16px;
    display: flex;
    flex-direction: column;
    gap: 22px;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 9px;
    text-decoration: none;
  }
  .brand:hover { text-decoration: none; }
  .wordmark {
    font-family: var(--display);
    font-weight: 700;
    font-size: 15px;
    color: var(--text);
    line-height: 1.2;
    letter-spacing: -0.01em;
  }
  .wordmark .sub { color: var(--muted); font-weight: 500; }
  .navlink {
    display: block;
    padding: 8px 10px;
    border-radius: 8px;
    color: var(--muted);
    text-decoration: none;
  }
  .navlink:hover { color: var(--text); background: var(--panel-2); text-decoration: none; }
  .navlink.active { color: var(--text); background: var(--accent-weak); border: 1px solid var(--accent); }

  .main { display: flex; flex-direction: column; min-width: 0; }
  .topbar {
    border-bottom: 1px solid var(--border);
    padding: 12px 22px;
    background: var(--panel);
  }
  .teamlabel { margin: 0; }
  .team { width: auto; min-width: 140px; padding: 6px 10px; }
  .chip {
    font-size: 12.5px;
    color: var(--muted);
    background: var(--panel-2);
    border: 1px solid var(--border);
    padding: 5px 10px;
    border-radius: 20px;
  }
  .content {
    padding: 24px 22px;
    max-width: 1100px;
    width: 100%;
  }

  @media (max-width: 720px) {
    .shell { grid-template-columns: 1fr; }
    .sidebar {
      flex-direction: row;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 16px;
    }
    .sidebar nav { display: flex; }
    .chip { display: none; }
  }
</style>
