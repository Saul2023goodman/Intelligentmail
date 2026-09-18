const status = document.getElementById("status");
const connect = document.getElementById("connect");
const disconnect = document.getElementById("disconnect");
document.getElementById("extension-id").textContent = chrome.runtime.id;

async function update(type) {
  connect.disabled = disconnect.disabled = true;
  if (type === "connect") status.textContent = "Identifying mailbox and connecting to the native bridge…";
  if (type === "disconnect") status.textContent = "Pausing auto-connect…";
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    let action = type;
    if (type === "connect" && !String(tab?.url || "").startsWith("https://mail.163.com/"))
      action = "openMailbox";
    const result = await chrome.runtime.sendMessage({ type: action, tabId: tab?.id });
    status.textContent = result.connected ?
      `Connected ${result.mailbox_address}${result.busy ? " · confirmed operation in progress" : ""}` :
      result.detail || "Auto-discovering mailbox…";
    const onMailbox = String(tab?.url || "").startsWith("https://mail.163.com/");
    connect.textContent = result.auto_connect ? (onMailbox ? "Prioritize current mailbox" : "Open 163 Mailbox") : "Resume auto-connect";
    connect.disabled = Boolean(result.busy || (result.connected && result.tab_id === tab?.id));
    disconnect.disabled = !result.auto_connect;
  } catch (error) { status.textContent = String(error.message || error); connect.disabled = false; }
}
connect.addEventListener("click", () => update("connect"));
disconnect.addEventListener("click", () => update("disconnect"));
update("status");
