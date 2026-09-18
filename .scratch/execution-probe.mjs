import { createRequire } from "node:module";
const require = createRequire("C:/Users/Zeng/AppData/Local/npm-cache/_npx/31e32ef8478fbf80/node_modules/");
const { chromium } = require("playwright");
const ORIGIN = "http://127.0.0.1:5179";
const browser = await chromium.launch({
  executablePath: "C:/Users/Zeng/AppData/Local/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-win64/chrome-headless-shell.exe",
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on("pageerror", (e) => console.log("pageerror:", e.message));
page.on("console", (m) => { if (m.type() === "error") console.log("console:", m.text()); });
page.on("requestfailed", (r) => console.log("reqfail:", r.url(), r.failure()?.errorText));
page.on("response", (r) => { if (r.url().includes("/api/core")) console.log("core:", r.status()); });
await page.goto(`${ORIGIN}/#execution`, { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
console.log(JSON.stringify(await page.evaluate(() => ({
  scope: window.localStorage.getItem("smartmail.workspaceScope"),
  connection: document.querySelector(".ex-connection")?.textContent,
  buttons: [...document.querySelectorAll(".ex-toolbar button")].map(b => [b.textContent, b.disabled]),
  timezone: document.querySelector(".ex-timezone")?.textContent ?? null,
})), null, 2));
await browser.close();
