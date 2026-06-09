<script lang="ts">
  import { route, navigate } from "./lib/router";
  import { session, setUser, clearSession, getToken } from "./lib/session";
  import { api } from "./lib/api";

  import Layout from "./components/Layout.svelte";
  import Toasts from "./components/Toasts.svelte";

  import Login from "./views/Login.svelte";
  import Projects from "./views/Projects.svelte";
  import Project from "./views/Project.svelte";

  // Hydration: on first load a token may live in sessionStorage but the user
  // object does not (it isn't persisted). Re-fetch it; on failure the session is
  // stale → clear it and the guard sends the operator to /login.
  let hydrating = $state(false);
  let hydrated = $state(false);

  $effect(() => {
    if (hydrated || hydrating) return;
    const token = getToken();
    if (!token) {
      hydrated = true;
      return;
    }
    hydrating = true;
    api
      .me()
      .then((u) => setUser(u))
      .catch(() => clearSession())
      .finally(() => {
        hydrating = false;
        hydrated = true;
      });
  });

  const authed = $derived(!!$session.token);
  const path = $derived($route.path);
  const parts = $derived($route.parts);

  // Auth guard: unauthenticated → only /login is reachable.
  $effect(() => {
    if (!hydrated) return;
    if (!authed && path !== "/login") {
      navigate("/login");
    } else if (authed && path === "/login") {
      // Already signed in — don't sit on the login screen.
      navigate("/projects");
    }
  });

  // Resolve the routed view + any params. Default route is the project list.
  const view = $derived.by(() => {
    if (path === "/login") return { kind: "login" as const };
    if (parts[0] === "projects" && parts[1]) return { kind: "project" as const, id: parts[1] };
    if (parts[0] === "projects" || path === "/") return { kind: "projects" as const };
    return { kind: "projects" as const };
  });
</script>

{#if !hydrated || hydrating}
  <div class="boot">
    <span class="spinner"></span>
  </div>
{:else if !authed || view.kind === "login"}
  <Login />
{:else}
  <Layout>
    {#if view.kind === "project"}
      <Project id={view.id} />
    {:else}
      <Projects />
    {/if}
  </Layout>
{/if}

<Toasts />

<style>
  .boot {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
  }
</style>
