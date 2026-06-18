<script lang="ts">
  import { api, ApiError } from "../lib/api";
  import { setToken, setUser } from "../lib/session";
  import { navigate } from "../lib/router";
  import { toastError } from "../lib/toast";
  import Spinner from "../components/Spinner.svelte";
  import Logo from "../components/Logo.svelte";

  type Tab = "login" | "register";

  let tab = $state<Tab>("login");
  let pending = $state(false);

  // Login fields
  let loginEmail = $state("");
  let loginPassword = $state("");

  // Register fields
  let orgName = $state("");
  let regEmail = $state("");
  let regPassword = $state("");

  // Inline notice (e.g. "email already registered — sign in").
  let notice = $state("");

  const loginValid = $derived(loginEmail.trim() !== "" && loginPassword !== "");
  const registerValid = $derived(
    orgName.trim() !== "" && regEmail.trim() !== "" && regPassword.length >= 8,
  );

  function switchTab(next: Tab) {
    if (pending) return;
    tab = next;
    if (next !== "register") notice = "";
  }

  // Shared finish: token already obtained → fetch user → land on projects.
  async function finishWithToken(token: string) {
    setToken(token);
    const user = await api.me();
    setUser(user);
    navigate("/projects");
  }

  async function doLogin() {
    if (!loginValid || pending) return;
    pending = true;
    try {
      const { access_token } = await api.login(loginEmail.trim(), loginPassword);
      await finishWithToken(access_token);
    } catch (e) {
      if (e instanceof ApiError) toastError(e.message, e.correlationId);
      else toastError("Sign-in failed. Please try again.");
    } finally {
      pending = false;
    }
  }

  async function doRegister() {
    if (!registerValid || pending) return;
    pending = true;
    notice = "";
    try {
      await api.register(orgName.trim(), regEmail.trim(), regPassword);
      // Bootstrap succeeded → auto-login with the same credentials.
      const { access_token } = await api.login(regEmail.trim(), regPassword);
      await finishWithToken(access_token);
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.code === "conflict") {
          // Registration is open — the only conflict is an email that already
          // has an account. Send the operator to sign-in with it prefilled.
          notice = "That email is already registered — sign in instead.";
          loginEmail = regEmail.trim();
          tab = "login";
        } else {
          toastError(e.message, e.correlationId);
        }
      } else {
        toastError("Registration failed. Please try again.");
      }
    } finally {
      pending = false;
    }
  }
</script>

<div class="wrap">
  <div class="card" style="max-width: 380px; width: 100%;">
    <div class="hero">
      <Logo size={44} />
      <div>
        <h1><span class="brain">Brain</span> <span class="cero">From Cero</span></h1>
        <p class="tagline">Your model. Your data. Your servers.</p>
      </div>
    </div>

    <div class="tabs" role="tablist">
      <button
        class="tab"
        class:active={tab === "login"}
        role="tab"
        aria-selected={tab === "login"}
        onclick={() => switchTab("login")}
      >
        Sign in
      </button>
      <button
        class="tab"
        class:active={tab === "register"}
        role="tab"
        aria-selected={tab === "register"}
        onclick={() => switchTab("register")}
      >
        Register
      </button>
    </div>

    {#if notice}
      <div class="muted-box" style="margin-bottom: 14px; color: var(--amber); border-color: var(--amber);">
        {notice}
      </div>
    {/if}

    {#if tab === "login"}
      <form onsubmit={(e) => { e.preventDefault(); doLogin(); }}>
        <div class="field">
          <label for="login-email">Email</label>
          <input
            id="login-email"
            type="email"
            autocomplete="username"
            bind:value={loginEmail}
            disabled={pending}
          />
        </div>
        <div class="field">
          <label for="login-password">Password</label>
          <input
            id="login-password"
            type="password"
            autocomplete="current-password"
            bind:value={loginPassword}
            disabled={pending}
          />
        </div>
        <button type="submit" class="primary" style="width: 100%;" disabled={!loginValid || pending}>
          {#if pending}<Spinner label="Signing in…" />{:else}Sign in{/if}
        </button>
      </form>
    {:else}
      <form onsubmit={(e) => { e.preventDefault(); doRegister(); }}>
        <div class="field">
          <label for="reg-org">Organization name</label>
          <input
            id="reg-org"
            type="text"
            autocomplete="organization"
            bind:value={orgName}
            disabled={pending}
          />
        </div>
        <div class="field">
          <label for="reg-email">Admin email</label>
          <input
            id="reg-email"
            type="email"
            autocomplete="username"
            bind:value={regEmail}
            disabled={pending}
          />
        </div>
        <div class="field">
          <label for="reg-password">Password</label>
          <input
            id="reg-password"
            type="password"
            autocomplete="new-password"
            bind:value={regPassword}
            disabled={pending}
          />
          <small>At least 8 characters.</small>
        </div>
        <button type="submit" class="primary" style="width: 100%;" disabled={!registerValid || pending}>
          {#if pending}<Spinner label="Creating…" />{:else}Create organization{/if}
        </button>
        <p class="muted" style="margin: 12px 0 0; font-size: 12.5px;">
          Creates your organization with you as its admin. Teammates join an
          existing organization through an admin invite.
        </p>
      </form>
    {/if}
  </div>
</div>

<style>
  .wrap {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
  }
  .hero {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 22px;
  }
  .hero h1 {
    font-family: var(--display);
    font-size: 20px;
    font-weight: 700;
    margin: 0 0 3px;
    line-height: 1.2;
    letter-spacing: -0.01em;
  }
  .brain  { color: var(--text); }
  .cero   { color: var(--muted); font-weight: 500; }
  .tagline {
    margin: 0;
    font-size: 12.5px;
    color: var(--muted);
    letter-spacing: 0.01em;
  }
  /* center Spinner label inside the full-width primary button */
  button.primary :global(.row) {
    justify-content: center;
  }
</style>
