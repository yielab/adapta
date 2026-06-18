/**
 * Hero GIF capture — records a guided walkthrough and converts webm → GIF.
 *
 * LOCAL ONLY. Not part of CI. Run with: make gif
 * Requires: stack up (make up), Playwright browsers installed, ffmpeg on PATH.
 *
 * Output:
 *   docs/screenshots/hero.gif  (~2 MB, 8 fps, 1000 px wide)
 *
 * Sequence:
 *   (a) Projects list with seeded data
 *   (b) Open a project — meaningful navigation interaction
 *   (c) Switch to Endpoint tab
 *   (d) Navigate to Models catalog (the "discovery" view)
 *   (e) Open Settings panel
 */

import { test, expect } from "@playwright/test";
import path from "path";
import { fileURLToPath } from "url";
import { execSync } from "child_process";
import fs from "fs";
import { seedDemoData } from "./seed.js";
import type { SeedResult } from "./seed.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(__dirname, "..", "docs", "screenshots");
const VIDEOS_DIR = path.join(__dirname, "videos");

const CREDS = { email: "admin@example.com", password: "admin12345" };

let seed: SeedResult;

test.beforeAll(async () => {
  // Re-use data seeded by screenshots run if it already exists, otherwise seed.
  // Since seed.ts is idempotent (it just creates more projects on top of
  // existing ones), always call it — extra projects on the list look realistic.
  seed = await seedDemoData();
  fs.mkdirSync(VIDEOS_DIR, { recursive: true });
  fs.mkdirSync(OUT, { recursive: true });
});

test("hero-gif", async ({ browser }) => {
  // Record at 1000 px wide so the GIF command's scale=1000:-2 is a no-op.
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    colorScheme: "dark",
    recordVideo: {
      dir: VIDEOS_DIR,
      size: { width: 1440, height: 900 },
    },
  });
  const page = await context.newPage();

  // ── (a) Show the main view with data ──────────────────────────────────────
  await page.goto("http://localhost:8000/console/");
  await page.waitForSelector("#login-email");
  await page.fill("#login-email", CREDS.email);
  await page.fill("#login-password", CREDS.password);
  await page.waitForTimeout(400);
  await page.click('button[type="submit"]');
  // Wait for project cards to appear
  await page.waitForSelector(".card.project", { timeout: 15_000 });
  // Let the user absorb the projects view
  await page.waitForTimeout(1800);

  // ── (b) Meaningful interaction — open the RAG project ─────────────────────
  // Hover over the card first so there's a visible state change.
  // Find the "Support Knowledge Base" card (it's the Live RAG project).
  const ragCard = page.locator(".card.project.rag").first();
  await ragCard.hover();
  await page.waitForTimeout(600);
  // Click the Open button on that card.
  await ragCard.locator('button:has-text("Open")').click();
  // Wait for the project detail tab bar (role=tablist is only in Project.svelte).
  await page.waitForSelector('[role="tablist"]', { timeout: 10_000 });
  // Let the setup tab settle with its file list visible.
  await page.waitForTimeout(1600);

  // ── (c) Switch to Endpoint tab ────────────────────────────────────────────
  await page.getByRole("tab", { name: /endpoint/i }).click();
  await page.waitForTimeout(1600);

  // ── (d) Navigate to Models catalog ───────────────────────────────────────
  await page.getByRole("link", { name: "Models" }).click();
  await page.waitForSelector(".models-page, h1", { timeout: 10_000 });
  await page.waitForTimeout(1600);

  // ── (e) Open Settings panel ───────────────────────────────────────────────
  await page.getByRole("link", { name: "Settings" }).click();
  await page.waitForSelector("h1", { timeout: 10_000 });
  // Click Platform tab to show config values (admin-only).
  await page.getByRole("button", { name: "Platform" }).click().catch(() => {});
  await page.waitForTimeout(1800);

  // Close the context to flush the video to disk.
  await context.close();

  // ── Convert webm → GIF ────────────────────────────────────────────────────
  // Find the video that was just written (newest file in VIDEOS_DIR).
  const files = fs
    .readdirSync(VIDEOS_DIR)
    .filter((f) => f.endsWith(".webm"))
    .map((f) => ({ f, mtime: fs.statSync(path.join(VIDEOS_DIR, f)).mtimeMs }))
    .sort((a, b) => b.mtime - a.mtime);

  expect(files.length).toBeGreaterThan(0);
  const videoPath = path.join(VIDEOS_DIR, files[0].f);
  const palettePath = path.join(VIDEOS_DIR, "palette.png");
  const gifPath = path.join(OUT, "hero.gif");

  console.log(`\nConverting ${videoPath} → ${gifPath}`);

  // Two-pass palette GIF per the spec.
  execSync(
    `ffmpeg -y -ss 1.5 -i "${videoPath}" ` +
      `-vf "fps=8,scale=1000:-2:flags=lanczos,palettegen=stats_mode=diff" "${palettePath}"`,
    { stdio: "inherit" },
  );
  execSync(
    `ffmpeg -y -ss 1.5 -i "${videoPath}" -i "${palettePath}" ` +
      `-filter_complex "[0:v] fps=8,scale=1000:-2:flags=lanczos [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" "${gifPath}"`,
    { stdio: "inherit" },
  );

  const gifSize = fs.statSync(gifPath).size;
  console.log(`GIF size: ${(gifSize / 1024 / 1024).toFixed(1)} MB`);

  expect(fs.existsSync(gifPath)).toBe(true);
  expect(gifSize).toBeGreaterThan(50_000); // at least 50 KB
});
