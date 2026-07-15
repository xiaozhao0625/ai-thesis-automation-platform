# ProjectFact P0 r6 Review Candidate

Candidate identifiers: `v0.3.2-P0-r6` / `v1.2.4-P0-r6`

Status: pending independent review. This candidate is not frozen, released, or pushed.

This is the restricted r6 repair after the r5 review. It adds no product pages
and does not start the six implementation-level documents.

## Scope

- Retrieval accepts only a fact identifier, matched model, evidence role, and
  optional alias identifier. The service derives the current locked value and
  FactVersion exclusively from the ACTIVE Snapshot.
- DOCX, source code, spreadsheets, and frozen OCR use slot-label semantics and
  preserve the extracted original value and jumpable source locator.
- Fact bindings are a dynamic dictionary of structured fact, version, and value
  references. The required slots come from the ACTIVE Snapshot.
- Bound outputs use one `content` field shared by Schema and runtime validation.
- SUSPENDED, INVALIDATED, or missing Snapshots fail closed.
- Content context is resolved from the server-side NodeDefinition registry.
- Labelled model conflicts are blocking; unclassified model-like tokens require
  review; common technical identifiers are not blocking.

## Contents

- `fixtures/`: frozen DOCX, generic-model DOCX, Python, XLSX, PNG/OCR, conflict
  source, dependency graph, and expected data.
- `project_fact_r6/`: extraction, governance, schema validation, and CLI.
- `schemas/`: closed Retrieval request/output contracts and dynamic binding,
  fact, version, snapshot, alias, conflict, dependency, approval, and audit schemas.
- `tests/`: positive, negative, dependency, snapshot trust-boundary, dynamic
  slot, context authorization, and false-positive regressions.

## Rebuild And Verify

```powershell
python -B -m project_fact_r6.cli build-review-payload --fixtures fixtures --output ..\uiux-prototype\project-fact-r6.json
python -B -m unittest discover -s tests -v
```

Inside the self-contained review package, write the payload to
`../prototype/project-fact-r6.json`.

`68c5c50`, `91e1b51`, `e9c06c4`, `608f1c6`, and `78e1648` remain failed review
candidates for traceability. r6 requires independent approval before any formal
`v0.3.2 / v1.2.4` freeze is considered.
