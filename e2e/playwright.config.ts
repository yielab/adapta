import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: ["screenshots.spec.ts", "hero-gif.spec.ts", "finetune-proof.spec.ts", "combined-proof.spec.ts", "usecase-proof.spec.ts", "vision-proof.spec.ts"],
  timeout: 60_000,
  retries: 0,
  workers: 1,
  use: {
    baseURL: "http://localhost:8000",
    // App is dark-only (tokens.css has no prefers-color-scheme:light overrides).
    colorScheme: "dark",
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: true,
    // Slow down interactions so video recording looks intentional.
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        // Override Desktop Chrome's default 1280×720 with our target resolution.
        viewport: { width: 1440, height: 900 },
      },
    },
  ],
});
