/* One confirmed compose operation in the supported in-page 163 layout. */
(() => {
  const api = globalThis.SmartMail163;
  const states = new Map();
  const selectors = {
    recipient: '.nui-editableAddr-ipt, input[name="to"], #to, textarea[name="to"]',
    subject: 'input[id$="_subjectInput"], input[name="subject"], #subject',
    richBody: 'body[contenteditable="true"], div[contenteditable="true"]',
    plainBody: 'textarea[name="content"], textarea.APP-editor-textarea',
    plainTextCheckbox: "span.js-component-checkbox[role='checkbox']"
  };
  const one = (root, selector) => {
    const nodes = Array.from(root.querySelectorAll(selector)).filter(api.visible);
    if (nodes.length !== 1) throw new Error(`Expected one unambiguous compose field: ${selector}`);
    return nodes[0];
  };
  const setValue = (node, value) => {
    const window = node.ownerDocument.defaultView;
    if ("value" in node) {
      const prototype = node.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(prototype, "value").set.call(node, value);
    } else { node.textContent = value; }
    node.dispatchEvent(new window.Event("input", { bubbles: true }));
    node.dispatchEvent(new window.Event("change", { bubbles: true }));
  };
  const frameRoots = () => {
    const roots = [document];
    for (const frame of document.querySelectorAll("iframe")) {
      try { if (api.visible(frame) && frame.contentDocument) roots.push(frame.contentDocument); }
      catch { /* Cross-origin editor is unsupported. */ }
    }
    return roots;
  };
  const matching = selector =>
    frameRoots().flatMap(root => Array.from(root.querySelectorAll(selector)).filter(api.visible));
  const richEditor = () => {
    const nodes = matching(selectors.richBody);
    return nodes.length === 1 ? nodes[0] : null;
  };
  const plainEditor = () => {
    const nodes = matching(selectors.plainBody);
    return nodes.length === 1 ? nodes[0] : null;
  };
  // Fresh compose may open in the operator's saved plain-text mode. Switch it
  // back to the rich HTML editor; the editor is empty at fill time, so the
  // official "convert to plain text loses formatting" dialog never appears.
  const enableRichEditor = async deadline => {
    const checkbox = Array.from(document.querySelectorAll(selectors.plainTextCheckbox))
      .filter(api.visible)
      .find(node => /纯文本/.test(node.textContent || "")
        && node.getAttribute("aria-checked") === "true");
    if (checkbox) checkbox.click();
    while (Date.now() < deadline) {
      const editor = richEditor();
      if (editor) return editor;
      await api.delay(250);
    }
    return null;
  };
  // Resolve one body editor, preferring rich HTML so italics, font sizes and
  // paragraph structure survive. Returns the node and its format.
  const resolveBodyEditor = async deadline => {
    let rich = richEditor();
    if (!rich) {
      const checkbox = Array.from(document.querySelectorAll(selectors.plainTextCheckbox))
        .filter(api.visible)
        .find(node => /纯文本/.test(node.textContent || "")
          && node.getAttribute("aria-checked") === "true");
      // Only wait for a rich editor when a plain-text mode toggle can be
      // switched. Layouts without either control fall back to plain at once.
      if (checkbox) rich = await enableRichEditor(deadline);
    }
    if (rich) return { node: rich, format: "html" };
    const plain = plainEditor();
    if (plain) return { node: plain, format: "plain" };
    throw new Error("A single accessible message editor is required");
  };
  const setRichHtml = (node, html) => {
    const doc = node.ownerDocument;
    node.innerHTML = html;
    node.dispatchEvent(new doc.defaultView.Event("input", { bubbles: true }));
    node.dispatchEvent(new doc.defaultView.Event("change", { bubbles: true }));
    const keyboard = type => node.dispatchEvent(
      new doc.defaultView.KeyboardEvent(type, { bubbles: true, key: "a" }));
    keyboard("keyup");
    keyboard("keydown");
  };
  const textValue = node => ("value" in node ? node.value : node.innerText);
  // The exact plain text the confirmed body projects to in a rich editor.
  const expectedBodyText = request => {
    const html = request.body_html || "";
    if (html) return api.htmlToPlainText(html);
    return api.looksLikeHtml(request.body) ? api.htmlToPlainText(request.body) : request.body;
  };
  const normalize = text => String(text).replace(/\r\n/g, "\n");
  const verify = state => {
    const { request, recipient, subject, body, bodyFormat } = state;
    if (api.account() !== request.sender.toLowerCase()) throw new Error("Connected Mailbox changed");
    if (![recipient, subject, body].every(node => node.isConnected)) throw new Error("Compose document changed");
    const chips = Array.from(document.querySelectorAll('[class*="nui-addr-email"]')).map(node => node.textContent).join(" ");
    const addresses = api.addresses(recipient.value + " " + chips);
    const extras = Array.from(document.querySelectorAll('input[name="cc"], input[name="bcc"], textarea[name="cc"], textarea[name="bcc"]'));
    if (addresses.length !== 1 || addresses[0] !== request.recipient.toLowerCase() || extras.some(node => node.value.trim()))
      throw new Error("Compose recipients differ from Confirmation");
    const bodyMatches = bodyFormat === "html"
      ? api.sameText(textValue(body), expectedBodyText(request))
      : normalize(textValue(body)) === normalize(request.body);
    if (subject.value !== request.subject || !bodyMatches)
      throw new Error("Compose content differs from Confirmation");
    const uploads = Array.from(document.querySelectorAll('input[type="file"]')).flatMap(node => Array.from(node.files || []));
    if (uploads.length !== state.files.length || uploads.some((file, index) =>
      file.name !== state.files[index].name || file.size !== state.files[index].size))
      throw new Error("Compose attachment selection changed");
  };
  api.prepare = async (command, encodedFiles) => {
    api.assertDeadline(command.deadline);
    const request = command.payload;
    if (request.kind !== "immediate" || api.account() !== request.sender.toLowerCase())
      throw new Error("An authenticated matching Mailbox and immediate Confirmation are required");
    if (Array.from(document.querySelectorAll(selectors.subject)).some(api.visible))
      throw new Error("Close the existing compose draft before starting confirmed execution");
    const previous = (await api.listSent()).map(row => row.id);
    const controls = Array.from(document.querySelectorAll('button, [role="button"], li.js-component-component, a'));
    const compose = controls.filter(api.visible).find(node => /^写\s*信$/.test(node.textContent.trim()));
    if (!compose) throw new Error("Supported in-page compose control was not found");
    compose.click();
    let recipient, subject, body, bodyFormat;
    const until = Math.min(command.deadline, Date.now() + 20000);
    while (Date.now() < until) {
      try {
        recipient = one(document, selectors.recipient);
        subject = one(document, selectors.subject);
        ({ node: body, format: bodyFormat } = await resolveBodyEditor(until));
        break;
      } catch { await api.delay(250); }
    }
    if (!recipient || !subject || !body) throw new Error("Compose layout is unsupported; popup or cross-origin editors require operator handling");
    if (Array.from(document.querySelectorAll('input[type="file"]')).some(node => node.files?.length))
      throw new Error("New compose contains unexpected attachments");
    setValue(recipient, request.recipient);
    recipient.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", bubbles: true }));
    recipient.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", code: "Enter", bubbles: true }));
    setValue(subject, request.subject);
    // Write HTML into the rich editor so the message keeps its formatting
    // (paragraphs, italics, font sizes). The editor re-renders while compose
    // initializes and can escape a write that lands too early, so fill until
    // the text projection matches the confirmed content. Plain-text layouts
    // fall back to the exact confirmed text.
    if (bodyFormat === "html") {
      const html = api.composeBodyHtml({ html: request.body_html, text: request.body });
      const fillUntil = Math.min(command.deadline, Date.now() + 8000);
      let established = false;
      while (Date.now() < fillUntil) {
        if (!body.isConnected) body = richEditor();
        if (!body) body = await enableRichEditor(fillUntil);
        if (!body) break;
        setRichHtml(body, html);
        await api.delay(350);
        if (body.isConnected && api.sameText(textValue(body), expectedBodyText(request))) {
          established = true;
          break;
        }
        await api.delay(250);
      }
      if (!established) throw new Error("Compose content could not be established in the rich HTML editor");
    } else {
      setValue(body, request.body);
    }
    const files = [];
    for (let index = 0; index < encodedFiles.length; index++) {
      const descriptor = request.attachments[index];
      const bytes = Uint8Array.from(atob(encodedFiles[index]), char => char.charCodeAt(0));
      const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))).map(value => value.toString(16).padStart(2, "0")).join("");
      if (digest !== descriptor.sha256 || bytes.length !== descriptor.size) throw new Error("Confirmed attachment digest mismatch");
      files.push(new File([bytes], descriptor.name, { type: "application/octet-stream" }));
    }
    if (files.length) {
      const inputs = Array.from(document.querySelectorAll('input[type="file"]'));
      if (inputs.length !== 1 || (files.length > 1 && !inputs[0].multiple)) throw new Error("Unsupported attachment upload control");
      const transfer = new DataTransfer();
      files.forEach(file => transfer.items.add(file));
      inputs[0].files = transfer.files;
      inputs[0].dispatchEvent(new Event("change", { bubbles: true }));
      // A filename alone does not prove upload completion. Require completed attachment rows.
      const uploadUntil = Math.min(command.deadline, Date.now() + 45000);
      let complete = false;
      while (Date.now() < uploadUntil) {
        const rows = Array.from(document.querySelectorAll('.nui-attachment, [data-upload-state="complete"]'));
        const busy = Array.from(document.querySelectorAll('[role="progressbar"], .nui-progress, .uploading')).some(api.visible);
        complete = !busy && files.every(file => rows.some(row => api.visible(row) && row.textContent.includes(file.name)
          && (row.dataset.uploadState === "complete" || /上传完成|上传成功/.test(row.textContent))));
        if (complete) break;
        await api.delay(300);
      }
      if (!complete) throw new Error("Attachment upload completion could not be established");
    }
    const state = { request, recipient, subject, body, bodyFormat, files, previous, clicked: false };
    verify(state);
    api.assertDeadline(command.deadline);
    states.set(command.id, state);
    return { prepared: true };
  };
  api.send = async command => {
    const state = states.get(command.id);
    if (!state || state.clicked) throw new Error("No prepared command or command already submitted");
    const reply = (outcome, detail, extra = {}) => ({ outcome, detail, reference: "",
      mailbox_address: state.request.sender.toLowerCase(), observed_at: new Date().toISOString(), ...extra });
    try {
      api.assertDeadline(command.deadline);
      verify(state);
      const buttons = Array.from(document.querySelectorAll('button, [role="button"], div.js-component-button, a'));
      const send = buttons.filter(api.visible).filter(node => node.textContent.trim() === "发送");
      if (send.length !== 1) throw new Error("A single Send control is required");
      const startedAt = Date.now();
      state.clicked = true;
      send[0].click(); // Never repeat this click, dismiss dialogs, or accept promotional changes.
      while (Date.now() < Math.min(command.deadline, startedAt + 45000)) {
        const match = api.newSentMatch(await api.listSent(), state.previous, state.request, startedAt);
        if (match) return reply("sent", "New canonical Sent-folder evidence confirms submission", {
          reference: match.id, evidence: { folder: "sent", new_reference: true,
            recipient: state.request.recipient.toLowerCase(), subject: state.request.subject,
            send_status: match.sndStatus, sent_date: match.sentDate }
        });
        await api.delay(1500);
      }
      return reply("unknown", "No unambiguous new Sent record; handle any dialog and reconcile before continuing");
    } catch (error) {
      return reply(state.clicked ? "unknown" : "failed", String(error.message || error));
    } finally { states.delete(command.id); }
  };
})();
