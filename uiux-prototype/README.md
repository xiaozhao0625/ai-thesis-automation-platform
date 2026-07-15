# UI/UX v1.2.4-P0-r6 Review Candidate

This prototype consumes the executable ProjectFact r6 candidate. It is pending
independent review and is neither frozen nor published. r6 changes no product
pages; the existing conflict confirmation interaction remains the only mutable
ProjectFact flow.

The API payload now contains dynamic structured fact bindings, a fifth RTC model
slot, unified output `content`, and service-derived Retrieval classifications.
Conflict confirmation still submits the selected candidate, source links, reason,
approver, and impact Snapshot hash to the executable candidate.

Run locally:

```powershell
node prototype.server.cjs
```

Open `http://127.0.0.1:4173/tasks/task-001/new-task`. The server provides SPA
fallback and uses `project-fact-r6.json`; conflict confirmation invokes the
adjacent `project-fact-p0-r6` executable directory or `../executable` inside the
self-contained review package.

```powershell
Push-Location ..\project-fact-p0-r6
python -B -m unittest discover -s tests -v
Pop-Location
node prototype.contract.test.mjs
$env:NODE_PATH=Join-Path (Join-Path $env:TEMP 'codex-playwright-check') 'node_modules'
node --test prototype.interaction.test.cjs
```
