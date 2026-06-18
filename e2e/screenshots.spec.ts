/**
 * Static screenshot capture — one PNG per major console view.
 *
 * LOCAL ONLY. Not part of CI. Run with: make screenshots
 * Requires: stack up (make up), Playwright browsers installed.
 *
 * Output: docs/screenshots/*.png  (1440×900, dark theme)
 */

import { test, expect } from "@playwright/test";
import path from "path";
import { fileURLToPath } from "url";
import { seedDemoData } from "./seed.js";
import type { SeedResult } from "./seed.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(__dirname, "..", "docs", "screenshots");

const CREDS = { email: "admin@example.com", password: "admin12345" };

// Seed once per suite run; share IDs across all tests.
let seed: SeedResult;

test.beforeAll(async () => {
  seed = await seedDemoData();
});

// Helper: log in through the UI and land on the Projects list.
async function login(page: Parameters<typeof test.fn>[0]["page"]) {
  await page.goto("http://localhost:8000/console/");
  await page.waitForSelector("#login-email");
  await page.fill("#login-email", CREDS.email);
  await page.fill("#login-password", CREDS.password);
  await page.click('button[type="submit"]');
  // Wait for the Projects view — confirms login completed and the SPA routed.
  await page.waitForSelector(".card.project, .card.empty", { timeout: 20_000 });
}

// Helper: navigate to a project detail and wait for its tab bar.
async function openProject(
  page: Parameters<typeof test.fn>[0]["page"],
  projectId: string,
) {
  await page.goto(`http://localhost:8000/console/#/projects/${projectId}`);
  // Confirm the project detail rendered (h1 inside main, not the login h2).
  // The project detail shows a back-button row + project name h1.
  await page.waitForSelector("button.ghost.sm", { timeout: 10_000 }); // "← Projects" btn
  await page.waitForSelector('[role="tablist"]', { timeout: 10_000 });
  // Small stabilisation pause.
  await page.waitForTimeout(400);
}

// ── 1. Login page ──────────────────────────────────────────────────────────
test("login", async ({ page }) => {
  await page.goto("http://localhost:8000/console/");
  await page.waitForSelector("#login-email");
  // Brief pause so fonts load
  await page.waitForTimeout(800);
  await page.screenshot({
    path: path.join(OUT, "login.png"),
    fullPage: false,
  });
});

// ── 2. Projects list ───────────────────────────────────────────────────────
test("projects", async ({ page }) => {
  await login(page);
  // Wait for cards to render (the grid with project cards)
  await page.waitForSelector(".card.project", { timeout: 15_000 });
  await page.waitForTimeout(600);
  await page.screenshot({
    path: path.join(OUT, "projects.png"),
    fullPage: false,
  });
});

// ── 3. RAG project — setup tab ─────────────────────────────────────────────
test("project-rag-setup", async ({ page }) => {
  await login(page);
  await openProject(page, seed.ragProjectId);
  // Setup is the default tab; wait for the file list to settle.
  await page.waitForTimeout(800);
  await page.screenshot({
    path: path.join(OUT, "project-rag-setup.png"),
    fullPage: false,
  });
});

// ── 4. RAG project — endpoint & keys tab ──────────────────────────────────
test("project-rag-endpoint", async ({ page }) => {
  await login(page);
  await openProject(page, seed.ragProjectId);
  await page.getByRole("tab", { name: /endpoint/i }).click();
  await page.waitForTimeout(1000);
  await page.screenshot({
    path: path.join(OUT, "project-rag-endpoint.png"),
    fullPage: false,
  });
});

// ── 5. RAG project — playground tab ───────────────────────────────────────
test("project-rag-playground", async ({ page }) => {
  await login(page);
  await openProject(page, seed.ragProjectId);
  await page.getByRole("tab", { name: "Playground" }).click();
  await page.waitForTimeout(800);
  await page.screenshot({
    path: path.join(OUT, "project-rag-playground.png"),
    fullPage: false,
  });
});

// ── 6. Fine-tune project — setup tab (dataset uploaded) ───────────────────
test("project-finetune-setup", async ({ page }) => {
  await login(page);
  await openProject(page, seed.finetuneProjectId);
  await page.waitForTimeout(800);
  await page.screenshot({
    path: path.join(OUT, "project-finetune-setup.png"),
    fullPage: false,
  });
});

// ── 7. Models catalog ─────────────────────────────────────────────────────
test("models", async ({ page }) => {
  await login(page);
  await page.goto("http://localhost:8000/console/#/models");
  await page.waitForSelector(".models-page, h1", { timeout: 10_000 });
  await page.waitForTimeout(600);
  await page.screenshot({
    path: path.join(OUT, "models.png"),
    fullPage: false,
  });
});

// ── 8. Settings — platform tab ────────────────────────────────────────────
test("settings", async ({ page }) => {
  await login(page);
  await page.goto("http://localhost:8000/console/#/settings");
  await page.waitForSelector("h1", { timeout: 10_000 });
  // Click Platform tab (admin-only)
  await page.click('button:has-text("Platform")').catch(() => {});
  await page.waitForTimeout(600);
  await page.screenshot({
    path: path.join(OUT, "settings.png"),
    fullPage: false,
  });
});

// ── 9. Project overview (the pipeline steps card) ─────────────────────────
test("project-overview", async ({ page }) => {
  await login(page);
  await openProject(page, seed.ragProjectId);
  await page.getByRole("tab", { name: "Overview" }).click();
  await page.waitForTimeout(800);
  await page.screenshot({
    path: path.join(OUT, "project-overview.png"),
    fullPage: false,
  });
});
