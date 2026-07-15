# ProjectFact P0 r4 Review Candidate

Candidate identifiers: `v0.3.2-P0-r4` / `v1.2.4-P0-r4`  
Status: pending independent review. This candidate is not frozen, released, or pushed.

This is a strictly scoped correction after the r3 review. It does not add pages,
expand product scope, or start the six implementation-level technical documents.

## Scope

- Make ProjectFact conflict state internally consistent: a conflicted fact has no
  current version, keeps its last locked version only for history, and suspends
  the current ProjectFactSnapshot.
- Detect unapproved model replacement by hardware slot, including cross-series
  and cross-vendor replacements.
- Bind `CONFIRMED_ALIAS` retrieval classifications to an approved FactAlias
  record instead of trusting caller-supplied fields.
- Propagate the approval actor to HumanApproval, AuditEvent, ProjectFactVersion,
  and ProjectFactSnapshot.
- Validate every generated review-payload instance against the bundled schemas.

## Contents

- `fixtures/`: frozen DOCX, Python, XLSX, PNG/OCR, conflict source, and expected
  fixture output.
- `project_fact_r4/extractor.py`: four real input extractors and structured
  source locators.
- `project_fact_r4/governance.py`: confirmation, model protection, retrieval
  validation, conflict lifecycle, dependency propagation, snapshot, and
  execution-fingerprint logic.
- `project_fact_r4/schema_validation.py`: schema-driven validation for the
  Draft 2020-12 features used by the bundled closed schemas.
- `schemas/`: ProjectFact, version, snapshot, conflict, locator, source link,
  dependency, alias, and retrieval-classification schemas.
- `tests/`: extraction, negative model, alias, conflict, propagation, version,
  actor, and payload-schema tests.
- `../uiux-prototype/project-fact-r4.json`: payload generated for the prototype
  API.

## Rebuild And Verify

From this source directory:

```powershell
python -m project_fact_r4.cli build-review-payload --fixtures fixtures --output ..\uiux-prototype\project-fact-r4.json
python -m unittest discover -s tests -v
```

The self-contained review package uses the adjacent `../prototype/` directory:

```powershell
python -m project_fact_r4.cli build-review-payload --fixtures fixtures --output ..\prototype\project-fact-r4.json
python -m unittest discover -s tests -v
```

Then run the prototype checks from `../uiux-prototype` in the source workspace,
or `../prototype` in the review package:

```powershell
node prototype.contract.test.mjs
$env:NODE_PATH=Join-Path (Join-Path $env:TEMP 'codex-playwright-check') 'node_modules'
node --test prototype.interaction.test.cjs
```

## Candidate Constraint

`68c5c50`, `91e1b51`, and `e9c06c4` remain failed review candidates retained for
traceability. This r4 candidate can become formal `v0.3.2 / v1.2.4` only after a
separate ProjectFact review approves it.
