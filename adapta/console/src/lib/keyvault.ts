import { writable } from "svelte/store";

// The full adp_ secret is shown by the server exactly once (on creation). The
// console never persists it (no localStorage), but we hold the most-recent one
// in memory for the lifetime of the tab so the Playground can prefill it right
// after you generate a key in the Endpoint tab. Keyed by project so we never
// hand one project's secret to another.
interface VaultEntry {
  projectId: string;
  key: string; // full adp_ secret
  name: string;
}

export const lastCreatedKey = writable<VaultEntry | null>(null);

export function rememberKey(projectId: string, name: string, key: string) {
  lastCreatedKey.set({ projectId, name, key });
}

let _entry: VaultEntry | null = null;
lastCreatedKey.subscribe((v) => (_entry = v));

// Returns the remembered full secret for this project, if we still hold one.
export function getRememberedKey(projectId: string): string | null {
  return _entry && _entry.projectId === projectId ? _entry.key : null;
}
