import { readable } from "svelte/store";

// Minimal hash router. Hash routing means StaticFiles never needs a SPA
// fallback — every deep link (#/projects/abc) loads index.html and the app
// resolves the route client-side.
export interface Route {
  path: string; // e.g. "/projects/123"
  parts: string[]; // e.g. ["projects", "123"]
}

function parse(): Route {
  const raw = location.hash.replace(/^#/, "") || "/";
  const path = raw.startsWith("/") ? raw : "/" + raw;
  const parts = path.split("/").filter(Boolean);
  return { path, parts };
}

export const route = readable<Route>(parse(), (set) => {
  const handler = () => set(parse());
  window.addEventListener("hashchange", handler);
  return () => window.removeEventListener("hashchange", handler);
});

export function navigate(path: string) {
  const target = path.startsWith("/") ? path : "/" + path;
  if (location.hash !== "#" + target) {
    location.hash = target;
  } else {
    // Same hash — force a re-read (e.g. after delete + re-navigate to same list).
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  }
}
