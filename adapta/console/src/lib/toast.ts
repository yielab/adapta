import { writable } from "svelte/store";

export interface Toast {
  id: number;
  kind: "error" | "success" | "info";
  message: string;
  correlationId?: string;
}

export const toasts = writable<Toast[]>([]);

let nextId = 1;

export function pushToast(t: Omit<Toast, "id">, ttlMs = 6000) {
  const id = nextId++;
  toasts.update((list) => [...list, { ...t, id }]);
  if (ttlMs > 0) {
    setTimeout(() => dismissToast(id), ttlMs);
  }
}

export function dismissToast(id: number) {
  toasts.update((list) => list.filter((t) => t.id !== id));
}

export const toastError = (message: string, correlationId?: string) =>
  pushToast({ kind: "error", message, correlationId }, 0); // errors stay until dismissed
export const toastSuccess = (message: string) => pushToast({ kind: "success", message });
export const toastInfo = (message: string) => pushToast({ kind: "info", message });
