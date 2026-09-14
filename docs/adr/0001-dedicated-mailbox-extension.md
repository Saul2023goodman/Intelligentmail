# Use a dedicated browser extension for 163 webmail

Status: accepted

The operator requested a pivot from external browser automation to a dedicated mailbox extension. Use a Manifest V3 Chrome/Edge extension in the operator's explicitly selected, authenticated 163 tab, connected to the local SmartMail store through Native Messaging. Python retains Preparation, Confirmation and the Execution Ledger; the extension owns webmail observation and confirmed page interaction.

Native Messaging avoids a local HTTP listener and ambient browser profile discovery, at the cost of explicit extension installation and per-browser native host registration. A durable, single-delivery queue connects short-lived CLI commands to the browser-owned host. Reconnection never replays a claimed operation, and the native host rechecks persisted Confirmation before issuing one submission permit.

The former Playwright CLI adapter and injected scripts are removed instead of maintained as a fallback. Existing data and historical acceptance evidence remain, but the extension does not inherit the former adapter's verification claims. Immediate sending is disabled by default and available only through explicit acceptance mode until live extension acceptance is recorded. Other external capabilities remain independently disabled.
