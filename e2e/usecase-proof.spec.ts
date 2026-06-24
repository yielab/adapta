/**
 * PROOF screenshots for two more real use cases on the 3B: structured extraction
 * (invoice → JSON) and fixed format / house voice. Completes the use-case gallery
 * alongside finetune-proof (triage classification) and combined-proof (RAG + voice).
 *
 * LOCAL ONLY. Prereq: run /tmp/demo_extraction_format.sh first (writes the pid/slug/key
 * files used below). Run: cd e2e && npx playwright test usecase-proof.spec.ts --reporter=line
 * Output: docs/screenshots/usecase-proof/*.png
 */

import { test } from "@playwright/test";
import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(__dirname, "..", "docs", "screenshots", "usecase-proof");
fs.mkdirSync(OUT, { recursive: true });

const CREDS = { email: "admin@example.com", password: "admin12345" };
const read = (p: string) => (fs.existsSync(p) ? fs.readFileSync(p, "utf8").trim() : "");

const CASES = [
  {
    key: "extraction",
    pid: read("/tmp/ex_pid.txt"),
    apiKey: read("/tmp/ex_key.txt"),
    prompt: "Invoice received from Qorvex for a total of $7700 dollars. Extract the fields.",
  },
  {
    key: "format",
    pid: read("/tmp/fmt_pid.txt"),
    apiKey: read("/tmp/fmt_key.txt"),
    prompt: "How do I connect an integration?",
  },
];

async function login(page: any) {
  await page.goto("http://localhost:8000/console/");
  await page.waitForSelector("#login-email");
  await page.fill("#login-email", CREDS.email);
  await page.fill("#login-password", CREDS.password);
  await page.click('button[type="submit"]');
  await page.waitForSelector(".card.project, .card.empty", { timeout: 20_000 });
}

async function openTab(page: any, pid: string, tabName: RegExp) {
  await page.goto(`http://localhost:8000/console/#/projects/${pid}`);
  await page.waitForSelector('[role="tablist"]', { timeout: 10_000 });
  await page.getByRole("tab", { name: tabName }).click();
  await page.waitForTimeout(900);
}

for (const c of CASES) {
  test(`${c.key}-gate`, async ({ page }) => {
    test.skip(!c.pid, `no pid for ${c.key}`);
    await login(page);
    await openTab(page, c.pid, /setup/i);
    const gate = page.locator(".card.gate");
    await gate.waitFor({ timeout: 15_000 });
    await gate.scrollIntoViewIfNeeded();
    await page.waitForTimeout(400);
    await gate.screenshot({ path: path.join(OUT, `${c.key}-gate.png`) });
  });

  test(`${c.key}-playground`, async ({ page }) => {
    test.skip(!c.pid || !c.apiKey, `no pid/key for ${c.key}`);
    await login(page);
    await openTab(page, c.pid, /playground/i);
    const keyInput = page.locator("#pg-key");
    if (await keyInput.count()) {
      await keyInput.fill(c.apiKey);
      await page.waitForTimeout(300);
    }
    await page.locator("textarea#pg-input").first().fill(c.prompt);
    await page.waitForTimeout(200);
    await page.getByRole("button", { name: /send|run/i }).first().click();
    // 3B served on CPU — give the generation room before the snapshot.
    await page.waitForTimeout(15_000);
    await page.screenshot({ path: path.join(OUT, `${c.key}-playground.png`), fullPage: true });
  });
}
