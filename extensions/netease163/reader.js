/* Full-content reader running in the page's MAIN world.
 *
 * It drives the official 163 webmail runtime ($.DataAction / $S) instead of
 * scraping the DOM or hand-serializing XML. Every call used here was verified
 * against the live mailbox as a read-only operation:
 *   - mbox:getAllFolders  : system folder inventory (no DOM tree walking)
 *   - mbox:listMessages   : paged folder rows
 *   -mbox:readMessage    : message envelope + MIME part descriptors
 *   - mbox:restoreDraft  : draft Compose model (subject/recipients/body/attachments)
 *   - mbox:getMessageData : raw text/html MIME part bytes (GET, no read-state change)
 *   - read/readdata.jsp   : attachment bytes / full RFC822 message (GET)
 *
 * mbox:readMessage is always issued WITHOUT markRead, and message data is fetched
 * through getMessageData, so observation never flips the unread flag. Locked drafts
 * are never auto-unlocked: only their envelope is reported. */
(() => {
  if (globalThis.SmartMail163Reader) return;
  const api = globalThis.SmartMail163Reader = {};

  const PAGE_SIZE = 200;
  const HARD_MAX_ROWS = 5000;
  const MAX_PART_BYTES = 2 * 1024 * 1024;
  const DETAIL_CONCURRENCY = 4;
  const PART_CONCURRENCY = 4;
  const FOLDER_DEFINITIONS = [
    { folder: "inbox", fid: 1, label: "收件箱" },
    { folder: "drafts", fid: 2, label: "草稿箱" },
    { folder: "sent", fid: 3, label: "已发送" },
    { folder: "deleted", fid: 4, label: "已删除" },
    { folder: "spam", fid: 5, label: "垃圾邮件" }
  ];

  api.runtimeAvailable = () => Boolean(globalThis.$?.DataAction && typeof globalThis.$S === "function");
  api.delay = ms => new Promise(resolve => setTimeout(resolve, ms));
  api.assertDeadline = deadline => {
    if (!Number.isFinite(deadline) || Date.now() >= deadline) throw new Error("Command expired; reconnect and reconcile");
  };

  const setting = name => {
    try { return globalThis.$S(name); } catch { return ""; }
  };
  api.account = () => {
    const value = String(setting("uid") || "").trim().toLowerCase();
    return value.endsWith("@163.com") ? value : "";
  };
  api.observationFailure = (status, detail, mailbox = "") => ({
    status, detail, mailbox_address: mailbox, observed_at: new Date().toISOString(),
    coverage: { complete: false, folders: [] }, messages: []
  });

  const wmsvr = (func, body) => new Promise((resolve, reject) => {
    let settled = false;
    const action = new globalThis.$.DataAction();
    action.wmsvr({
      func, body, ignoreError: true,
      call(response) {
        if (settled) return;
        settled = true;
        resolve(response || {});
      },
      error(error) {
        if (settled) return;
        settled = true;
        reject(new Error(error?.message || error?.code || `${func} failed`));
      }
    });
  });

  const ADDRESS_RE = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi;
  const addressesIn = value => [...new Set((String(value || "").match(ADDRESS_RE) || []).map(a => a.toLowerCase()))];

  // Prefer the page's own mailbox-address parser (handles quoted display names);
  // fall back to a regex when the runtime helper is unavailable.
  const parseAddresses = value => {
    const text = String(value || "");
    const out = [];
    try {
      const parsed = globalThis.$?.Uri?.getEmails?.(text);
      for (const item of parsed?.match || []) {
        const address = String(item?.address || "").trim().toLowerCase();
        if (address) out.push({ address, name: String(item?.name || "").trim() });
      }
    } catch { /* fall through to regex */ }
    if (!out.length) for (const address of addressesIn(text)) out.push({ address, name: "" });
    return out;
  };
  const addressList = value => {
    if (Array.isArray(value)) return value.flatMap(parseAddresses);
    return parseAddresses(value);
  };

  const stampOf = value => {
    if (value === null || value === undefined || value === "") return "";
    if (value instanceof Date) return Number.isNaN(value.getTime()) ? "" : value.toISOString();
    if (typeof value === "object" && typeof value.getTime === "function") {
      const ms = Number(value.getTime());
      return Number.isFinite(ms) ? new Date(ms).toISOString() : "";
    }
    if (typeof value === "number" && Number.isFinite(value)) {
      return new Date(value < 1e12 ? value * 1000 : value).toISOString();
    }
    const text = String(value).trim();
    if (/^\d{10,13}$/.test(text)) return new Date(Number(text) < 1e12 ? Number(text) * 1000 : Number(text)).toISOString();
    const parsed = new Date(text);
    return Number.isNaN(parsed.getTime()) ? text : parsed.toISOString();
  };

  const htmlToText = html => {
    const raw = String(html || "");
    if (!raw) return "";
    try {
      const doc = new DOMParser().parseFromString(raw, "text/html");
      doc.querySelectorAll("script,style,noscript").forEach(node => node.remove());
      const block = doc.createElement("div");
      block.innerHTML = doc.body ? doc.body.innerHTML : raw;
      block.querySelectorAll("br").forEach(br => br.replaceWith("\n"));
      block.querySelectorAll("p,div,li,tr,h1,h2,h3,h4,h5,h6").forEach(node => node.append("\n"));
      return block.textContent
        .replace(/ /g, " ")
        .replace(/[ \t]+\n/g, "\n")
        .replace(/\n{3,}/g, "\n\n")
        .trim();
    } catch {
      return raw.replace(/<br\s*\/?>(\n)?/gi, "\n").replace(/<[^>]+>/g, "").trim();
    }
  };

  const headerOf = (headerRaw, name) => {
    const match = String(headerRaw || "").match(
      new RegExp(`^${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}:\\s*(.+?)\\r?$`, "mi"));
    return match ? match[1].trim() : "";
  };
  const cleanMessageId = value => {
    const match = String(value || "").match(/<[^<>]+>/);
    return (match ? match[0] : String(value || "").trim()).toLowerCase();
  };

  async function listFolders() {
    const response = await wmsvr("mbox:getAllFolders", {});
    if (response.code !== "S_OK") throw new Error(`getAllFolders returned ${response.code || "without a result code"}`);
    const rows = Array.isArray(response.var) ? response.var : [];
    return FOLDER_DEFINITIONS.map(definition => ({
      ...definition,
      present: rows.some(row => Number(row?.id) === definition.fid || String(row?.name) === definition.label),
      custom_count: Math.max(0, rows.filter(row => row?.flags?.system !== true).length)
    }));
  }

  async function listFolder(fid) {
    const rows = [];
    const ids = new Set();
    let total = null;
    let start = 0;
    while ((total === null || start < total) && start < HARD_MAX_ROWS) {
      const response = await wmsvr("mbox:listMessages", {
        fid, order: "date", desc: true, limit: PAGE_SIZE, start,
        summaryWindowSize: 0, returnTotal: true, skipLockedFolders: false
      });
      if (response.code !== "S_OK") throw new Error(`listMessages(${fid}) returned ${response.code || "without a result code"}`);
      const page = Array.isArray(response.var) ? response.var : [];
      const reported = Number(response.total);
      if (Number.isFinite(reported)) total = reported;
      for (const row of page) {
        const id = String(row?.id || row?.mid || "");
        if (id && !ids.has(id)) { ids.add(id); rows.push(row); }
      }
      if (page.length < PAGE_SIZE) break;
      start += PAGE_SIZE;
    }
    return { rows, total: total ?? ids.size, capped: total !== null && total > HARD_MAX_ROWS };
  }

  // Official read-view envelope request. markRead is deliberately never sent:
  // verified live that omitting it leaves the unread flag untouched.
  async function readEnvelope(id, part) {
    const body = {
      id, header: true, returnImageInfo: true, returnAntispamInfo: true,
      autoName: true, supportTNEF: true,
      returnHeaders: {
        "Resent-From": "A", Sender: "A", "List-Unsubscribe": "A",
        "Reply-To": "A", "In-Reply-To": "A", References: "A", From: ""
      }
    };
    if (part) body.part = part;
    const response = await wmsvr("mbox:readMessage", body);
    if (response.code !== "S_OK") {
      const error = new Error(`readMessage returned ${response.code || "without a result code"}`);
      error.code = response.code;
      throw error;
    }
    return response.var && typeof response.var === "object" && !Array.isArray(response.var) ? response.var : null;
  }

  async function restoreDraft(id) {
    const response = await wmsvr("mbox:restoreDraft", { id });
    if (response.code !== "S_OK") return null;
    return response.var && typeof response.var === "object" && !Array.isArray(response.var) ? response.var : null;
  }

  const decodePart = async buffer => {
    let charset = "utf-8";
    for (const [key, value] of buffer.headers) {
      if (key.toLowerCase() === "content-type") {
        const match = value.match(/charset=([^;\s]+)/i);
        if (match) charset = match[1].toLowerCase().replace(/^gb2312$/, "gbk");
      }
    }
    let text;
    try {
      text = new TextDecoder(charset === "gb2312" ? "gbk" : charset).decode(buffer.bytes);
    } catch {
      text = new TextDecoder("utf-8").decode(buffer.bytes);
    }
    return text;
  };

  // Raw MIME part bytes via the official GET endpoint. Verified read-only: the
  // unread flag and folder state are untouched.
  async function fetchPart(mid, part, { text = false } = {}) {
    const sid = setting("sid");
    if (!sid) throw new Error("Mailbox session is unavailable; log in again");
    const query = new URLSearchParams({ sid, func: "mbox:getMessageData", mid, part: String(part) });
    if (text) query.set("mode", "text");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(`/js6/s?${query}`, {
        method: "GET", credentials: "same-origin", signal: controller.signal
      });
      if (!response.ok) throw new Error(`getMessageData returned HTTP ${response.status}`);
      const bytes = new Uint8Array(await response.arrayBuffer());
      const truncated = bytes.byteLength > MAX_PART_BYTES;
      const headers = Array.from(response.headers.entries());
      const decoded = await decodePart({ bytes: truncated ? bytes.slice(0, MAX_PART_BYTES) : bytes, headers });
      return {
        text: decoded, truncated, bytes: bytes.byteLength,
        content_type: response.headers.get("content-type") || ""
      };
    } finally {
      clearTimeout(timer);
    }
  }

  const attachmentOf = item => {
    const part = String(item?.id ?? item?.part ?? item?.partId ?? "");
    const name = String(item?.filename || item?.name || item?.fileName || "").trim();
    if (!part && !name) return null;
    return {
      part, name: name || `Attachment ${part}`,
      size: Number(item?.size ?? item?.contentLength ?? 0) || 0,
      content_type: String(item?.contentType || item?.mimeType || "").trim(),
      content_id: String(item?.contentId || item?.cid || "").trim(),
      inlined: Boolean(item?.inlined)
    };
  };

  const directionOf = (row, envelope, mailbox) => {
    const from = addressList(envelope?.from ?? row?.from).map(a => a.address);
    const to = addressList(envelope?.to ?? row?.to).map(a => a.address);
    const cc = addressList(envelope?.cc).map(a => a.address);
    if (from.includes(mailbox)) return "outbound";
    if ([...to, ...cc].includes(mailbox)) return "inbound";
    if (addressesIn(row?.from).includes(mailbox)) return "outbound";
    if (addressesIn(row?.to).includes(mailbox)) return "inbound";
    return "ambiguous";
  };

  const statusOf = (definition, row, envelope) => {
    const flags = envelope?.flags || row?.flags || {};
    if (definition.folder === "inbox") return "received";
    if (definition.folder === "drafts" && flags.scheduleDelivery === true) return "scheduled";
    if (definition.folder === "drafts") return "draft";
    if (definition.folder === "deleted") return "deleted";
    if (definition.folder === "spam") return "spam";
    if (definition.folder === "sent") {
      let sndStatus = row?.sndStatus;
      if (typeof sndStatus !== "number") {
        if (flags.rcptSucceed) sndStatus = 3;
        else if (flags.rcptFailed) sndStatus = 4;
      }
      if (sndStatus === 3 && !flags.rcptFailed) return "sent";
    }
    return "ambiguous";
  };

  async function pool(items, concurrency, worker) {
    let cursor = 0;
    const runners = Array.from({ length: Math.min(concurrency, items.length) }, async () => {
      while (cursor < items.length) {
        const index = cursor++;
        await worker(items[index], index);
      }
    });
    await Promise.all(runners);
  }

  api.observe = async (mailboxAddress, deadline) => {
    if (!api.runtimeAvailable()) return api.observationFailure("runtime_unavailable", "Official webmail runtime is unavailable", "");
    const account = api.account();
    if (account !== mailboxAddress) return api.observationFailure(
      account ? "wrong_mailbox" : "authentication_required",
      "Reconnect the intended logged-in Mailbox", account);

    const observedAt = new Date().toISOString();
    let definitions;
    try {
      definitions = (await listFolders()).filter(definition => definition.present);
    } catch (error) {
      return api.observationFailure("failed", String(error.message || error), account);
    }

    const coverage = [];
    const work = [];
    for (const definition of definitions) {
      api.assertDeadline(deadline);
      const folderCoverage = {
        folder: definition.folder, folder_id: definition.fid,
        page_size: PAGE_SIZE, declared_total: 0, ids_enumerated: 0,
        enumeration_complete: false,
        details_requested: 0, details_succeeded: 0, details_failed: 0,
        contents_requested: 0, contents_succeeded: 0, contents_failed: 0,
        drafts_restored: 0, draft_restore_failures: 0, locked_skipped: 0,
        attachments_seen: 0, complete: false, errors: []
      };
      coverage.push(folderCoverage);
      try {
        const { rows, total, capped } = await listFolder(definition.fid);
        folderCoverage.declared_total = total;
        folderCoverage.ids_enumerated = rows.length;
        folderCoverage.capped = capped;
        folderCoverage.enumeration_complete = !capped && rows.length === total;
        for (const row of rows) work.push({ definition, row, folderCoverage });
      } catch (error) {
        folderCoverage.errors.push(String(error.message || error));
        folderCoverage.enumeration_complete = false;
      }
    }

    await pool(work, DETAIL_CONCURRENCY, async item => {
      api.assertDeadline(deadline);
      const { definition, row, folderCoverage } = item;
      folderCoverage.details_requested += 1;
      try {
        item.envelope = await readEnvelope(row.id);
        folderCoverage.details_succeeded += 1;
      } catch (error) {
        item.envelopeError = String(error.message || error);
        folderCoverage.details_failed += 1;
        return;
      }

      // Drafts: load the native Compose model so imported drafts carry full
      // recipients/body/attachments and can be revised and re-sent. Locked drafts
      // stay envelope-only; unlocking is an explicit mailbox mutation.
      if (definition.folder === "drafts") {
        const flags = item.envelope?.flags || row.flags || {};
        if (flags.locked) {
          folderCoverage.locked_skipped += 1;
          item.locked = true;
        } else {
          try {
            item.draft = await restoreDraft(row.id);
            if (item.draft) folderCoverage.drafts_restored += 1;
          } catch (error) {
            item.draftError = String(error.message || error);
            folderCoverage.draft_restore_failures += 1;
          }
        }
      }

      // MIME parts → full text/html content via getMessageData.
      const envelope = item.envelope || {};
      const parts = [];
      if (envelope.text && envelope.text.id != null) parts.push({ kind: "text", part: envelope.text.id });
      if (envelope.html && envelope.html.id != null) parts.push({ kind: "html", part: envelope.html.id });
      const content = { fetched: false, text: "", html: "", text_part: "", html_part: "", charset: "", truncated: false, sources: [], error: "" };
      await pool(parts, PART_CONCURRENCY, async ({ kind, part }) => {
        folderCoverage.contents_requested += 1;
        try {
          const result = await fetchPart(row.id, part, { text: kind === "text" });
          folderCoverage.contents_succeeded += 1;
          content.fetched = true;
          content.sources.push(`${kind}:${part}`);
          const charset = result.content_type.match(/charset=([^;\s]+)/i)?.[1]?.toLowerCase() || "";
          if (charset) content.charset = charset;
          if (result.truncated) content.truncated = true;
          if (kind === "text") { content.text = result.text; content.text_part = String(part); }
          else { content.html = result.text; content.html_part = String(part); }
        } catch (error) {
          folderCoverage.contents_failed += 1;
          content.error = content.error || String(error.message || error);
        }
      });
      if (!content.text && content.html) content.text = htmlToText(content.html);
      item.content = content;

      item.attachments = (envelope.attachments || [])
        .map(attachmentOf)
        .filter(Boolean)
        .map(attachment => ({
          ...attachment,
          download_path: `/js6/read/readdata.jsp?mid=${encodeURIComponent(row.id)}`
            + `&part=${encodeURIComponent(attachment.part)}&mode=download&l=read&action=download_attach`
        }));
      folderCoverage.attachments_seen += item.attachments.length;
    });

    const messages = work.map(item => {
      const { definition, row } = item;
      const envelope = item.envelope || {};
      const direction = directionOf(row, envelope, account);
      const status = statusOf(definition, row, envelope);
      const counterpart = direction === "outbound"
        ? (addressList(envelope.to ?? row.to)[0]?.address || addressesIn(row.to)[0] || "")
        : (addressList(envelope.from ?? row.from)[0]?.address || addressesIn(row.from)[0] || "");
      const flags = envelope.flags || row.flags || {};
      const headerRaw = envelope.headerRaw || "";
      const messageId = cleanMessageId(headerOf(headerRaw, "Message-ID") || headerOf(headerRaw, "Message-Id"));

      let ambiguity = "";
      if (direction === "ambiguous") ambiguity = "Message direction could not be established from authenticated Mailbox headers";
      if (!row.id) ambiguity = ambiguity || "Canonical platform message ID was unavailable";
      if (status === "ambiguous") ambiguity = ambiguity || "Sent delivery status was not established";
      if (item.envelopeError) ambiguity = ambiguity || `Envelope unavailable: ${item.envelopeError}`;
      if (!item.content?.fetched) ambiguity = ambiguity || "Message content could not be fetched";
      if (item.locked) ambiguity = ambiguity || "Draft is locked; content intentionally not restored";

      const attachments = item.attachments || [];
      const cloudLinks = item.draft ? Array.isArray(item.draft.link)
        ? item.draft.link.flatMap(link => link && typeof link === "object"
            ? [{ name: String(link.name || link.fileName || ""), url: String(link.url || link.href || "") }] : [])
        : [] : [];

      const message = {
        direction,
        folder: definition.folder,
        platform_reference: row.id || "",
        counterpart,
        subject: envelope.subject || row.subject || "",
        observed_time: stampOf(envelope.sentDate ?? row.sentDate ?? row.receivedDate),
        status,
        message_id: messageId,
        in_reply_to: cleanMessageId(headerOf(headerRaw, "In-Reply-To")),
        references: headerOf(headerRaw, "References").match(/<[^<>]+>/g)?.map(v => v.toLowerCase()) || [],
        participants: {
          from: addressList(envelope.from ?? row.from),
          to: addressList(envelope.to ?? row.to),
          cc: addressList(envelope.cc),
          bcc: addressList(envelope.bcc)
        },
        content: {
          fetched: Boolean(item.content?.fetched),
          text: item.content?.text || "",
          html: item.content?.html || "",
          truncated: Boolean(item.content?.truncated),
          charset: item.content?.charset || "",
          sources: item.content?.sources || [],
          error: item.content?.error || ""
        },
        attachments,
        ambiguity,
        evidence: {
          source: "163.com official runtime: listMessages + readMessage + getMessageData"
            + (item.draft ? " + restoreDraft" : ""),
          list: row,
          detail: envelope,
          envelope_error: item.envelopeError || "",
          draft_restore_error: item.draftError || "",
          content: { fetched: Boolean(item.content?.fetched), sources: item.content?.sources || [] }
        }
      };

      if (item.draft) {
        const draft = item.draft;
        const bodyHtml = draft.content == null ? "" : String(draft.content);
        message.compose = {
          detail_source: "mbox:restoreDraft",
          to: addressList(draft.to),
          cc: addressList(draft.cc),
          bcc: addressList(draft.bcc),
          is_html: draft.isHtml !== false,
          body_html: bodyHtml,
          body_text: htmlToText(bodyHtml),
          account: String(draft.account || "").trim(),
          priority: Number(draft.priority || 0) || 0,
          schedule_date: stampOf(flags.scheduleDelivery ? (row.sentDate ?? draft.scheduleDate) : draft.scheduleDate),
          scheduled_draft: flags.scheduleDelivery === true,
          attachments: (draft.attachments || [])
            .map(attachmentOf).filter(Boolean)
            .map(attachment => ({
              ...attachment,
              download_path: `/js6/read/readdata.jsp?mid=${encodeURIComponent(row.id)}`
                + `&part=${encodeURIComponent(attachment.part)}&mode=download&l=read&action=download_attach`
            })),
          cloud_links: cloudLinks
        };
      }
      return message;
    });

    for (const folder of coverage) {
      folder.detail_complete = folder.enumeration_complete
        && folder.details_requested === folder.ids_enumerated
        && folder.details_failed === 0;
      folder.complete = folder.detail_complete
        && folder.contents_failed === 0
        && folder.draft_restore_failures === 0;
    }
    const supportedScopeComplete = definitions.length === FOLDER_DEFINITIONS.length
      && coverage.every(folder => folder.complete);
    const customFolders = definitions[0]?.custom_count ?? 0;
    return {
      status: supportedScopeComplete ? "complete" : "partial",
      mailbox_address: account, observed_at: observedAt,
      detail: "Dedicated extension full-content observation via official webmail runtime",
      coverage: {
        complete: false, supported_scope_complete: supportedScopeComplete, folders: coverage,
        scope: "recognized built-in folders discovered through mbox:getAllFolders",
        limitations: [
          ...(customFolders ? ["Custom folders excluded"] : []),
          `At most ${HARD_MAX_ROWS} rows per folder`,
          `Message parts larger than ${MAX_PART_BYTES} bytes are truncated`,
          "Attachment bytes are not embedded; download_path locates them on demand"
        ]
      },
      messages
    };
  };
})();
