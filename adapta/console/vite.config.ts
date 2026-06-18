import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// The console is served same-origin by FastAPI StaticFiles under /console/,
// so all built asset URLs must be prefixed with that base. In `vite dev`,
// /v1 and /health are proxied to the running app so there is still no CORS.
export default defineConfig({
  base: "/console/",
  plugins: [svelte()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/v1": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
