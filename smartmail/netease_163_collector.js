async page => {
  const now = new Date().toISOString();
  const body = await page.locator("body").innerText();
  const account = (body.match(/[A-Z0-9._%+-]+@163\.com/i) || [null])[0];
  if (!page.url().includes("/js6/main.jsp") || !account) {
    return {
      status: "authentication_required",
      mailbox_address: account || "",
      observed_at: now,
      detail: "Complete 163.com login, verification, or CAPTCHA in the headed browser, then refresh again",
      coverage: { folders: [], complete: false, supported_scope_complete: false },
      messages: []
    };
  }
  const intendedMailbox = __INTENDED_MAILBOX__;
  if (account.toLowerCase() !== intendedMailbox) {
    return {
      status: "wrong_mailbox",
      mailbox_address: account.toLowerCase(),
      observed_at: now,
      detail: `Browser is logged into ${account.toLowerCase()}; intended Mailbox is ${intendedMailbox}`,
      coverage: { folders: [], complete: false, supported_scope_complete: false },
      messages: []
    };
  }

  const folderDefinitions = [
    { folder: "inbox", fid: 1, label: "收件箱" },
    { folder: "drafts", fid: 2, label: "草稿箱" },
    { folder: "sent", fid: 3, label: "已发送" },
    { folder: "deleted", fid: 4, label: "已删除" },
    { folder: "spam", fid: 5, label: "垃圾邮件" }
  ];
  const otherFolders = page.getByRole("treeitem", { name: /^其他\d+个文件夹/ }).first();
  if (await otherFolders.count() && await otherFolders.getAttribute("aria-expanded") !== "true") {
    await otherFolders.click({ timeout: 10000 });
    await page.waitForTimeout(300);
  }
  const discovered = [];
  for (const definition of folderDefinitions) {
    const locator = page.getByRole("treeitem", {
      name: new RegExp(`^${definition.label}(?:\\(|$)`)
    }).first();
    if (await locator.count()) discovered.push(definition);
  }

  const scan = await page.evaluate(async ({ definitions, mailboxAddress }) => {
    const sid = new URL(location.href).searchParams.get("sid");
    const pageSize = 50;
    const valueOf = node => {
      if (!node) return null;
      if (node.tagName === "int" || node.tagName === "long") {
        const value = Number(node.textContent || 0);
        return Number.isFinite(value) ? value : null;
      }
      if (node.tagName === "boolean") return node.textContent === "true";
      if (node.tagName === "array") return Array.from(node.children).map(valueOf);
      if (node.tagName === "object") {
        const value = {};
        for (const child of Array.from(node.children)) {
          const name = child.getAttribute("name") || child.tagName;
          const decoded = valueOf(child);
          if (Object.prototype.hasOwnProperty.call(value, name)) {
            value[name] = Array.isArray(value[name]) ? [...value[name], decoded] : [value[name], decoded];
          } else {
            value[name] = decoded;
          }
        }
        return value;
      }
      return node.textContent || "";
    };
    const xmlDocument = async response => new DOMParser().parseFromString(
      new TextDecoder("utf-8").decode(await response.arrayBuffer()), "application/xml");
    const post = async (func, xml) => fetch(
      `/js6/s?sid=${encodeURIComponent(sid)}&func=${encodeURIComponent(func)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ var: xml })
      });
    const listPayload = (fid, start) => `<?xml version="1.0"?><object><int name="fid">${fid}</int><string name="order">date</string><boolean name="desc">true</boolean><int name="limit">${pageSize}</int><int name="start">${start}</int><boolean name="skipLockedFolders">false</boolean><boolean name="returnTag">true</boolean><boolean name="returnTotal">true</boolean></object>`;
    const readPayload = id => `<?xml version="1.0"?><object><string name="id">${id}</string><boolean name="header">true</boolean><boolean name="returnImageInfo">true</boolean><boolean name="returnAntispamInfo">true</boolean><boolean name="autoName">true</boolean><boolean name="supportTNEF">true</boolean></object>`;
    const codeOf = document => document.querySelector("code")?.textContent || "";
    const addressIn = value => {
      const match = String(value || "").match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
      return match ? match[0].toLowerCase() : "";
    };
    const directionOf = row => {
      if (addressIn(row.from) === mailboxAddress) return "outbound";
      if (String(row.to || "").toLowerCase().includes(mailboxAddress)) return "inbound";
      return "ambiguous";
    };
    const statusOf = (definition, row) => {
      if (definition.folder === "inbox") return "received";
      if (definition.folder === "drafts") return "draft";
      if (definition.folder === "deleted") return "deleted";
      if (definition.folder === "spam") return "spam";
      if (definition.folder === "sent" && (row.sndStatus === 3 || row.flags?.rcptSucceed === true)) return "sent";
      return "ambiguous";
    };

    const folders = [];
    const rows = [];
    for (const definition of definitions) {
      let total = null;
      let start = 0;
      let pagesRequested = 0;
      let pagesSucceeded = 0;
      const errors = [];
      const ids = new Set();
      while (total === null || start < total) {
        pagesRequested += 1;
        try {
          const response = await post("mbox:listMessages", listPayload(definition.fid, start));
          const document = await xmlDocument(response);
          if (!response.ok || codeOf(document) !== "S_OK") {
            throw new Error(`listMessages returned HTTP ${response.status} ${codeOf(document) || "without a result code"}`);
          }
          const container = document.querySelector('array[name="var"]');
          const pageRows = Array.from(container?.children || [])
            .filter(node => node.tagName === "object").map(valueOf);
          const totalNode = document.querySelector('[name="total"]');
          const reportedTotal = Number(totalNode?.textContent);
          if (Number.isFinite(reportedTotal)) total = reportedTotal;
          pagesSucceeded += 1;
          for (const row of pageRows) {
            if (row.id && !ids.has(row.id)) {
              ids.add(row.id);
              rows.push({ definition, row, detail: null, detailError: "" });
            }
          }
          if (pageRows.length === 0 || pageRows.length < pageSize) break;
          start += pageSize;
        } catch (error) {
          errors.push(String(error?.message || error));
          break;
        }
      }
      folders.push({
        folder: definition.folder,
        folder_id: definition.fid,
        page_size: pageSize,
        declared_total: total,
        ids_enumerated: ids.size,
        pages_requested: pagesRequested,
        pages_succeeded: pagesSucceeded,
        details_requested: 0,
        detail_attempts: 0,
        details_succeeded: 0,
        details_failed: 0,
        enumeration_complete: total !== null && ids.size === total && errors.length === 0,
        detail_complete: false,
        complete: false,
        errors
      });
    }

    for (let offset = 0; offset < rows.length; offset += 5) {
      await Promise.all(rows.slice(offset, offset + 5).map(async item => {
        const folderCoverage = folders.find(folder => folder.folder_id === item.definition.fid);
        folderCoverage.details_requested += 1;
        try {
          let completed = false;
          for (let attempt = 0; attempt < 4; attempt += 1) {
            folderCoverage.detail_attempts += 1;
            const response = await post("mbox:readMessage", readPayload(item.row.id));
            const document = await xmlDocument(response);
            const code = codeOf(document);
            if (response.ok && code === "S_OK") {
              item.detail = valueOf(document.querySelector('object[name="var"]'));
              completed = true;
              break;
            }
            if (code === "FA_REQUEST_OVER_LIMIT" && attempt < 3) {
              await new Promise(resolve => setTimeout(resolve, 500 * (attempt + 1)));
              continue;
            }
            throw new Error(`readMessage returned HTTP ${response.status} ${code || "without a result code"}`);
          }
          if (!completed) throw new Error("readMessage retries were exhausted");
          folderCoverage.details_succeeded += 1;
        } catch (error) {
          item.detailError = String(error?.message || error);
          folderCoverage.details_failed += 1;
        }
      }));
    }
    for (const folder of folders) {
      folder.detail_complete = folder.enumeration_complete &&
        folder.details_requested === folder.ids_enumerated && folder.details_failed === 0;
      folder.complete = folder.enumeration_complete && folder.detail_complete;
    }

    const messages = rows.map(item => {
      const direction = directionOf(item.row);
      const status = statusOf(item.definition, item.row);
      const counterpart = direction === "outbound" ? item.row.to : item.row.from;
      let ambiguity = "";
      if (direction === "ambiguous") ambiguity = "Message direction could not be established from authenticated Mailbox headers";
      if (!item.row.id) ambiguity = ambiguity || "Canonical platform message ID was unavailable";
      if (status === "ambiguous") ambiguity = ambiguity || "Sent delivery status was not established";
      return {
        direction,
        folder: item.definition.folder,
        platform_reference: item.row.id || "",
        counterpart: counterpart || "",
        subject: item.detail?.subject || item.row.subject || "",
        observed_time: item.detail?.sentDate || item.row.sentDate || item.row.receivedDate || "",
        status,
        ambiguity,
        evidence: {
          source: "163.com mbox:listMessages plus metadata-only mbox:readMessage",
          list: item.row,
          detail: item.detail,
          detail_error: item.detailError,
          body: {
            fetched: false,
            reason: "Body HTML is excluded because its endpoint changes unread state"
          }
        }
      };
    });
    return { folders, messages };
  }, { definitions: discovered, mailboxAddress: account.toLowerCase() });

  const supportedScopeComplete = discovered.length === folderDefinitions.length &&
    scan.folders.every(folder => folder.complete);
  return {
    status: supportedScopeComplete ? "complete" : "partial",
    mailbox_address: account.toLowerCase(),
    observed_at: now,
    detail: "Read-only folder enumeration and metadata detail scan in the authenticated 163.com browser session",
    coverage: {
      scope: "recognized built-in folders discovered in the live DOM",
      complete: false,
      supported_scope_complete: supportedScopeComplete,
      folder_discovery: {
        method: "live_dom",
        recognized: discovered.map(folder => ({ folder: folder.folder, folder_id: folder.fid })),
        expected_recognized: folderDefinitions.length,
        complete: discovered.length === folderDefinitions.length
      },
      folders: scan.folders,
      limitations: [
        "Virtual views and unrecognized custom folders are not scanned",
        "Message bodies are not fetched because the body endpoint changes unread state",
        "Whole-mailbox completeness is not claimed beyond the recognized built-in folder scope"
      ]
    },
    messages: scan.messages
  };
}
