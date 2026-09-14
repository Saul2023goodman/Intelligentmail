async page => {
  const request = __SEND_REQUEST__;
  const attachmentFiles = __ATTACHMENT_FILES__;
  const startedAt = Date.now();
  const stamp = () => new Date().toISOString();
  const reply = (outcome, detail, extra) => Object.assign({
    outcome: outcome,
    detail: detail,
    mailbox_address: "",
    reference: "",
    observed_at: stamp()
  }, extra || {});

  const context = page.context();

  // A native dialog (alert/confirm) blocks the CLI's evaluation context and
  // makes every later command fail, so accept dialogs as they appear and keep
  // their text so the outcome can report what was acknowledged.
  const dialogLog = [];
  const handleDialogs = target => {
    try {
      target.on("dialog", dialog => {
        dialogLog.push({ type: dialog.type(), message: String(dialog.message()).slice(0, 200) });
        dialog.accept().catch(() => {});
      });
    } catch (error) {
      // Some targets do not emit dialog events.
    }
  };
  handleDialogs(page);
  for (const open of context.pages()) {
    handleDialogs(open);
  }
  context.on("page", handleDialogs);

  const accountIn = text => {
    const match = String(text || "").match(/[A-Z0-9._%+-]+@163\.com/i);
    return match ? match[0].toLowerCase() : "";
  };
  const homePage = () => context.pages().find(
    candidate => candidate.url().includes("/js6/main.jsp"));

  // 1. Establish the authenticated webmail page for this named session.
  let main = homePage();
  if (!main) {
    try {
      await page.goto("https://mail.163.com/js6/main.jsp",
        { waitUntil: "domcontentloaded", timeout: 30000 });
    } catch (error) {
      return reply("unknown", `Could not reach 163.com webmail: ${error.message}`);
    }
    main = page;
  }
  let bodyText = "";
  try {
    bodyText = await main.locator("body").innerText({ timeout: 10000 });
  } catch (error) {
    bodyText = "";
  }
  const account = accountIn(bodyText);
  if (!main.url().includes("/js6/main.jsp") || !account) {
    return reply("authentication_required",
      "Complete 163.com login, verification, or CAPTCHA in the headed browser, then run execution again");
  }
  const intendedSender = String(request.sender || "").toLowerCase();
  if (account !== intendedSender) {
    return reply("failed",
      `Browser is logged into ${account}; the confirmed sender is ${intendedSender}`);
  }

  const clickFirst = async candidates => {
    for (const locator of candidates) {
      try {
        if (await locator.count()) {
          await locator.first().click({ timeout: 8000 });
          return true;
        }
      } catch (error) {
        // Fall through to the next candidate selector.
      }
    }
    return false;
  };

  // 2. Open the compose interface; 163 may open it as a new tab or in-page overlay.
  // 163 renders the compose label with letter-spacing, so the accessible text
  // is "写 信"; match on whitespace-normalized text and fall back to the
  // component markup rather than an exact string.
  const popup = context.waitForEvent("page", { timeout: 5000 }).catch(() => null);
  const opened = await clickFirst([
    main.getByText(/写\s*信/),
    main.locator("li.js-component-component").filter({ hasText: /写\s*信/ }),
    main.locator("span.oz0"),
    main.locator('[href*="compose"]')
  ]);
  if (!opened) {
    return reply("failed", "Could not open the 163.com compose interface");
  }
  const popped = await popup;
  const compose = popped || main;
  await compose.waitForLoadState("domcontentloaded", { timeout: 20000 }).catch(() => {});
  await compose.waitForTimeout(1500);

  // 3. Fill the confirmed recipient, subject and body exactly as authorized.
  const fillFirst = async (candidates, value) => {
    for (const locator of candidates) {
      try {
        if (await locator.count()) {
          await locator.first().fill(value, { timeout: 8000 });
          return true;
        }
      } catch (error) {
        // Fall through to the next candidate selector.
      }
    }
    return false;
  };

  const recipientFilled = await fillFirst([
    compose.locator(".nui-editableAddr-ipt"),
    compose.locator('input[name="to"]'),
    compose.locator("#to"),
    compose.locator('input[placeholder*="收件人"]'),
    compose.locator('input[title*="收件人"]'),
    compose.locator('textarea[name="to"]')
  ], request.recipient);
  if (!recipientFilled) {
    return reply("failed", "Could not locate the compose recipient field");
  }
  try {
    await compose.keyboard.press("Enter");
    await compose.waitForTimeout(400);
  } catch (error) {
    // The recipient may already be committed as a chip.
  }

  const subjectFilled = await fillFirst([
    compose.locator('input[id$="_subjectInput"]'),
    compose.locator('input[name="subject"]'),
    compose.locator("#subject"),
    compose.locator('input[placeholder*="主题"]'),
    compose.locator('input[title*="主题"]')
  ], request.subject);
  if (!subjectFilled) {
    return reply("failed", "Could not locate the compose subject field");
  }

  // 163 renders the body in a rich-text editor whose contenteditable lives in
  // an unnamed iframe.  That frame initialises later than the recipient and
  // subject fields, so poll for it instead of sampling the frame list once.
  let bodyFilled = false;
  const bodyDeadline = Date.now() + 25000;
  while (!bodyFilled && Date.now() < bodyDeadline) {
    for (const frame of compose.frames()) {
      try {
        const editable = frame.locator(
          'body[contenteditable="true"], div[contenteditable="true"]').first();
        if (await editable.count()) {
          await editable.click({ timeout: 3000 });
          await editable.fill(request.body, { timeout: 8000 });
          bodyFilled = true;
          break;
        }
      } catch (error) {
        // Try the next frame.
      }
    }
    if (!bodyFilled) {
      await compose.waitForTimeout(1000);
    }
  }
  if (!bodyFilled) {
    bodyFilled = await fillFirst([
      compose.locator('div[contenteditable="true"]'),
      compose.locator('body[contenteditable="true"]'),
      compose.locator('textarea[name="content"]')
    ], request.body);
  }
  if (!bodyFilled) {
    // Last resort: the plain-text editor keeps the model in a hidden textarea.
    try {
      const plain = compose.locator("textarea.APP-editor-textarea").first();
      if (await plain.count()) {
        await plain.evaluate((node, value) => {
          node.value = value;
          node.dispatchEvent(new Event("input", { bubbles: true }));
          node.dispatchEvent(new Event("change", { bubbles: true }));
        }, request.body);
        bodyFilled = true;
      }
    } catch (error) {
      bodyFilled = false;
    }
  }
  if (!bodyFilled) {
    return reply("failed", "Could not locate the compose message body");
  }

  // 4. Attach the exact confirmed bytes, waiting for each upload to register.
  if (attachmentFiles.length) {
    const fileInput = compose.locator('input[type="file"]').first();
    if (!(await fileInput.count())) {
      return reply("failed", "Could not locate the compose attachment input");
    }
    try {
      await fileInput.setInputFiles(attachmentFiles, { timeout: 60000 });
    } catch (error) {
      return reply("failed", `Attaching the confirmed files failed: ${error.message}`);
    }
    for (const path of attachmentFiles) {
      const name = String(path).split(/[\\/]/).pop();
      try {
        await compose.getByText(name, { exact: false }).first().waitFor({ timeout: 60000 });
      } catch (error) {
        return reply("failed", `Attachment ${name} did not finish uploading`);
      }
    }
    await compose.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
  }

  // 5. Prove the header carries the confirmed recipient and subject before the
  //    single submission.  A mismatch refuses to send rather than risk an
  //    unintended delivery.
  const header = await compose.evaluate(() => {
    const subjectInput = document.querySelector('input[id$="_subjectInput"]');
    const chips = Array.from(
      document.querySelectorAll('[class*="nui-addr-email"], [class*="editableAddr"]'))
      .map(element => element.textContent || "").join(" ");
    return {
      subject: subjectInput ? subjectInput.value : "",
      recipients: chips,
      text: document.body ? (document.body.innerText || "") : ""
    };
  }).catch(() => ({ subject: "", recipients: "", text: "" }));
  const condensed = String(
    header.subject + " " + header.recipients + " " + header.text)
    .replace(/\s+/g, "").toLowerCase();
  const wantedRecipient = String(request.recipient || "").replace(/\s+/g, "").toLowerCase();
  const wantedSubject = String(request.subject || "").replace(/\s+/g, "").toLowerCase();
  if (wantedRecipient && !condensed.includes(wantedRecipient)) {
    return reply("failed",
      "The confirmed recipient is absent from the compose header; refusing to submit");
  }
  if (wantedSubject && !condensed.includes(wantedSubject)) {
    return reply("failed",
      "The confirmed subject is absent from the compose header; refusing to submit");
  }

  // 6. Submit once. 163 interposes a promotional "AI 优化" modal on the first
  //    submit that silently blocks the send until it is dismissed, so dismiss
  //    that prompt and submit again.  A visible validation error is recorded
  //    rather than retried.
  const submit = () => clickFirst([
    compose.locator('div.js-component-button:has-text("发送")'),
    compose.locator('span.nui-btn-text:has-text("发送")'),
    compose.getByRole("button", { name: /^发送/ }),
    compose.locator('a:has-text("发送")'),
    compose.getByText("发送", { exact: true })
  ]);
  const dismissPromotionalModal = async () => {
    const text = await compose.evaluate(() => {
      const visible = Array.from(
        document.querySelectorAll('[class*="newdialog"], [class*="nui-msgbox"]'))
        .filter(candidate => candidate.offsetParent);
      return visible.length ? (visible[0].textContent || "").replace(/\s+/g, "") : "";
    }).catch(() => "");
    if (!/智能优化|智能润色|润色重写|纠错英文邮件/.test(text)) return false;
    await compose.locator(".nui-msgbox-close, .nui-close").first()
      .click({ timeout: 4000, force: true }).catch(() => {});
    await compose.waitForTimeout(1200);
    return true;
  };

  const submitted = await submit();
  if (!submitted) {
    return reply("failed", "Could not locate the compose send button");
  }
  await compose.waitForTimeout(2500);
  for (let attempt = 0; attempt < 3; attempt++) {
    if (!(await dismissPromotionalModal())) break;
    await submit();
    await compose.waitForTimeout(2500);
  }

  let validation = "";
  try {
    const toast = await compose.locator(
      '.nui-msg-error, .nui-msg-warning, [class*="error"]').first().innerText({ timeout: 1500 });
    validation = String(toast || "").trim();
  } catch (error) {
    validation = "";
  }
  if (validation) {
    return reply("failed", `163.com refused the submission: ${validation}`);
  }

  // 7. Establish Sent from mailbox evidence, never from the click alone.
  const recipientLower = String(request.recipient || "").toLowerCase();
  const subject = String(request.subject || "").trim();
  const confirmed = await main.evaluate(async ({ recipient, subject, sinceMillis }) => {
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
          value[child.getAttribute("name") || child.tagName] = valueOf(child);
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
    const listPayload = start => `<?xml version="1.0"?><object><int name="fid">3</int><string name="order">date</string><boolean name="desc">true</boolean><int name="limit">${pageSize}</int><int name="start">${start}</int><boolean name="skipLockedFolders">false</boolean><boolean name="returnTag">true</boolean><boolean name="returnTotal">true</boolean></object>`;
    const readPayload = id => `<?xml version="1.0"?><object><string name="id">${id}</string><boolean name="header">true</boolean><boolean name="returnImageInfo">true</boolean><boolean name="autoName">true</boolean></object>`;
    const codeOf = document => document.querySelector("code")?.textContent || "";
    // 163 returns sentDate as server-local text (UTC+8); convert to epoch ms so
    // the observation window actually excludes earlier identical subjects.
    const parseSent = value => {
      const match = String(value || "").match(
        /(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/);
      if (!match) return NaN;
      return Date.UTC(+match[1], +match[2] - 1, +match[3],
        +match[4], +match[5], +match[6]) - 8 * 3600 * 1000;
    };
    const deadline = Date.now() + 45000;
    while (Date.now() < deadline) {
      const response = await post("mbox:listMessages", listPayload(0));
      const document = await xmlDocument(response);
      if (response.ok && codeOf(document) === "S_OK") {
        const container = document.querySelector('array[name="var"]');
        const rows = Array.from(container?.children || [])
          .filter(node => node.tagName === "object").map(valueOf);
        for (const row of rows) {
          const to = String(row.to || "").toLowerCase();
          if (recipient && !to.includes(recipient)) continue;
          const sentAt = parseSent(row.sentDate);
          if (Number.isFinite(sentAt) && sentAt < sinceMillis - 180000) continue;
          const detailResponse = await post("mbox:readMessage", readPayload(row.id));
          const detailDocument = await xmlDocument(detailResponse);
          const detail = valueOf(detailDocument.querySelector('object[name="var"]')) || {};
          const detailSubject = String(detail.subject || row.subject || "").trim();
          if (!subject || detailSubject === subject) {
            return {
              matched: true,
              reference: row.id,
              evidence: {
                source: "163.com mbox:listMessages plus metadata-only mbox:readMessage",
                folder: "sent",
                to: row.to,
                subject: detailSubject,
                sent_date: row.sentDate,
                send_status: row.sndStatus
              }
            };
          }
        }
      }
      await new Promise(resolve => setTimeout(resolve, 3000));
    }
    return { matched: false };
  }, { recipient: recipientLower, subject, sinceMillis: startedAt });

  // 8. Return the session to the mailbox so later read-only observations see the
  //    folder tree rather than the compose module.
  try {
    await main.goto("https://mail.163.com/js6/main.jsp",
      { waitUntil: "domcontentloaded", timeout: 20000 });
    await main.waitForTimeout(1500);
  } catch (error) {
    // Leave the session as it is; the next observation reports its own state.
  }

  if (confirmed.matched) {
    return reply("sent",
      "Mailbox evidence confirms the message in the Sent folder",
      {
        reference: confirmed.reference,
        mailbox_address: account,
        evidence: confirmed.evidence,
        dialogs: dialogLog
      });
  }
  return reply("unknown",
    "Compose was submitted but the Sent folder did not confirm the message within the observation window",
    { mailbox_address: account, dialogs: dialogLog });
}
