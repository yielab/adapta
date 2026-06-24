/**
 * PROOF screenshots: ONE endpoint composing BOTH artifacts — a fine-tune adapter
 * (brand VOICE) and RAG over indexed documents (FACTS, cited). Everyday example:
 * a corner coffee-shop assistant ("Café Luna").
 *
 * LOCAL ONLY. Prereq: run /tmp/demo_combined.sh first (trains a real adapter, indexes
 * a doc, writes /tmp/combined_pid.txt, /tmp/combined_slug.txt, /tmp/combined_key.txt).
 *
 * Run: cd e2e && npx playwright test combined-proof.spec.ts --reporter=line
 * Output: docs/screenshots/combined-proof/*.png
 */

import { test } from "@playwright/test";
import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(__dirname, "..", "docs", "screenshots", "combined-proof");
fs.mkdirSync(OUT, { recursive: true });

const CREDS = { email: "admin@example.com", password: "admin12345" };
const read = (p: string) => (fs.existsSync(p) ? fs.readFileSync(p, "utf8").trim() : "");
const PID = process.env.COMBINED_PID || read("/tmp/combined_pid.txt");

async function login(page: any) {
  await page.goto("http://localhost:8000/console/");
  await page.waitForSelector("#login-email");
  await page.fill("#login-email", CREDS.email);
  await page.fill("#login-password", CREDS.password);
  await page.click('button[type="submit"]');
  await page.waitForSelector(".card.project, .card.empty", { timeout: 20_000 });
}

async function openTab(page: any, tabName: RegExp) {
  await page.goto(`http://localhost:8000/console/#/projects/${PID}`);
  await page.waitForSelector('[role="tablist"]', { timeout: 10_000 });
  await page.getByRole("tab", { name: tabName }).click();
  await page.waitForTimeout(900);
}

// 1. Setup tab, full: BOTH inputs configured — a document indexed (knowledge) AND a
//    dataset trained that passed the gate (behavior). One project holds both.
test("01-setup-knowledge-and-behavior", async ({ page }) => {
  await login(page);
  await openTab(page, /setup/i);
  await page.waitForSelector(".card.gate", { timeout: 15_000 });
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(OUT, "01-setup-knowledge-and-behavior.png"), fullPage: true });
});

// 2. The endpoint header states the composition: base + fine-tuned adapter, gate score.
test("02-endpoint", async ({ page }) => {
  await login(page);
  await openTab(page, /endpoint/i);
  await page.screenshot({ path: path.join(OUT, "02-endpoint.png"), fullPage: true });
});

// 3. THE PAYOFF — one Playground call returns a FACT from the indexed doc (with a
//    citation) wrapped in the fine-tuned brand voice. Knowledge + behavior, one answer.
test("03-combined-answer", async ({ page }) => {
  const slug = read("/tmp/combined_slug.txt");
  const key = read("/tmp/combined_key.txt");
  test.skip(!slug || !key, "no slug/key captured from the demo run");
  await login(page);
  await openTab(page, /playground/i);
  const keyInput = page.locator("#pg-key");
  if (await keyInput.count()) {
    await keyInput.fill(key);
    await page.waitForTimeout(300);
  }
  const input = page.locator("textarea#pg-input").first();
  // A question whose FACT (dog-friendly patio) lives in the indexed doc, asked in a
  // conversational way so the answer also carries the fine-tuned brand sign-off.
  await input.fill("Can I bring my dog?");
  await page.waitForTimeout(200);
  await page.getByRole("button", { name: /send|run/i }).first().click();
  // Retrieval + 3B generation — give it room.
  await page.waitForTimeout(9000);
  await page.screenshot({ path: path.join(OUT, "03-combined-answer.png"), fullPage: true });
});
