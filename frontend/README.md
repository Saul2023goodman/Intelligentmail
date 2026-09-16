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
message and source inspection, duplicate checks, zoom and fit. Existing imported
records appear immediately; a fresh store shows an empty workflow. Import through
the Core CLI using the same store, then refresh the page.

```powershell
npm run build
npm run lint
```

The build is a static UI bundle; the stdio Core bridge runs with `npm run dev`,
not standalone static hosting or `vite preview`. See
[workflow mapping and boundaries](../docs/frontend-workflow.md).

The UI targets desktop browsers only. Future changes do not need mobile
adaptation: mobile viewports, responsive layouts and touch interaction are
out of scope and require no testing or fixes.
