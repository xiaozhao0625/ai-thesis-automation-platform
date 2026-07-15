# UI/UX v1.2.4-P0-r5 Review Candidate

This prototype consumes the executable ProjectFact r5 candidate. It is pending
independent review and is neither frozen nor published. r5 changes an existing
conflict confirmation modal; it does not add product pages.

The modal now submits the selected fact candidate, checked source links, reason,
approver, and impact snapshot hash to the executable candidate API. The returned
new FactVersion, Snapshot, HumanApproval, AuditEvent, and workflow state are
rendered from that response.

Run locally:

```powershell
node prototype.server.cjs
```

Open `http://127.0.0.1:4173/tasks/task-001/new-task`. The server provides SPA
fallback and uses `project-fact-r5.json`; conflict confirmation invokes the
adjacent `project-fact-p0-r5` executable directory (or `../executable` in the
self-contained review package).

```powershell
Push-Location ..\project-fact-p0-r5
python -B -m unittest discover -s tests -v
Pop-Location
node prototype.contract.test.mjs
$env:NODE_PATH=Join-Path (Join-Path $env:TEMP 'codex-playwright-check') 'node_modules'
node --test prototype.interaction.test.cjs
```
