/**
 * PROOF screenshots for the image-understanding (OCR) path: a vision fine-tune that
 * reads invoice IMAGES and extracts {vendor, total} as JSON. Captures the console's
 * image-bundle upload + eval gate and the vision Playground serving an attached image.
 *
 * LOCAL ONLY. Prereq: run /tmp/ocr_demo.py (writes data/ocr_{pid,slug,key}.txt and
 * data/ocr_probe.png). Run: cd e2e && npx playwright test vision-proof.spec.ts --reporter=line
 * Output: docs/screenshots/vision-proof/*.png
 */

import { test } from "@playwright/test";
import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(__dirname, "..", "docs", "screenshots", "vision-proof");
fs.mkdirSync(OUT, { recursive: true });
const DATA = path.join(__dirname, "..", "data");
const read = (p: string) => (fs.existsSync(p) ? fs.readFileSync(p, "utf8").trim() : "");

const CREDS = { email: "admin@example.com", password: "admin12345" };
const PID = read(path.join(DATA, "ocr_pid.txt"));
const KEY = read(path.join(DATA, "ocr_key.txt"));
const PROBE = path.join(DATA, "ocr_probe.png");

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

// 1. Setup: the image bundle uploaded (modality vision) and the eval gate PASSED.
test("01-vision-setup", async ({ page }) => {
  test.skip(!PID, "no ocr pid");
  await login(page);
  await openTab(page, /setup/i);
  await page.waitForSelector(".card.gate", { timeout: 15_000 });
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(OUT, "01-vision-setup.png"), fullPage: true });
});

// 2. Close-up of the eval gate for the vision adapter.
test("02-vision-gate", async ({ page }) => {
  test.skip(!PID, "no ocr pid");
  await login(page);
  await openTab(page, /setup/i);
  const gate = page.locator(".card.gate");
  await gate.waitFor({ timeout: 15_000 });
  await gate.scrollIntoViewIfNeeded();
  await page.waitForTimeout(400);
  await gate.screenshot({ path: path.join(OUT, "02-vision-gate.png") });
});

// 3. THE PAYOFF — attach a held-out invoice IMAGE in the Playground and watch the
//    fine-tuned VLM read it and return the trained JSON.
test("03-vision-playground-ocr", async ({ page }) => {
  test.skip(!PID || !KEY, "no ocr pid/key");
  test.setTimeout(180_000); // VL-3B + mmproj served on CPU — image inference is slow.
  await login(page);
  await openTab(page, /playground/i);
  const keyInput = page.locator("#pg-key");
  if (await keyInput.count()) {
    await keyInput.fill(KEY);
    await page.waitForTimeout(300);
  }
  // Attach the invoice image (hidden file input; setInputFiles fires onImagePicked).
  await page.locator("#pg-image").setInputFiles(PROBE);
  await page.waitForTimeout(800);
  await page
    .locator("textarea#pg-input")
    .first()
    .fill("Extract the vendor and total from this invoice as JSON.");
  await page.waitForTimeout(200);
  await page.getByRole("button", { name: /send|run/i }).first().click();
  // Wait for the response to complete — the usage badges ("completion N") render only
  // after the answer arrives — then snapshot.
  await page.getByText(/completion \d/).first().waitFor({ timeout: 150_000 });
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(OUT, "03-vision-playground-ocr.png"), fullPage: true });
});
