// Capture README/slide screenshots from a running deployment (real data, real model output).
//   npm i -D playwright   (or use a global install)  then:
//   node scripts/capture_screenshots.js https://ops.example.com
// Writes PNGs to docs/screenshots/. Run it AFTER the smoke test so every page has content.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const base = (process.argv[2] || "http://localhost:3000").replace(/\/$/, "");
const out = path.join(__dirname, "..", "docs", "screenshots");
fs.mkdirSync(out, { recursive: true });

const pages = [
  ["dashboard", "/"],
  ["requests", "/requests"],
  ["approvals", "/approvals"],
  ["invoices", "/invoices"],
  ["audit", "/audit"],
];

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  for (const [name, p] of pages) {
    await page.goto(base + p, { waitUntil: "networkidle" });
    await page.screenshot({ path: path.join(out, `${name}.png`) });
  }
  // Detail pages: first row of the requests list and the first flagged invoice
  await page.goto(base + "/requests", { waitUntil: "networkidle" });
  await page.locator("tbody a").first().click();
  await page.waitForLoadState("networkidle");
  await page.screenshot({ path: path.join(out, "request-detail.png"), fullPage: true });
  await page.goto(base + "/approvals", { waitUntil: "networkidle" });
  const review = page.locator("text=Review").first();
  if (await review.count()) {
    await review.click();
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: path.join(out, "invoice-detail.png"), fullPage: true });
  }
  await browser.close();
  console.log("Screenshots written to", out);
})();
