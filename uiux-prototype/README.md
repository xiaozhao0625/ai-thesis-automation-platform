# UI/UX v1.2.4-P0-r4 Review Candidate

This prototype consumes the executable ProjectFact r4 candidate. It is a review
candidate only, not a frozen `v1.2.4` release. No pages were added for r4.

## r4 Scope

- The conflict state distinguishes historical locked data from a current fact:
  a conflicted fact has no current FactVersion and its current snapshot is
  `SUSPENDED`.
- The material and conflict states continue to show source locators, affected
  downstream objects, and the impact confirmation action.
- Existing task navigation, workflow semantics, query isolation, global routing,
  and history behavior remain unchanged.

Failed candidates `68c5c50`, `91e1b51`, and `e9c06c4` are retained for review
traceability and are neither frozen nor pushed.

## Local Preview

```powershell
node prototype.server.cjs
```

Open `http://127.0.0.1:4173/tasks/task-001/new-task`. The server provides SPA
fallback plus the confirmation, conflict, impact-analysis, and conflict-resolution
API responses backed by `project-fact-r4.json`.

## Verification

```powershell
Push-Location ..\project-fact-p0-r4
python -m unittest discover -s tests -v
Pop-Location

node prototype.contract.test.mjs

$env:NODE_PATH=Join-Path (Join-Path $env:TEMP 'codex-playwright-check') 'node_modules'
node --test prototype.interaction.test.cjs
```
