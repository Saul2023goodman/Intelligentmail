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

  /* ----- HTML message body helpers -------------------------------------
   * Confirmed content is bound as exact plain text. Rendering it as HTML is
   * a presentation transform: plain text is escaped and mapped one line to
   * one block, so nothing is invented. When the confirmed body itself carries
   * HTML (or an explicit body_html is supplied), its tags and inline styles
   * (italics, font size, color) are preserved verbatim. */
  const HTML_TAG_RE = /<\s*(?:p|div|br|span|b|strong|i|em|u|s|strike|ul|ol|li|font|h[1-6]|a|blockquote|hr|img|table|thead|tbody|tr|td|th)\b[^>]*>/i;
  api.looksLikeHtml = value => HTML_TAG_RE.test(String(value || ""));
  api.escapeHtml = value => String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
  // 163 renders the editor body with this root wrapper. Newlines map to <br>
  // inside one block; element.innerText then projects back to the exact text.
  api.plainToHtml = text => {
    const lines = String(text ?? "").replace(/\r\n?/g, "\n").split("\n");
    // Every newline becomes one <br>; an empty line contributes nothing.
    const html = lines.map(line => (line === "" ? "" : api.escapeHtml(line)))
      .join("<br />");
    return '<div data-ntes="ntes_mail_body_root" '
      + 'style="line-height:1.7;color:#000000;font-size:14px;font-family:Arial">'
      + html + "</div>";
  };
  api.composeBodyHtml = ({ html = "", text = "" } = {}) => {
    if (html && api.looksLikeHtml(html)) return html;
    return api.looksLikeHtml(text) ? text : api.plainToHtml(text);
  };
  api.htmlToPlainText = html => {
    const raw = String(html || "");
    if (!raw) return "";
    try {
      const doc = new DOMParser().parseFromString(raw, "text/html");
      doc.querySelectorAll("script,style,noscript").forEach(node => node.remove());
      const block = doc.createElement("div");
      block.innerHTML = doc.body ? doc.body.innerHTML : raw;
      block.querySelectorAll("br").forEach(br => br.replaceWith("\n"));
      block.querySelectorAll("p,div,li,tr,h1,h2,h3,h4,h5,h6")
        .forEach(node => node.append("\n"));
      return String(block.textContent || "")
        .replace(/ /g, " ")
        .replace(/[ \t]+\n/g, "\n")
        .replace(/\n{3,}/g, "\n\n")
        .replace(/^\n+|\s+$/g, "");
    } catch {
      return raw.replace(/<br\s*\/?>(\n)?/gi, "\n")
        .replace(/<\/(?:p|div|li|tr|h[1-6])>/gi, "\n")
        .replace(/<[^>]+>/g, "").trim();
    }
  };
  // Compare a rich editor's text projection with the confirmed body. Line
  // endings and trailing whitespace differ between text nodes and innerText,
  // and block-level tags render with varying numbers of blank lines, so runs
  // of blank lines are treated as a single paragraph separation.
  api.sameText = (left, right) => {
    const norm = value => String(value ?? "").replace(/\r\n?/g, "\n")
      .split("\n").map(line => line.replace(/[ \t]+$/g, ""))
      .join("\n")
      .replace(/\n{3,}/g, "\n\n")
      .replace(/^\n+|\n+$/g, "");
    return norm(left) === norm(right);
  };
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

  /* ------------------------------------------------------------------ */
  /* Native scheduling, cancellation and Recall: bounded wmsvr calls.   */
  /* ------------------------------------------------------------------ */

  // Only these fixed funcs can be issued; there is no arbitrary JS/URL surface.
  const WMSVR_FUNCS = new Set([
    "mbox:listMessages", "mbox:readMessage", "mbox:compose",
    "mbox:updateMessageInfos", "mbox:recallMessage",
  ]);
  api.toXml = (value, name = null) => {
    let tag = "string";
    let text = "";
    if (value === null || value === undefined) return "";
    if (typeof value === "boolean") { tag = "boolean"; text = value ? "true" : "false"; }
    else if (typeof value === "number") {
      text = String(value);
      tag = Number.isInteger(value) && -2147483648 <= value && value < 2147483648 ? "int"
        : Number.isInteger(value) ? "long" : "number";
    } else if (value instanceof Date) {
      tag = "date";
      text = api.beijingStamp(value);
    } else if (Array.isArray(value)) {
      tag = "array";
      text = value.map(child => api.toXml(child)).join("");
    } else if (typeof value === "object") {
      tag = "object";
      text = Object.entries(value)
        .filter(([, child]) => child !== undefined && child !== null)
        .map(([key, child]) => api.toXml(child, key)).join("");
    } else {
      text = String(value);
    }
    // Container text is already serialized markup: only leaf values are escaped.
    if (tag === "object" || tag === "array") {
      if (!text) return name === null ? `<${tag}/>` : `<${tag} name="${api.escapeXML(name)}"/>`;
      return name === null ? `<${tag}>${text}</${tag}>`
        : `<${tag} name="${api.escapeXML(name)}">${text}</${tag}>`;
    }
    const escaped = api.escapeXML(text);
    return name === null ? `<${tag}>${escaped}</${tag}>`
      : `<${tag} name="${api.escapeXML(name)}">${escaped}</${tag}>`;
  };
  // 163 stores scheduleDate as the Beijing wall clock; render it from the
  // instant directly so the result is independent of the operator's OS timezone.
  api.beijingStamp = instant => {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: "Asia/Shanghai", hour12: false,
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    }).formatToParts(instant).reduce((acc, part) => { acc[part.type] = part.value; return acc; }, {});
    const hour = parts.hour === "24" ? "00" : parts.hour;
    return `${parts.year}-${parts.month}-${parts.day} ${hour}:${parts.minute}:${parts.second}`;
  };
  api.wmsvr = async (func, obj) => {
    if (!WMSVR_FUNCS.has(func)) throw new Error("Unsupported wmsvr operation");
    const sid = new URL(location.href).searchParams.get("sid");
    if (!sid) throw new Error("Mailbox session is unavailable; log in again");
    const xml = '<?xml version="1.0"?>' + api.toXml(obj);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(`/js6/s?sid=${encodeURIComponent(sid)}&func=${encodeURIComponent(func)}`, {
        method: "POST", credentials: "same-origin", signal: controller.signal,
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ var: xml })
      });
      const text = await response.text();
      const document = await api.xmlDocument({ arrayBuffer: async () => new TextEncoder().encode(text) });
      const code = api.codeOf(document);
      if (!response.ok && code !== "S_OK") throw new Error(`${func} returned HTTP ${response.status}`);
      const nodes = {};
      Array.from(document.querySelector("result")?.children || []).forEach(node => {
        const key = node.getAttribute("name") || node.tagName;
        nodes[key] = api.valueOf(node);
      });
      return { code, nodes, raw: text };
    } finally { clearTimeout(timer); }
  };
  api.listFolder = async (fid, limit = 50, start = 0) => {
    const result = await api.wmsvr("mbox:listMessages", {
      fid, order: "date", desc: true, limit, start,
      skipLockedFolders: false, returnTag: true, returnTotal: true
    });
    return Array.isArray(result.nodes.var) ? result.nodes.var : [];
  };
  // A scheduled draft: drafts folder row explicitly flagged scheduleDelivery.
  api.scheduledRows = async (limit = 50) =>
    (await api.listFolder(2, limit)).filter(row => row.flags?.scheduleDelivery === true);
  api.findScheduledRow = async (externalId, request) => {
    const rows = await api.scheduledRows(50);
    if (externalId) {
      const exact = rows.find(row => row.id === externalId);
      if (exact) return exact;
    }
    return rows.filter(row => row.subject === request.subject
      && api.addresses(row.to).includes(request.recipient.toLowerCase())).pop() || null;
  };
  api.uploadAttachment = async (composeId, bytes, descriptor) => {
    const sid = new URL(location.href).searchParams.get("sid");
    if (!sid) throw new Error("Mailbox session is unavailable; log in again");
    if (bytes.length !== descriptor.size) throw new Error("Confirmed attachment size mismatch");
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)))
      .map(value => value.toString(16).padStart(2, "0")).join("");
    if (digest !== descriptor.sha256) throw new Error("Confirmed attachment digest mismatch");
    const file = new File([bytes], descriptor.name, { type: "application/octet-stream" });
    const form = new FormData();
    form.append("Filedata", file, descriptor.name);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 45000);
    try {
      const response = await fetch(
        `/js6/compose/upload.jsp?sid=${encodeURIComponent(sid)}`
        + `&composeId=${encodeURIComponent(composeId)}&type=native`,
        { method: "POST", credentials: "same-origin", signal: controller.signal, body: form });
      const text = await response.text();
      if (!response.ok) throw new Error(`Attachment upload returned HTTP ${response.status}`);
      // upload.jsp answers with single-quoted pseudo-JSON; normalize before parsing.
      const parsed = JSON.parse(text.replace(/([{,])\s*'([^']+)'\s*:/g, '$1"$2":')
        .replace(/:\s*'([^']*)'/g, ': "$1"').replace(/'\s*}/g, '"}').replace(/'\s*,/g, '",'));
      if (parsed.code !== "S_OK") throw new Error(`Attachment upload rejected: ${parsed.code || text.slice(0, 120)}`);
      const info = parsed.attachInfo || parsed;
      const id = info.attachmentId ?? parsed.attachId ?? parsed.attachId;
      if (id === undefined || id === null) throw new Error("Attachment upload returned no identity");
      if (Number(info.size ?? info.actualSize) !== descriptor.size)
        throw new Error("Uploaded attachment size differs from Confirmation");
      return { id, name: info.fileName || descriptor.name };
    } finally { clearTimeout(timer); }
  };
})();
