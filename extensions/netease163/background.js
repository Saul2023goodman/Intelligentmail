import { PROTOCOL, HOST, executeCommand } from "./commands.mjs";

let port = null;
let connection = null;
let timer = null;
let busy = false;
let polling = false;
let lastError = "尚未连接邮箱标签页";
const waiting = new Map();

function disconnect(detail = "连接已断开") {
  clearInterval(timer);
  timer = null;
  const previous = port;
  port = null;
  connection = null;
  lastError = detail;
  for (const callback of waiting.values()) callback.reject(new Error(detail));
  waiting.clear();
  previous?.disconnect();
}

function rpc(type, payload = {}) {
  return new Promise((resolve, reject) => {
    if (!port) return reject(new Error("本机桥接未连接"));
    const id = crypto.randomUUID();
    const timeout = setTimeout(() => {
      waiting.delete(id);
      reject(new Error("本机桥接响应超时"));
    }, 10000);
    waiting.set(id, {
      resolve: value => { clearTimeout(timeout); resolve(value); },
      reject: error => { clearTimeout(timeout); reject(error); }
    });
    try { port.postMessage({ protocol: PROTOCOL, id, type, ...payload }); }
    catch (error) { waiting.get(id).reject(error); waiting.delete(id); }
  });
}

const ISOLATED_METHODS = new Set(
  ["account", "observe", "prepare", "send", "placeSchedule", "cancelSchedule", "recallMessage"]);

async function executeInWorld(world, namespace, method, args) {
  if (!connection) throw new Error("Mailbox tab was disconnected");
  if (!ISOLATED_METHODS.has(method)) throw new Error("Unsupported mailbox command");
  const selected = connection;
  const results = await chrome.scripting.executeScript({
    target: { tabId: selected.tabId, documentIds: [selected.documentId] }, world,
    func: async (namespace, method, args) => {
      const scope = namespace.split(".").reduce((node, key) => node?.[key], globalThis);
      if (!scope || typeof scope[method] !== "function")
        throw new Error("Mailbox runtime is unavailable in the selected execution world");
      return await scope[method](...args);
    }, args: [namespace, method, args]
  });
  if (connection !== selected || results.length !== 1 || results[0].documentId !== selected.documentId)
    throw new Error("Mailbox document changed during execution");
  if (results[0].error) throw new Error(results[0].error.message || "Mailbox script failed");
  return results[0].result;
}

async function invoke(method, ...args) {
  // Observation prefers the MAIN-world reader, which drives the official webmail
  // runtime ($.DataAction) and returns full message content, draft Compose models
  // and attachment metadata. Older pages without that runtime transparently fall
  // back to the ISOLATED metadata-only observer.
  if (method === "observe") {
    try {
      const result = await executeInWorld("MAIN", "SmartMail163Reader", "observe", args);
      if (result && result.status !== "runtime_unavailable") return result;
    } catch {
      // Fall through to the ISOLATED observer.
    }
  }
  const result = await executeInWorld("ISOLATED", "SmartMail163", method, args);
  if (result == null) throw new Error("Mailbox script returned no result");
  return result;
}

async function connect(tabId) {
  if (busy) throw new Error("操作尚未结束；请等待或检查执行台账");
  if (connection) throw new Error("请先断开已连接的邮箱标签页");
  const tab = await chrome.tabs.get(tabId);
  const url = new URL(tab.url);
  if (url.origin !== "https://mail.163.com" || url.pathname !== "/js6/main.jsp")
    throw new Error("请在已登录的 163 邮箱主页打开扩展");
  await chrome.scripting.executeScript({
    target: { tabId }, world: "MAIN", files: ["reader.js"]
  });
  await chrome.scripting.executeScript({
    target: { tabId }, world: "ISOLATED", files: ["common.js", "observe.js", "compose.js", "schedule.js"]
  });
  // Prefer the official runtime account ($S('uid')); fall back to the ISOLATED
  // DOM-based probe for pages whose runtime is not ready yet.
  let identity = await chrome.scripting.executeScript({
    target: { tabId }, world: "MAIN",
    func: () => globalThis.SmartMail163Reader?.runtimeAvailable() ? globalThis.SmartMail163Reader.account() : ""
  });
  if (!identity[0]?.result) {
    identity = await chrome.scripting.executeScript({
      target: { tabId }, world: "ISOLATED", func: () => globalThis.SmartMail163.account()
    });
  }
  if (!identity[0]?.result) throw new Error("无法唯一识别当前邮箱；请完成登录后重试");
  connection = { tabId, documentId: identity[0].documentId, mailbox_address: identity[0].result };
  const selected = connection;
  port = chrome.runtime.connectNative(HOST);
  const selectedPort = port;
  port.onMessage.addListener(message => {
    if (message.protocol !== PROTOCOL) return disconnect("本机桥接版本不兼容");
    const callback = waiting.get(message.id);
    if (!callback) return;
    waiting.delete(message.id);
    if (message.ok) callback.resolve(message.result);
    else callback.reject(new Error(message.error || "本机桥接拒绝请求"));
  });
  port.onDisconnect.addListener(() => {
    const detail = chrome.runtime.lastError?.message || "本机桥接已关闭，请重新连接";
    if (port === selectedPort) disconnect(detail);
  });
  try {
    await rpc("connect", { mailbox_address: identity.result });
    lastError = "";
    timer = setInterval(async () => {
      if (polling || connection !== selected) return;
      polling = true;
      try {
        const { command } = await rpc("poll", { ready: !busy });
        if (command && !busy) {
          busy = true;
          // Keep heartbeat polling while a page operation awaits upload or Sent evidence.
          executeCommand(command, { invoke, rpc, connected: () => connection === selected })
            .then(result => rpc("result", { command_id: command.id, result }))
            .catch(error => { lastError = String(error.message || error); })
            .finally(() => { busy = false; });
        }
      } catch (error) { disconnect(String(error.message || error)); }
      finally { polling = false; }
    }, 1000);
  } catch (error) { disconnect(String(error.message || error)); throw error; }
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id || sender.url !== chrome.runtime.getURL("popup.html")) return;
  (async () => {
    if (message.type === "connect") await connect(message.tabId);
    else if (message.type === "disconnect") disconnect("已由操作员断开连接");
    else if (message.type !== "status") throw new Error("Unsupported extension action");
    return { ok: true, connected: Boolean(connection), mailbox_address: connection?.mailbox_address || "",
      busy, detail: lastError };
  })().then(respond, error => respond({ ok: false, detail: String(error.message || error) }));
  return true;
});
chrome.tabs.onRemoved.addListener(tabId => { if (connection?.tabId === tabId) disconnect("邮箱标签页已关闭"); });
chrome.tabs.onUpdated.addListener((tabId, change) => {
  if (connection?.tabId === tabId && change.status === "loading") disconnect("邮箱页面正在重新载入，请重新连接");
});
