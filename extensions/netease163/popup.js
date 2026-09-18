const status = document.getElementById("status");
const connect = document.getElementById("connect");
const disconnect = document.getElementById("disconnect");
document.getElementById("extension-id").textContent = chrome.runtime.id;

async function update(type) {
  connect.disabled = disconnect.disabled = true;
  if (type === "connect") status.textContent = "正在识别邮箱并连接本机桥接…";
  if (type === "disconnect") status.textContent = "正在暂停自动连接…";
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    let action = type;
    if (type === "connect" && !String(tab?.url || "").startsWith("https://mail.163.com/"))
      action = "openMailbox";
    const result = await chrome.runtime.sendMessage({ type: action, tabId: tab?.id });
    status.textContent = result.connected ?
      `已连接 ${result.mailbox_address}${result.busy ? " · 正在执行已确认操作" : ""}` :
      result.detail || "正在自动查找邮箱";
    const onMailbox = String(tab?.url || "").startsWith("https://mail.163.com/");
    connect.textContent = result.auto_connect ? (onMailbox ? "优先连接当前邮箱" : "打开 163 邮箱") : "恢复自动连接";
    connect.disabled = Boolean(result.busy || (result.connected && result.tab_id === tab?.id));
    disconnect.disabled = !result.auto_connect;
  } catch (error) { status.textContent = String(error.message || error); connect.disabled = false; }
}
connect.addEventListener("click", () => update("connect"));
disconnect.addEventListener("click", () => update("disconnect"));
update("status");
