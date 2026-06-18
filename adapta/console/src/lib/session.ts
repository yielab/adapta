import { writable } from "svelte/store";
import type { User, TeamSummary } from "./types";

const TOKEN_KEY = "adapta_console_token";

interface SessionState {
  token: string | null;
  user: User | null;
  activeTeam: TeamSummary | null;
}

function load(): SessionState {
  const token = sessionStorage.getItem(TOKEN_KEY);
  return { token, user: null, activeTeam: null };
}

export const session = writable<SessionState>(load());

export function setToken(token: string) {
  sessionStorage.setItem(TOKEN_KEY, token);
  session.update((s) => ({ ...s, token }));
}

export function setUser(user: User) {
  session.update((s) => ({
    ...s,
    user,
    // Default to the user's first team (most operators have the single "default").
    activeTeam: s.activeTeam ?? user.teams[0] ?? null,
  }));
}

export function setActiveTeam(team: TeamSummary) {
  session.update((s) => ({ ...s, activeTeam: team }));
}

export function clearSession() {
  sessionStorage.removeItem(TOKEN_KEY);
  session.set({ token: null, user: null, activeTeam: null });
}

let _token: string | null = null;
session.subscribe((s) => (_token = s.token));
export const getToken = () => _token;
