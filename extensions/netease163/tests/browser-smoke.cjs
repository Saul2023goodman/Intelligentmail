/* Optional development smoke test. Every network request is fulfilled locally or aborted. */
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const assert = require("node:assert/strict");
const { createHash } = require("node:crypto");
const { chromium } = require(process.env.SMARTMAIL_PLAYWRIGHT_MODULE || "playwright");

(async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "smartmail-extension-smoke-"));
  const extension = path.resolve(__dirname, "..");
  let context;
  try {
    context = await chromium.launchPersistentContext(directory, {
      channel: "chromium", headless: true,
      executablePath: process.env.SMARTMAIL_CHROMIUM_EXECUTABLE || undefined,
      args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`]
    });
    const worker = context.serviceWorkers()[0] || await context.waitForEvent("serviceworker");
    let sendCount = 0;
    const xml = text => '<?xml version="1.0"?><result><code>S_OK</code>' + text + "</result>";
    const row = () => `<object><string name="id">new-sent-1</string><string name="from">student@163.com</string><string name="to">supervisor@example.edu</string><string name="subject">Confirmed subject</string><string name="sentDate">${new Date().toISOString()}</string><int name="sndStatus">3</int></object>`;
    const html = `<!doctype html><html><body><span id="spnUid">student@163.com</span><ul>${["收件箱", "草稿箱", "已发送", "已删除", "垃圾邮件"].map(text => '<li role="treeitem">' + text + "</li>").join("")}</ul><button id="compose">写 信</button><section id="editor"></section><script>
      document.getElementById('compose').onclick=()=>{
        document.getElementById('editor').innerHTML='<input name="to"><input name="subject"><textarea name="content"></textarea><input type="file" multiple><div id="uploads"></div><button id="send">发送</button>';
        document.querySelector('input[type=file]').onchange=e=>{document.getElementById('uploads').innerHTML=Array.from(e.target.files).map(f=>'<div data-upload-state="complete">'+f.name+'</div>').join('');};
        document.getElementById('send').onclick=()=>window.recordFixtureSend();
      };
    </script></body></html>`;
    await context.route("**/*", async route => {
      const url = new URL(route.request().url());
      if (url.origin !== "https://mail.163.com") return route.abort();
      if (url.pathname === "/js6/main.jsp") return route.fulfill({ contentType: "text/html; charset=utf-8", body: html });
      if (url.pathname === "/js6/s") {
        const body = url.searchParams.get("func") === "mbox:readMessage"
          ? xml('<object name="var"><string name="subject">Confirmed subject</string></object>')
          : xml(`<array name="var">${sendCount ? row() : ""}</array><int name="total">${sendCount ? 1 : 0}</int>`);
        return route.fulfill({ contentType: "application/xml; charset=utf-8", body });
      }
      return route.abort();
    });
    const page = await context.newPage();
    await page.exposeFunction("recordFixtureSend", () => { sendCount++; });
    await page.goto("https://mail.163.com/js6/main.jsp?sid=fixture");
    const tabId = await worker.evaluate(async () => (await chrome.tabs.query({ url: "https://mail.163.com/*" }))[0].id);
    const invoke = (method, args = []) => worker.evaluate(async ({ tabId, method, args }) => {
      const [result] = await chrome.scripting.executeScript({ target: { tabId }, world: "ISOLATED",
        func: async (method, args) => globalThis.SmartMail163[method](...args), args: [method, args] });
      if (result.error || result.result == null) throw new Error("Mailbox script returned no result");
      return result.result;
    }, { tabId, method, args });
    await worker.evaluate(tabId => chrome.scripting.executeScript({ target: { tabId }, world: "ISOLATED",
      files: ["common.js", "observe.js", "compose.js"] }), tabId);
    assert.equal(await invoke("account"), "student@163.com");
    const initial = await invoke("observe", ["student@163.com", Date.now() + 60000]);
    assert.equal(initial.status, "complete");
    assert.equal(initial.messages.length, 0);
    assert.equal(sendCount, 0);
    const bytes = Buffer.from("Exact confirmed attachment bytes\n中文");
    const command = { id: "fixture-command", operation: "submit", deadline: Date.now() + 60000, payload: {
      kind: "immediate", sender: "student@163.com", recipient: "supervisor@example.edu",
      subject: "Confirmed subject", body: "Confirmed body\nSecond line",
      attachments: [{ name: "sample.txt", size: bytes.length, sha256: createHash("sha256").update(bytes).digest("hex") }]
    } };
    assert.equal((await invoke("prepare", [command, [bytes.toString("base64")]])).prepared, true);
    const outcome = await invoke("send", [command]);
    assert.equal(outcome.outcome, "sent", JSON.stringify(outcome));
    assert.equal(sendCount, 1);
    await assert.rejects(invoke("send", [command]));
    assert.equal(sendCount, 1);
    const popup = await context.newPage();
    await popup.goto(worker.url().replace(/background\.js$/, "popup.html"));
    await popup.waitForSelector("#extension-id", { state: "attached" });
    const output = path.resolve("output/playwright");
    fs.mkdirSync(output, { recursive: true });
    await popup.screenshot({ path: path.join(output, "extension-popup.png") });
    console.log(JSON.stringify({ extensionLoaded: true, isolatedScripts: true, readOnlyObservation: true,
      exactAttachment: true, sendCount, repeatRefused: true, outcome: outcome.outcome }));
  } finally {
    if (context) await context.close();
    const resolved = path.resolve(directory);
    if (path.dirname(resolved) !== path.resolve(os.tmpdir()) || !path.basename(resolved).startsWith("smartmail-extension-smoke-"))
      throw new Error("Refusing cleanup outside the smoke-test temporary directory");
    fs.rmSync(resolved, { recursive: true, force: true });
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
