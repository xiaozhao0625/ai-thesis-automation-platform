# ProjectFact P0 r5 Review Candidate

Candidate identifiers: `v0.3.2-P0-r5` / `v1.2.4-P0-r5`
Status: pending independent review. This candidate is not frozen, released, or pushed.

This is the restricted r5 repair after the r4 review. It does not add product
pages, expand the feature scope, or start the six implementation-level documents.

## Scope

- Compute the retrieval `match_type` on the service side and reject a caller
  declaration that differs from the actual locked-model relationship.
- Make structured `fact_bindings` the primary output contract for outline,
  content, BOM, parameter table, figure, and test outputs. Free-text scanning is
  an auxiliary alarm only.
- Require a confirmed alias to validate against FactAlias Schema and reference a
  LOCKED FactVersion that is the current version in the ACTIVE Snapshot.
- Accept a real conflict-confirmation request with candidate, source links,
  reason, approver, and impact hash; create Version, Snapshot, HumanApproval,
  AuditEvent, and dependency results from that request.

## Contents

- `fixtures/`: frozen DOCX, Python, XLSX, PNG/OCR, conflict source, and expected
  fixture data.
- `project_fact_r5/`: extraction, governance, schema validation, and CLI.
- `schemas/`: ProjectFact, Alias, bound-output, approval, audit, conflict, and
  dependency contracts.
- `tests/`: positive, negative, dependency, alias-currentness, binding, and
  request-driven confirmation regressions.
- `../uiux-prototype/project-fact-r5.json`: generated review payload for the
  prototype API.

## Rebuild And Verify

```powershell
python -B -m project_fact_r5.cli build-review-payload --fixtures fixtures --output ..\uiux-prototype\project-fact-r5.json
python -B -m unittest discover -s tests -v
```

Inside the self-contained review package, write the payload to the adjacent
`../prototype/project-fact-r5.json` instead. The conflict CLI receives a request
body on standard input:

```powershell
'{"conflict_id":"pfc-mcu-model", "selected_canonical_value":"STM32F103C8T6", "selected_source_link_ids":["fsl-012e03b3682cea32"], "decision":"APPROVED", "reason":"以任务书为准", "approved_by":"reviewer-zhang", "impact_snapshot_hash":"sha256:..."}' | python -B -m project_fact_r5.cli resolve-conflict --fixtures fixtures
```

`68c5c50`, `91e1b51`, `e9c06c4`, and `608f1c6` remain failed review candidates
for traceability. This r5 candidate requires a separate approval before any
formal `v0.3.2 / v1.2.4` freeze is considered.
