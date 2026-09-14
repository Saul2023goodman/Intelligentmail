# SmartMail — project conventions

Ticket-driven repo. Issues live at `.scratch/smartmail-phase-one/issues/NN-<slug>.md` with a
`Status:` line near the top and history appended under `## Comments`. Completed tickets read
`Status: resolved` / `Labels: implemented` with acceptance boxes `[x]`.

## Docs per ticket
Each ticket ships two docs and a README update: `docs/<name>-pattern-NN.md` (design/usage) and
`docs/ticket-NN-validation.md` (measured outcomes). README's intro says "Tickets 01 to NN", adds a
section for the new capability, links the new pattern in "Local state", and links the new
validation in "Verify".

## Code map
- `smartmail/__init__.py` — core command/query boundary (`SmartMail`); all logic lives here.
- `smartmail/mailbox.py` — adapter boundary; `Disabled` (default), `Controlled` (fixtures),
  `NetEase163Mailbox` (live 163.com).
- `smartmail/netease_163_collector.js` — read-only observation payload injected into `run-code`.
- `smartmail/netease_163_sender.js` — confirmed immediate-send payload.
- `smartmail/__main__.py` — argparse terminal shell; adapters chosen via `--adapter`.
- `smartmail/schema.sql` — schema; new columns are added via the idempotent `_migrate` tuples.

## Tests
`\.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests` (157 tests, 5 opt-in skips).
`.venv` has openpyxl. Adapter tests use a fake Playwright runner (`tests/test_live_send.py`) — keep
tests independent of live accounts; verify the real browser separately in live acceptance. Throwaway
pilots belong in `.smartmail/` (gitignored), e.g. `.smartmail/ticket09-pilot.py`.

## Live 163.com acceptance (hard-won)
- **Use a persistent profile.** Playwright's default context is incognito-like: cookies live only in
  memory, so the login is lost the moment the browser/daemon exits and the profile's Cookies DB stays
  empty. `NetEase163Mailbox._open_browser` passes `--persistent --profile .smartmail/browser-163`
  (override with `SMARTMAIL_BROWSER_PROFILE`). Named session: `smartmail-163`.
- **Git Bash path gotcha.** Passing `/c/Users/...` to native Node creates a literal `C:\c\Users\...`.
  Use drive-letter paths (`C:/Users/...`) for native exes. Python `Path.cwd()` is fine.
- **163 compose selectors.** Trigger `getByText(/写\s*信/)` (label renders letter-spaced as "写 信");
  recipient `.nui-editableAddr-ipt` (press Enter to commit the chip); subject `input[id$="_subjectInput"]`;
  body = contenteditable `BODY` inside a same-origin iframe; files `input[type=file]`; send
  `div.js-component-button:has-text("发送")`.
- **The send is blocked by a promo modal.** Clicking 发送 raises "智能优化您的英文邮件" which silently
  blocks submission; dismiss it (`.nui-msgbox-close`) then submit again. Without this the attempt
  correctly returns `unknown` (nothing sent).
- **Evidence, not the click, decides Sent.** Confirm via `mbox:listMessages` (fid 3) + metadata-only
  `mbox:readMessage`. `sentDate` is server-local text (UTC+8) — parse it to epoch ms, because
  `Number("2026-09-11 18:31:12")` is `NaN` and silently disables the time window.
- Prefer unique subjects per acceptance run so a prior send cannot false-match.
