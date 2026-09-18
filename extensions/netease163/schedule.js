/* Confirmed native schedules, operator-controlled cancellation and conditional Recall.
   Every call uses fixed wmsvr funcs and requires a transport permit from the core. */
(() => {
  const api = globalThis.SmartMail163;

  const reply = (payload, outcome, detail, extra = {}) => ({
    outcome, detail, reference: "", mailbox_address: payload.sender.toLowerCase(),
    observed_at: new Date().toISOString(), ...extra
  });
  const authFailure = payload => {
    const account = api.account();
    return reply(payload, "authentication_required",
      account && account !== payload.sender.toLowerCase()
        ? `Connected Mailbox is ${account}; intended Mailbox is ${payload.sender.toLowerCase()}`
        : "Reconnect the intended logged-in Mailbox before the confirmed operation",
      { mailbox_address: account || "" });
  };
  const midOf = externalId => {
    const text = String(externalId || "");
    const index = text.indexOf(":");
    return index >= 0 ? text.slice(index + 1) : text;
  };
  const rowMatches = (row, payload) => row.subject === payload.subject
    && api.addresses(row.to).includes(payload.recipient.toLowerCase());
  const waitFor = async (predicate, { timeout = 15000, interval = 700, deadline } = {}) => {
    const until = Math.min(deadline || Infinity, Date.now() + timeout);
    let value = await predicate();
    while (!value && Date.now() < until) {
      await api.delay(interval);
      value = await predicate();
    }
    return value;
  };

  api.placeSchedule = async (command, encodedFiles) => {
    api.assertDeadline(command.deadline);
    const payload = command.payload;
    if (payload.kind !== "scheduled") throw new Error("Only confirmed native schedules are supported");
    if (api.account() !== payload.sender.toLowerCase()) return authFailure(payload);
    const epoch = Number(payload.scheduled_epoch_ms);
    if (!Number.isFinite(epoch) || epoch <= Date.now())
      return reply(payload, "failed", "The confirmed schedule time is missing or has elapsed");
    const composeId = "c:" + Date.now();
    let submitted = false;
    let externalId = "";
    try {
      const descriptors = payload.attachments || [];
      const attachmentIds = [];
      for (let index = 0; index < encodedFiles.length; index += 1) {
        api.assertDeadline(command.deadline);
        const bytes = Uint8Array.from(atob(encodedFiles[index]), char => char.charCodeAt(0));
        const uploaded = await api.uploadAttachment(composeId, bytes, descriptors[index]);
        attachmentIds.push({ id: uploaded.id });
      }
      const body = {
        id: composeId, action: "schedule", returnInfo: false, notifyEML: true,
        attrs: {
          account: payload.sender.toLowerCase(),
          to: [payload.recipient.toLowerCase()], cc: [], bcc: [],
          subject: payload.subject,
          // Send as HTML so paragraph structure and inline formatting in the
          // confirmed body (italics, font size, color) survive. Plain text is
          // escaped with one block per line and projects back exactly.
          content: api.composeBodyHtml({ html: payload.body_html, text: payload.body }),
          isHtml: true, priority: 3, requestReadReceipt: false,
          saveSentCopy: true, charset: "GBK",
          scheduleDate: new Date(epoch),
          attachments: attachmentIds
        }
      };
      const result = await api.wmsvr("mbox:compose", body);
      submitted = true;
      if (result.code !== "S_OK" || !result.nodes.scheduledSent?.mid) {
        return reply(payload, "unknown",
          `mbox:compose returned ${result.code || "without a result code"}; reconcile before retrying`,
          { response_code: result.code });
      }
      externalId = result.code === "S_OK"
        ? `${result.nodes.scheduledSent.msid}:${result.nodes.scheduledSent.mid}` : "";
      const expectedStamp = api.beijingStamp(new Date(epoch));
      const row = await waitFor(() => api.scheduledRows(50).then(rows =>
        rows.find(item => item.id === externalId
          && item.flags?.scheduleDelivery === true
          && rowMatches(item, payload)
          && String(item.sentDate || "").replace("T", " ") === expectedStamp) || null),
        { deadline: command.deadline });
      if (!row) {
        return reply(payload, "unknown",
          "Schedule was accepted but its scheduled draft could not be verified; reconcile",
          { external_id: externalId, reference: externalId,
            evidence: { scheduled_sent: result.nodes.scheduledSent } });
      }
      return reply(payload, "scheduled", "Native schedule placed and verified in the Drafts folder", {
        reference: externalId, external_id: externalId,
        evidence: {
          folder: "drafts", external_id: externalId,
          msid: result.nodes.scheduledSent.msid, mid: result.nodes.scheduledSent.mid,
          scheduled_beijing: row.sentDate, schedule_delivery: true,
          recipient: payload.recipient.toLowerCase(), subject: payload.subject,
          scheduled_epoch_ms: epoch
        }
      });
    } catch (error) {
      const detail = String(error.message || error);
      if (!api.account() || api.account() !== payload.sender.toLowerCase())
        return authFailure(payload);
      return reply(payload, submitted ? "unknown" : "failed", detail,
        externalId ? { external_id: externalId, reference: externalId } : {});
    }
  };

  api.cancelSchedule = async command => {
    api.assertDeadline(command.deadline);
    const payload = command.payload;
    if (payload.kind !== "cancel_schedule") throw new Error("Only confirmed schedule cancellation is supported");
    if (api.account() !== payload.sender.toLowerCase()) return authFailure(payload);
    const externalId = String(payload.external_id || "");
    const evidence = { external_id: externalId, recipient: payload.recipient.toLowerCase(),
      subject: payload.subject };
    try {
      const before = await api.scheduledRows(50)
        .then(rows => rows.find(row => row.id === externalId) || null);
      if (!before) {
        // The commitment may already have fired or been removed externally.
        const sent = await api.listFolder(3, 50)
          .then(rows => rows.find(row => row.id === externalId) || null);
        if (sent && (sent.sndStatus === 3 || sent.flags?.rcptSucceed === true))
          return reply(payload, "already_sent",
            "The scheduled message was Sent before cancellation; its Sent Record stays frozen",
            { reference: externalId, external_id: externalId,
              evidence: { ...evidence, folder: "sent", sent: sent } });
        const trash = await api.listFolder(4, 50)
          .then(rows => rows.find(row => row.id === externalId) || null);
        if (trash)
          return reply(payload, "already_cancelled",
            "The external scheduled draft was already removed (observed in Deleted)",
            { reference: externalId, external_id: externalId,
              evidence: { ...evidence, folder: "deleted" } });
        return reply(payload, "unknown",
          "The external scheduled draft is not observable; removal cannot be asserted, so pause",
          { external_id: externalId, reference: externalId, evidence });
      }
      const move = await api.wmsvr("mbox:updateMessageInfos",
        { ids: [externalId], attrs: { fid: 4 } });
      if (move.code !== "S_OK")
        return reply(payload, "unknown", `Removal request returned ${move.code}; reconcile`, evidence);
      const removed = await waitFor(async () => {
        const drafts = await api.scheduledRows(50);
        if (drafts.some(row => row.id === externalId)) return false;
        const trash = await api.listFolder(4, 50);
        return trash.some(row => row.id === externalId) ? { trash: true } : null;
      }, { deadline: command.deadline });
      if (!removed)
        return reply(payload, "unknown", "Removal could not be verified; pause rather than asserting Cancellation",
          { external_id: externalId, reference: externalId, evidence });
      return reply(payload, "removed", "Observed removal of the external scheduled draft before recording Cancellation",
        { reference: externalId, external_id: externalId,
          evidence: { ...evidence, folder_drafts: false, folder_deleted: true,
            observed_removed_at: new Date().toISOString() } });
    } catch (error) {
      const detail = String(error.message || error);
      if (!api.account() || api.account() !== payload.sender.toLowerCase())
        return authFailure(payload);
      return reply(payload, "unknown", detail, { external_id: externalId, evidence });
    }
  };

  // Recall is separately gated and never blocks completion; platform eligibility
  // (recallable) comes from the full letter endpoint, so this only ever reports.
  api.recallMessage = async command => {
    api.assertDeadline(command.deadline);
    const payload = command.payload;
    if (payload.kind !== "recall") throw new Error("Only a confirmed Recall is supported");
    if (api.account() !== payload.sender.toLowerCase()) return authFailure(payload);
    const base = {
      reference: payload.external_id || "", external_id: payload.external_id || "",
      mailbox_address: payload.sender.toLowerCase(), observed_at: new Date().toISOString()
    };
    try {
      const result = await api.wmsvr("mbox:recallMessage", { mid: midOf(payload.external_id) });
      const recallResult = result.nodes.recallresult || result.nodes.recallResult || {};
      const codes = Object.values(recallResult).map(value => Number(value?.code ?? value)).filter(Number.isFinite);
      const evidence = { response_code: result.code, recall_result: recallResult };
      if (result.code === "FA_UNSUPPORT_RECALL")
        return { ...base, outcome: "unsupported", detail: "This platform or message does not support Recall", evidence };
      if (result.code === "FA_MAIL_EXPIRED")
        return { ...base, outcome: "ineligible", detail: "The Recall eligibility window has elapsed", evidence };
      if (result.code !== "S_OK")
        return { ...base, outcome: "failed", detail: `recallMessage returned ${result.code}`, evidence };
      if (codes.some(code => code === 2 || code === 3))
        return { ...base, outcome: "recalled", detail: "Platform reported a successful Recall", evidence };
      if (codes.some(code => code === 0 || code === 1))
        return { ...base, outcome: "recall_pending", detail: "Recall is in progress; inspect the result later", evidence };
      return { ...base, outcome: "recall_failed",
        detail: `Platform reported failed Recall result(s): ${codes.join(",") || "unknown"}`, evidence };
    } catch (error) {
      return { ...base, outcome: "unknown", detail: String(error.message || error), evidence: {} };
    }
  };
})();
