/* Read-only built-in folder scan. No message-body endpoint or mailbox mutations. */
(() => {
  const api = globalThis.SmartMail163;
  api.observe = async (mailboxAddress, deadline) => {
    const account = api.account();
    if (account !== mailboxAddress) return api.observationFailure(
      account ? "wrong_mailbox" : "authentication_required", "Reconnect the intended logged-in Mailbox", account);
    const folderDefinitions = [
      { folder: "inbox", fid: 1, label: "收件箱" },
      { folder: "drafts", fid: 2, label: "草稿箱" },
      { folder: "sent", fid: 3, label: "已发送" },
      { folder: "deleted", fid: 4, label: "已删除" },
      { folder: "spam", fid: 5, label: "垃圾邮件" }
    ];
    const tree = Array.from(document.querySelectorAll('[role="treeitem"]'));
    const other = tree.find(node => /^其他\d+个文件夹/.test(node.textContent.trim()));
    if (other && other.getAttribute("aria-expanded") !== "true") {
      other.click();
      await api.delay(300);
    }
    const labels = Array.from(document.querySelectorAll('[role="treeitem"]')).map(node => node.textContent.trim());
    const definitions = folderDefinitions.filter(definition => labels.some(
      label => label === definition.label || label.startsWith(definition.label + "(")));

    const pageSize = 50;
    const { valueOf, xmlDocument, post, codeOf } = api;
    const listPayload = (fid, start) => `<?xml version="1.0"?><object><int name="fid">${fid}</int><string name="order">date</string><boolean name="desc">true</boolean><int name="limit">${pageSize}</int><int name="start">${start}</int><boolean name="skipLockedFolders">false</boolean><boolean name="returnTag">true</boolean><boolean name="returnTotal">true</boolean></object>`;
    const readPayload = id => `<?xml version="1.0"?><object><string name="id">${api.escapeXML(id)}</string><boolean name="header">true</boolean><boolean name="returnImageInfo">true</boolean><boolean name="returnAntispamInfo">true</boolean><boolean name="autoName">true</boolean><boolean name="supportTNEF">true</boolean></object>`;
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
      while ((total === null || start < total) && start < 5000) {
        api.assertDeadline(deadline);
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
          const reportedTotal = totalNode ? Number(totalNode.textContent) : NaN;
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
      api.assertDeadline(deadline);
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

    const supportedScopeComplete = definitions.length === folderDefinitions.length && folders.every(folder => folder.complete);
    return {
      status: supportedScopeComplete ? "complete" : "partial", mailbox_address: account,
      observed_at: new Date().toISOString(), detail: "Dedicated extension metadata-only observation",
      coverage: { complete: false, supported_scope_complete: supportedScopeComplete, folders,
        scope: "recognized built-in folders discovered in the connected tab",
        limitations: ["Custom folders excluded", "Message bodies excluded to preserve unread state", "At most 5000 rows per folder"] },
      messages
    };
  };
})();
