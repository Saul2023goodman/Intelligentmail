# SmartMail workflow frontend

Install the repository's Python requirements and frontend dependencies, then:

```powershell
cd frontend
npm install
$env:SMARTMAIL_PYTHON = (Resolve-Path ../.venv/Scripts/python.exe).Path
npm run dev
```

Open the loopback URL printed by Vite. The Core bridge defaults to the repository's
`.smartmail` store. Set `SMARTMAIL_HOME` to another store directory before starting
Vite if needed. `SMARTMAIL_PYTHON` is optional when `python` already has the
repository requirements installed.

The page supports campaign selection/creation, workflow exploration, task search,
message and source inspection, read-only mailbox intake, persisted evidence,
duplicate checks, subject/recipient correction, source-based Rewrite, zoom and fit.
Connect the dedicated extension in the explicitly selected Student mailbox to
enable reading. Sending remains disabled in the UI bridge. Existing imported
records appear immediately; a fresh store shows an empty workflow. Import through
the Core CLI using the same store, then refresh the page.

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

## Source-mapping prototype

Open `/#source-mapping`, or select **Source mapping** in the workflow toolbar or
sidebar. This second page uses labeled sample data to demonstrate spreadsheets,
documents, attachments, student mailbox identities, and imported mailbox records
being associated with structured outreach tasks. Select a source to trace its
tasks; inspect rules and tasks for field mappings and source evidence. Search,
source-type and task-status filters, collapsible groups, and diagram zoom work locally.

The sample contains nine ready preparations, two attachment blockers, and one
duplicate suspicion. **Validate mapping** displays the sample validation summary.
**Add sources** stages file metadata locally without reading or parsing file contents.
Sample changes reset on navigation or reload; this page does not persist to Core,
import mailbox history, or authorize sending. The existing workflow remains connected
to Core.

## Review prototype

Open `/#review`, or select **Readiness review** in the sidebar. The third page is
an isolated sample-data readiness workbench with a searchable preparation queue,
annotated full-message preview, source excerpts, recipient comparison, attachment
review, and duplicate evidence coverage. A sample recipient conflict blocks review
completion until explicitly corrected. Review markings and corrections live in
memory and reset when leaving the page. Readiness and local review markings do not
grant sending confirmation; this page performs no Core mutations or external actions.

Desktop uses three independently bounded regions. At widths of 900px or less,
Preparations, Message, and Readiness tabs expose the same content and controls.
