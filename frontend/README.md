# SmartMail workflow frontend

Install the repository's Python requirements and frontend dependencies, then:

```powershell
cd frontend
npm install
$env:SMARTMAIL_PYTHON = (Resolve-Path ../.venv/Scripts/python.exe).Path
npm run dev
```

Mailbox writes remain off by default. For an operator-approved live extension
acceptance session, opt into only the required capabilities before starting Vite:

```powershell
$env:SMARTMAIL_ENABLE_EXTENSION_SEND = '1'
$env:SMARTMAIL_ENABLE_EXTENSION_SCHEDULE = '1' # only when required
npm run dev
```

These flags expose the same guarded capabilities as the CLI. The selected extension
tab must still be connected, every action still requires exact operator Confirmation,
and Core rechecks authority before execution.

Open the loopback URL printed by Vite. The Core bridge defaults to the repository's
`.smartmail` store. Set `SMARTMAIL_HOME` to another store directory before starting
Vite if needed. `SMARTMAIL_PYTHON` is optional when `python` already has the
repository requirements installed.

The pages support campaign and Student scoping, browser source-set import, supported
document preparation, readiness review, task search, message and source inspection,
read-only mailbox intake, persisted evidence, duplicate checks, subject/recipient
correction, attachment confirmation, source-based Rewrite, zoom and fit. Connect
the dedicated extension in the explicitly selected Student mailbox to enable
reading. External capabilities remain independently guarded by Core and the
configured mailbox adapter. Existing imported records appear immediately; a fresh
store shows an empty workflow.

```powershell
npm run build
npm run lint
npm test
```

The build is a static UI bundle; the stdio Core bridge runs with `npm run dev`,
not standalone static hosting or `vite preview`. See
[workflow mapping and boundaries](../docs/frontend-workflow.md).

Every main page must fit the available viewport responsively, without page-level
scrolling. Density, spacing and internal regions adapt to both window width and
height. Lists, diagrams, inspectors and dialogs own their bounded scrolling;
controls and content must remain reachable in narrow or short windows.

Restart Vite after editing Python Core code so its long-lived stdio worker reloads.

## Page ownership and shared foundation

Workspace code lives in `src/pages/workspace/`; Intake (Source mapping) lives in
`src/pages/intake/`. Shared shell, navigation and hash routing live in `src/app/`,
tokens/icons/primitives in `src/shared/`, and the typed Core bridge in `src/core/`.
Keep page development within its directory. See
[foundation interfaces and state lifetime](../docs/frontend-foundation.md) and
[frontend agent guidance](AGENTS.md) before starting page worktrees.

## Source mapping

Open `/#source-mapping`, or select **Source mapping** in the workflow toolbar or
sidebar. This page is backed by Core Campaigns, Students, imports, Source Materials,
Outreach Tasks and Preparations. **Add source set** accepts a supported `.xlsx`
master list or `.zip` bundle, retains the original bytes, creates or reuses Tasks,
and runs supported deterministic document association. Unsupported or replacement
documents stay visible as unresolved evidence. Filters and inspectors are
presentation-only; they never infer associations or authorize sending.

## Readiness review

Open `/#review`, or select **Readiness review** in the sidebar. The third page reads
current Preparations and retained evidence from Core. Recipient and subject
corrections revalidate the Preparation and invalidate stale Confirmation; attachment
confirmation snapshots selected bytes; duplicate checks retain their coverage; and
supported identity and prior-outreach Exceptions require explicit operator
resolution. **Mark reviewed** is session-local and deliberately does not create
sending Confirmation. No action on this page writes to a mailbox.

Desktop uses three independently bounded regions. At widths of 900px or less,
Preparations, Message, and Readiness tabs expose the same content and controls.
