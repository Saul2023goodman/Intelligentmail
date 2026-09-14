/* Packaged code runs only in the extension's ISOLATED world on the chosen tab. */
(() => {
  if (globalThis.SmartMail163) return;
  const api = globalThis.SmartMail163 = {};
  api.delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
  api.assertDeadline = deadline => {
    if (!Number.isFinite(deadline) || Date.now() >= deadline) throw new Error("Command expired; reconnect and reconcile");
  };
  api.visible = node => Boolean(node && node.getClientRects().length);
  api.addresses = value => [...new Set((String(value || "").match(
    /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi) || []).map(address => address.toLowerCase()))];
  api.account = () => {
    if (location.origin !== "https://mail.163.com" || location.pathname !== "/js6/main.jsp") return "";
    const headers = Array.from(document.querySelectorAll('#spnUid, #spnWelcome, [data-mailbox-address]'));
    const text = headers.length ? headers.map(node => node.getAttribute("data-mailbox-address") || node.textContent).join(" ")
      : (document.body?.innerText || "").split("\n").slice(0, 12).join(" ");
    const addresses = api.addresses(text).filter(address => address.endsWith("@163.com"));
    return addresses.length === 1 ? addresses[0] : "";
  };
  api.observationFailure = (status, detail, mailbox = "") => ({
    status, detail, mailbox_address: mailbox, observed_at: new Date().toISOString(),
    coverage: { complete: false, folders: [] }, messages: []
  });
  api.escapeXML = value => String(value).replace(/[<>&"']/g, char => ({
    "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;", "'": "&apos;"
  })[char]);
  api.valueOf = node => {
    if (!node) return null;
    if (["int", "long"].includes(node.tagName)) return Number(node.textContent);
    if (node.tagName === "boolean") return node.textContent === "true";
    if (node.tagName === "array") return Array.from(node.children).map(api.valueOf);
    if (node.tagName === "object") {
      const result = Object.create(null);
      for (const child of node.children) result[child.getAttribute("name") || child.tagName] = api.valueOf(child);
      return result;
    }
    return node.textContent || "";
  };
  api.xmlDocument = async response => new DOMParser().parseFromString(
    new TextDecoder("utf-8").decode(await response.arrayBuffer()), "application/xml");
  api.codeOf = xml => xml.querySelector("code")?.textContent || "";
  api.post = async (operation, xml) => {
    if (!["mbox:listMessages", "mbox:readMessage"].includes(operation)) throw new Error("Unsupported mailbox read");
    const sid = new URL(location.href).searchParams.get("sid");
    if (!sid) throw new Error("Mailbox session is unavailable; log in again");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      return await fetch(`/js6/s?sid=${encodeURIComponent(sid)}&func=${encodeURIComponent(operation)}`, {
        method: "POST", credentials: "same-origin", signal: controller.signal,
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ var: xml })
      });
    } finally { clearTimeout(timer); }
  };
  api.listSent = async () => {
    const response = await api.post("mbox:listMessages", '<?xml version="1.0"?><object><int name="fid">3</int><string name="order">date</string><boolean name="desc">true</boolean><int name="limit">50</int><int name="start">0</int><boolean name="returnTotal">true</boolean></object>');
    const xml = await api.xmlDocument(response);
    if (!response.ok || api.codeOf(xml) !== "S_OK") throw new Error("Sent-folder evidence is unavailable");
    const container = xml.querySelector('array[name="var"]');
    if (!container) throw new Error("Unsupported Sent-folder response");
    return Array.from(container.children).filter(node => node.tagName === "object").map(api.valueOf);
  };
  api.newSentMatch = (rows, previous, request, startedAt) => {
    const matches = rows.filter(row => {
      const date = String(row.sentDate || "");
      const stamp = /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}$/.test(date)
        ? Date.parse(date.replace(" ", "T") + "+08:00") : Date.parse(date);
      const recipients = api.addresses(row.to);
      return row.id && !previous.includes(row.id) && Number.isFinite(stamp) && stamp >= startedAt - 2000
        && stamp <= Date.now() + 5000 && (row.sndStatus === 3 || row.flags?.rcptSucceed === true)
        && recipients.length === 1 && recipients[0] === request.recipient.toLowerCase()
        && api.addresses(row.from).includes(request.sender.toLowerCase()) && row.subject === request.subject;
    });
    return matches.length === 1 ? matches[0] : null;
  };
})();
