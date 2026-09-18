import { PROTOCOL, HOST, executeCommand } from "./commands.mjs";
import {
  mailboxIdentity,
  nextPollDelay,
  reconnectDelay,
  selectMailboxTab,
} from "./connection.mjs";

const AUTO_CONNECT_KEY = "autoConnect";
const ENSURE_ALARM = "smartmail-ensure-connection";

let port = null;
let bridgeReady = false;
let connection = null;
let pollTimer = null;
let retryTimer = null;
let busy = false;
let polling = false;
let connecting = false;
let autoConnect = false;
let retryAttempt = 0;
let lastError = "正在自动查找已登录的 163 邮箱…";
const waiting = new Map();

function publicStatus() {
  const connected = Boolean(connection && port && bridgeReady);
  return {
    ok: true,
    state: connected ? "connected" : connection ? "recovering" : connecting ? "connecting" :
      autoConnect ? "discovering" : "paused",
    connected,
    mailbox_address: connection?.mailbox_address || "",
    tab_id: connection?.tabId ?? null,
    busy,
    auto_connect: autoConnect,
    detail: lastError,
  };
}

function rejectWaiting(detail) {
  for (const callback of waiting.values()) callback.reject(new Error(detail));
  waiting.clear();
}

function clearPoll() {
  clearTimeout(pollTimer);
  pollTimer = null;
  polling = false;
}

function closePort(detail) {
  clearPoll();
  const previous = port;
  port = null;
  bridgeReady = false;
  rejectWaiting(detail);
  previous?.disconnect();
}

function clearTarget(detail) {
  clearTimeout(retryTimer);
  retryTimer = null;
  closePort(detail);
  connection = null;
  retryAttempt = 0;
  lastError = detail;
}

async function setAutoConnect(value) {
  autoConnect = value;
  await chrome.storage.local.set({ [AUTO_CONNECT_KEY]: value });
}

function rpc(type, payload = {}) {
  return new Promise((resolve, reject) => {
    if (!port) return reject(new Error("本机桥接未连接"));
    const selectedPort = port;
    const id = crypto.randomUUID();
    const timeout = setTimeout(() => {
      waiting.delete(id);
      reject(new Error("本机桥接响应超时"));
    }, 10000);
    waiting.set(id, {
      resolve: value => { clearTimeout(timeout); resolve(value); },
      reject: error => { clearTimeout(timeout); reject(error); },
    });
    try {
      selectedPort.postMessage({ protocol: PROTOCOL, id, type, ...payload });
    } catch (error) {
      const callback = waiting.get(id);
      if (callback) callback.reject(error);
      waiting.delete(id);
    }
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
    }, args: [namespace, method, args],
  });
  if (connection !== selected || results.length !== 1 || results[0].documentId !== selected.documentId)
    throw new Error("Mailbox document changed during execution");
  if (results[0].error) throw new Error(results[0].error.message || "Mailbox script failed");
  return results[0].result;
}

async function invoke(method, ...args) {
  if (method === "observe") {
    try {
      const result = await executeInWorld("MAIN", "SmartMail163Reader", "observe", args);
      if (result && result.status !== "runtime_unavailable") return result;
    } catch {
      // Older pages without the official runtime use the isolated observer.
    }
  }
  const result = await executeInWorld("ISOLATED", "SmartMail163", method, args);
  if (result == null) throw new Error("Mailbox script returned no result");
  return result;
}

function scheduleRetry(detail) {
  lastError = detail;
  if (!autoConnect || retryTimer) return;
  const delay = reconnectDelay(retryAttempt++);
  retryTimer = setTimeout(() => {
    retryTimer = null;
    void ensureConnection().catch(error => scheduleRetry(String(error.message || error)));
  }, delay);
}

function bridgeLost(selected, selectedPort, detail) {
  if (connection !== selected || port !== selectedPort) return;
  closePort(detail);
  scheduleRetry(`${detail}；正在自动重连`);
}

function startPolling(selected, selectedPort) {
  const schedule = delay => {
    clearTimeout(pollTimer);
    if (connection === selected && port === selectedPort)
      pollTimer = setTimeout(poll, delay);
  };
  const poll = async () => {
    if (polling || connection !== selected || port !== selectedPort) return;
    polling = true;
    try {
      const { command } = await rpc("poll", { ready: !busy });
      if (command && !busy) {
        busy = true;
        executeCommand(command, {
          invoke,
          rpc,
          connected: () => connection === selected && port === selectedPort && bridgeReady,
        })
          .then(result => rpc("result", { command_id: command.id, result }))
          .catch(error => { lastError = String(error.message || error); })
          .finally(() => { busy = false; schedule(0); });
      }
    } catch (error) {
      bridgeLost(selected, selectedPort, String(error.message || error));
    } finally {
      polling = false;
      if (connection === selected && port === selectedPort) schedule(nextPollDelay(busy));
    }
  };
  return poll();
}

async function connectBridge() {
  if (!connection || port) return;
  const selected = connection;
  const selectedPort = chrome.runtime.connectNative(HOST);
  port = selectedPort;
  bridgeReady = false;
  selectedPort.onMessage.addListener(message => {
    if (message.protocol !== PROTOCOL) return bridgeLost(selected, selectedPort, "本机桥接版本不兼容");
    const callback = waiting.get(message.id);
    if (!callback) return;
    waiting.delete(message.id);
    if (message.ok) callback.resolve(message.result);
    else callback.reject(new Error(message.error || "本机桥接拒绝请求"));
  });
  selectedPort.onDisconnect.addListener(() => {
    const detail = chrome.runtime.lastError?.message || "本机桥接已关闭";
    bridgeLost(selected, selectedPort, detail);
  });
  try {
    await rpc("connect", { mailbox_address: selected.mailbox_address });
    if (connection !== selected || port !== selectedPort) return;
    bridgeReady = true;
    retryAttempt = 0;
    lastError = "";
    await startPolling(selected, selectedPort);
  } catch (error) {
    bridgeLost(selected, selectedPort, String(error.message || error));
    throw error;
  }
}

async function probeTab(tabId) {
  const tab = await chrome.tabs.get(tabId);
  const url = new URL(tab.url || "");
  if (url.origin !== "https://mail.163.com" || url.pathname !== "/js6/main.jsp")
    throw new Error("请先登录 163 邮箱；扩展会在邮箱主页自动连接");
  await chrome.scripting.executeScript({ target: { tabId }, world: "MAIN", files: ["reader.js"] });
  await chrome.scripting.executeScript({
    target: { tabId }, world: "ISOLATED", files: ["common.js", "observe.js", "compose.js", "schedule.js"],
  });
  let identity = await chrome.scripting.executeScript({
    target: { tabId }, world: "MAIN",
    func: () => globalThis.SmartMail163Reader?.runtimeAvailable() ? globalThis.SmartMail163Reader.account() : "",
  });
  if (!mailboxIdentity(identity)) {
    identity = await chrome.scripting.executeScript({
      target: { tabId }, world: "ISOLATED", func: () => globalThis.SmartMail163.account(),
    });
  }
  const mailboxAddress = mailboxIdentity(identity);
  if (!mailboxAddress) throw new Error("邮箱仍在登录或加载中；扩展将自动重试");
  return { tabId, documentId: identity[0].documentId, mailbox_address: mailboxAddress };
}

async function connectTab(tabId) {
  if (busy) throw new Error("操作尚未结束；请等待或检查执行台账");
  if (connection?.tabId === tabId) {
    if (!port) await connectBridge();
    return publicStatus();
  }
  const target = await probeTab(tabId);
  clearTarget("正在切换邮箱标签页");
  connection = target;
  lastError = "已识别邮箱，正在连接本机桥接…";
  await connectBridge();
  return publicStatus();
}

async function ensureConnection(preferredTabId = null) {
  if (!autoConnect || connecting || busy) return publicStatus();
  if (connection && port) return publicStatus();
  connecting = true;
  try {
    if (connection) {
      await connectBridge();
      return publicStatus();
    }
    const tabs = await chrome.tabs.query({ url: "https://mail.163.com/*" });
    const tab = selectMailboxTab(tabs, preferredTabId);
    if (!tab) {
      lastError = tabs.length > 1
        ? "检测到多个 163 邮箱标签页；请在要使用的页面点一次扩展图标"
        : "未发现已登录的 163 邮箱主页；打开邮箱后会自动连接";
      return publicStatus();
    }
    return await connectTab(tab.id);
  } finally {
    connecting = false;
  }
}

async function resumeAndConnect(tabId = null) {
  await setAutoConnect(true);
  clearTimeout(retryTimer);
  retryTimer = null;
  if (typeof tabId === "number") return connectTab(tabId);
  return ensureConnection();
}

async function pause() {
  await setAutoConnect(false);
  clearTarget("自动连接已暂停");
  return publicStatus();
}

async function checkedStatus(preferredTabId = null) {
  if (connection && port && bridgeReady) {
    const selected = connection;
    const selectedPort = port;
    try {
      // Do not trust the service worker's globals: refresh the host lease and
      // require a real round trip before the popup says "connected".
      await rpc("poll", { ready: false });
    } catch (error) {
      bridgeLost(selected, selectedPort, String(error.message || error));
    }
  }
  if (autoConnect && !(connection && port && bridgeReady)) {
    try {
      await ensureConnection(preferredTabId);
    } catch (error) {
      scheduleRetry(String(error.message || error));
    }
  }
  return publicStatus();
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id || sender.url !== chrome.runtime.getURL("popup.html")) return;
  (async () => {
    if (message.type === "connect") return resumeAndConnect(message.tabId);
    if (message.type === "resume") return resumeAndConnect();
    if (message.type === "disconnect") return pause();
    if (message.type === "openMailbox") {
      await setAutoConnect(true);
      await chrome.tabs.create({ url: "https://mail.163.com/" });
      lastError = "请完成登录；进入邮箱主页后将自动连接";
      return publicStatus();
    }
    if (message.type !== "status") throw new Error("Unsupported extension action");
    return checkedStatus(message.tabId);
  })().then(respond, error => respond({ ...publicStatus(), ok: false, detail: String(error.message || error) }));
  return true;
});

chrome.tabs.onRemoved.addListener(tabId => {
  if (connection?.tabId !== tabId) return;
  clearTarget("邮箱标签页已关闭；正在查找其他邮箱页");
  void ensureConnection().catch(error => scheduleRetry(String(error.message || error)));
});
chrome.tabs.onUpdated.addListener((tabId, change) => {
  if (connection?.tabId === tabId && change.status === "loading")
    clearTarget("邮箱页面正在重新载入；完成后将自动重连");
  if (change.status === "complete")
    void ensureConnection(tabId).catch(error => scheduleRetry(String(error.message || error)));
});
chrome.tabs.onActivated.addListener(({ tabId }) => {
  void ensureConnection(tabId).catch(error => scheduleRetry(String(error.message || error)));
});
chrome.runtime.onStartup.addListener(() => {
  void ensureConnection().catch(error => scheduleRetry(String(error.message || error)));
});
chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(ENSURE_ALARM, { periodInMinutes: 1 });
  void ensureConnection().catch(error => scheduleRetry(String(error.message || error)));
});
chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === ENSURE_ALARM)
    void ensureConnection().catch(error => scheduleRetry(String(error.message || error)));
});

(async () => {
  const stored = await chrome.storage.local.get(AUTO_CONNECT_KEY);
  autoConnect = stored[AUTO_CONNECT_KEY] !== false;
  chrome.alarms.create(ENSURE_ALARM, { periodInMinutes: 1 });
  if (autoConnect)
    await ensureConnection().catch(error => scheduleRetry(String(error.message || error)));
})();
