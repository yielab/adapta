/**
 * PROOF screenshots: a REAL fine-tune that trained on the live GPU worker and
 * passed the eval gate, captured straight from the operator console.
 *
 * LOCAL ONLY. Prereq: run /tmp/demo_finetune.sh first (it trains a real adapter
 * and writes /tmp/demo_pid.txt, /tmp/demo_slug.txt, /tmp/demo_key.txt).
 *
 * Run: cd e2e && npx playwright test finetune-proof.spec.ts --reporter=line
 * Output: docs/screenshots/finetune-proof/*.png  (1440×900, dark theme)
 */

import { test } from "@playwright/test";
import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(__dirname, "..", "docs", "screenshots", "finetune-proof");
fs.mkdirSync(OUT, { recursive: true });

const CREDS = { email: "admin@example.com", password: "admin12345" };
const read = (p: string) => (fs.existsSync(p) ? fs.readFileSync(p, "utf8").trim() : "");
const PID = process.env.DEMO_PID || read("/tmp/demo_pid.txt");

async function login(page: any) {
  await page.goto("http://localhost:8000/console/");
  await page.waitForSelector("#login-email");
  await page.fill("#login-email", CREDS.email);
  await page.fill("#login-password", CREDS.password);
  await page.click('button[type="submit"]');
  await page.waitForSelector(".card.project, .card.empty", { timeout: 20_000 });
}

async function openProjectTab(page: any, tabName: RegExp) {
  await page.goto(`http://localhost:8000/console/#/projects/${PID}`);
  await page.waitForSelector('[role="tablist"]', { timeout: 10_000 });
  await page.getByRole("tab", { name: tabName }).click();
  await page.waitForTimeout(900);
}

// 1. The whole fine-tune flow in one tall shot: dataset valid → job succeeded →
//    EVAL GATE PASSED (with the real score) → Serve. This is the proof.
test("01-finetune-flow-full", async ({ page }) => {
  await login(page);
  await openProjectTab(page, /setup/i);
  // Wait until the gate card has rendered its verdict.
  await page.waitForSelector(".card.gate", { timeout: 15_000 });
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(OUT, "01-finetune-flow-full.png"), fullPage: true });
});

// 2. Close-up of just the EVAL GATE card — the PASSED badge + the real score.
test("02-eval-gate-card", async ({ page }) => {
  await login(page);
  await openProjectTab(page, /setup/i);
  const gate = page.locator(".card.gate");
  await gate.waitFor({ timeout: 15_000 });
  await gate.scrollIntoViewIfNeeded();
  await page.waitForTimeout(400);
  await gate.screenshot({ path: path.join(OUT, "02-eval-gate-card.png") });
});

// 3. Close-up of the fine-tune JOB row — succeeded, with its eval score.
test("03-job-succeeded", async ({ page }) => {
  await login(page);
  await openProjectTab(page, /setup/i);
  // The job table card — pinpoint it by its "3 · Fine-tune job" heading so we don't
  // match the explainer card (whose prose also mentions "fine-tune job").
  const jobCard = page
    .locator(".card")
    .filter({ has: page.getByRole("heading", { name: /Fine-tune job/i }) })
    .first();
  await jobCard.waitFor({ timeout: 15_000 });
  await jobCard.scrollIntoViewIfNeeded();
  await page.waitForTimeout(400);
  await jobCard.screenshot({ path: path.join(OUT, "03-job-succeeded.png") });
});

// 4. Overview tab — the pipeline steps, now all green through "served".
test("04-overview", async ({ page }) => {
  await login(page);
  await openProjectTab(page, /overview/i);
  await page.screenshot({ path: path.join(OUT, "04-overview.png"), fullPage: true });
});

// 5. Endpoint & keys tab — the live serving endpoint born from the passed gate.
test("05-endpoint", async ({ page }) => {
  await login(page);
  await openProjectTab(page, /endpoint/i);
  await page.screenshot({ path: path.join(OUT, "05-endpoint.png"), fullPage: true });
});

// 6. Playground — send a HELD-OUT ticket through the trained adapter and capture
//    the model returning the learned label. Best-effort (needs slug + key files).
test("06-playground-inference", async ({ page }) => {
  const slug = read("/tmp/demo_slug.txt");
  const key = read("/tmp/demo_key.txt");
  test.skip(!slug || !key, "no slug/key captured from the demo run");
  await login(page);
  await openProjectTab(page, /playground/i);
  // Enter the scoped key.
  const keyInput = page.locator("#pg-key");
  if (await keyInput.count()) {
    await keyInput.fill(key);
    await page.waitForTimeout(300);
  }
  // The Playground composer has no separate system field, so send a self-contained
  // message: the routing instruction + a ticket the model never trained on verbatim.
  // The trained adapter replies with just the learned label.
  const input = page.locator("textarea#pg-input").first();
  await input.fill(
    "Classify the support message into exactly one of: billing, technical, account. " +
      "Reply with only the label.\n\n" +
      "My card was declined but I was still charged — what happened?",
  );
  await page.waitForTimeout(200);
  // Send (button labelled Send / Run).
  await page.getByRole("button", { name: /send|run/i }).first().click();
  // Wait for an assistant bubble to appear.
  await page.waitForTimeout(4000);
  await page.screenshot({ path: path.join(OUT, "06-playground-inference.png"), fullPage: true });
});
