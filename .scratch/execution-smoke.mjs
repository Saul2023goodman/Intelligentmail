import { createRequire } from "node:module";
const require = createRequire("C:/Users/Zeng/AppData/Local/npm-cache/_npx/31e32ef8478fbf80/node_modules/");
const { chromium } = require("playwright");

const ORIGIN = "http://127.0.0.1:5179";
async function core(command, args = {}) {
  const response = await fetch(`${ORIGIN}/api/core`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command, ...args }),
  });
  const value = await response.json();
  if (value.error) throw new Error(`${command}: ${value.error}`);
  return value.result;
}

// Adopt an existing Student that already owns a Campaign, so Core has a report.
const workspace = await core("workspace");
const student = workspace.mailboxes.find((m) => m.campaign_id)
  ?? workspace.mailboxes[0];
const campaign = workspace.campaigns.find((c) => c.id === student.campaign_id)
  ?? workspace.campaigns[0];

const browser = await chromium.launch({
  executablePath: "C:/Users/Zeng/AppData/Local/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-win64/chrome-headless-shell.exe",
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const problems = [];
page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
page.on("console", (m) => { if (m.type() === "error") problems.push(`console: ${m.text()}`); });

await page.goto(`${ORIGIN}/#workflow`, { waitUntil: "networkidle" });
await page.evaluate((scope) => {
  window.localStorage.setItem("smartmail.workspaceScope", JSON.stringify(scope));
}, {
  studentId: student.student_id ?? student.id,
  studentName: student.student_name ?? "Smoke Student",
  mailbox: student.address ?? "smoke@163.com",
  campaignId: campaign.id,
  campaignName: campaign.name,
});
await page.goto(`${ORIGIN}/#execution`, { waitUntil: "networkidle" });
await page.waitForTimeout(1500);

console.log(JSON.stringify(await page.evaluate(() => ({
  headings: [...document.querySelectorAll(".ex-panel-heading h2")].map((h) => h.textContent),
  overflowY: document.documentElement.scrollHeight - window.innerHeight,
  overflowX: document.documentElement.scrollWidth - window.innerWidth,
  settingsEnabled: !document.querySelector(".ex-toolbar .ex-button:nth-of-type(1)")?.disabled,
})), null, 2));

const rules = page.getByRole("button", { name: /排期设置/ });
if (await rules.count() && await rules.first().isEnabled()) {
  await rules.first().click();
  await page.waitForTimeout(600);
  console.log(JSON.stringify(await page.evaluate(() => {
    const el = document.querySelector(".ex-dialog[open]");
    if (!el) return null;
    return {
      title: el.querySelector("h2")?.textContent,
      windows: el.querySelectorAll(".ex-window").length,
      days: el.querySelectorAll(".ex-day").length,
      projection: [...el.querySelectorAll(".ex-projection dd")].map((d) => d.textContent),
      miniCells: el.querySelectorAll(".ex-mini-cell").length,
      banner: el.querySelector(".ex-settings-preview .ex-banner")?.textContent?.trim().slice(0, 100),
      pace: el.querySelector(".ex-pace-row select")?.value,
      fitsHeight: el.scrollHeight <= el.clientHeight + 2,
    };
  }), null, 2));
  await page.screenshot({ path: ".scratch/execution-settings.png" });
  await page.keyboard.press("Escape");
}
await page.screenshot({ path: ".scratch/execution-page.png" });

console.log(problems.length ? `PROBLEMS:\n${problems.join("\n")}` : "no console/page errors");
await browser.close();
