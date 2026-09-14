const status = document.getElementById("status");
const connect = document.getElementById("connect");
const disconnect = document.getElementById("disconnect");
document.getElementById("extension-id").textContent = chrome.runtime.id;

async function update(type) {
  connect.disabled = disconnect.disabled = true;
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const result = await chrome.runtime.sendMessage({ type, tabId: tab?.id });
    status.textContent = result.connected
      ? `已连接 ${result.mailbox_address}${result.busy ? " · 正在执行已确认操作" : ""}`
      : result.detail || "尚未连接邮箱";
    connect.disabled = Boolean(result.connected || result.busy);
    disconnect.disabled = !result.connected;
  } catch (error) { status.textContent = String(error.message || error); connect.disabled = false; }
}
connect.addEventListener("click", () => update("connect"));
disconnect.addEventListener("click", () => update("disconnect"));
update("status");
