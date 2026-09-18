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

const workspace = await core("workspace");
const student = workspace.mailboxes.find((m) => m.student_name === "Pacing Demo")
  ?? workspace.mailboxes.find((m) => m.campaign_id);
const campaign = workspace.campaigns.find((c) => c.id === student.campaign_id);

const browser = await chromium.launch({
  executablePath: "C:/Users/Zeng/AppData/Local/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-win64/chrome-headless-shell.exe",
});
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
const problems = [];
page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
page.on("console", (m) => { if (m.type() === "error") problems.push(`console: ${m.text()}`); });

await page.goto(`${ORIGIN}/#workflow`, { waitUntil: "networkidle" });
await page.evaluate((scope) => {
  window.localStorage.setItem("smartmail.workspaceScope", JSON.stringify(scope));
}, {
  studentId: student.student_id, studentName: student.student_name,
  mailbox: student.address, campaignId: campaign.id, campaignName: campaign.name,
});
await page.reload({ waitUntil: "networkidle" });
await page.evaluate(() => { window.location.hash = "#execution"; });
await page.waitForTimeout(1500);

const grid = await page.evaluate(() => {
  const cells = [...document.querySelectorAll(".ex-grid tbody tr")].map((tr) => ({
    institution: tr.querySelector(".ex-row-name")?.textContent,
    slots: [...tr.querySelectorAll(".ex-slot")].map((s) => ({
      time: s.querySelector(".ex-slot-time")?.textContent,
      name: s.querySelector(".ex-slot-name")?.textContent,
      state: s.querySelector(".ex-slot-state")?.textContent,
    })),
    empties: tr.querySelectorAll(".ex-cell-empty").length,
  }));
  return {
    columns: [...document.querySelectorAll(".ex-colhead .ex-col-date")].map((t) => t.textContent),
    corner: document.querySelector(".ex-grid-corner")?.textContent,
    cells,
    excluded: [...document.querySelectorAll(".ex-excluded .ex-card")].map((c) => c.textContent),
    overflowY: document.documentElement.scrollHeight - window.innerHeight,
    overflowX: document.documentElement.scrollWidth - window.innerWidth,
    tabLabels: [...document.querySelectorAll(".ex-tabs button")].map((b) => b.textContent),
  };
});
console.log(JSON.stringify(grid, null, 2));
await page.screenshot({ path: ".scratch/execution-page.png" });

// Narrow window: the three regions become reachable tabs, still no page overflow.
await page.setViewportSize({ width: 900, height: 600 });
await page.waitForTimeout(400);
console.log(JSON.stringify(await page.evaluate(() => ({
  tabsVisible: getComputedStyle(document.querySelector(".ex-tabs")).display !== "none",
  overflows: [...document.querySelectorAll(".ex-tabs button")].map((b, i) => {
    b.click();
    return document.documentElement.scrollHeight - window.innerHeight
      + (document.documentElement.scrollWidth - window.innerWidth);
  }),
})), null, 2));

console.log(problems.length ? `PROBLEMS:\n${problems.join("\n")}` : "no console/page errors");
await browser.close();
