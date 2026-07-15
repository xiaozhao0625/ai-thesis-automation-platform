# ProjectFact P0 r4 Minimal Correction

## P0-1 Conflict State And Payload Validation

- A ProjectFact in `CONFLICT` now has `current_fact_version_id: null` and
  `conflict_status: OPEN`.
- `last_locked_fact_version_id` preserves the previous confirmed version solely
  for traceability.
- The conflict response exposes a `SUSPENDED` ProjectFactSnapshot; the prior
  `ACTIVE` snapshot is retained as historical data and is not the current
  execution context.
- The review-payload test validates every generated ProjectFact, version,
  locator/source link, conflict, snapshot, dependency, retrieval classification,
  and dependency-graph instance against the bundled schemas.

## P0-2 Model Protection By Fact Slot

The generated-surface validator extracts model candidates by hardware slot and
compares them with the locked models in the current snapshot. It covers MCU,
sensor, wireless module, and display driver values. An unapproved different
model in the same slot creates `FACT_CONSTRAINT_VIOLATION / BLOCKING`, including
cross-series examples such as `DHT11 -> SHT31` and `STM32F103C8T6 -> ATmega328P`.
Explicit background or comparison contexts remain permitted.

## P0-3 Confirmed Alias Registry Binding

`RetrievalClassification` now carries `fact_id`, `fact_version_id`, and
`alias_id`. Runtime validation resolves `CONFIRMED_ALIAS` against the supplied
approved FactAlias registry and requires all of the following to match:

- alias identifier exists;
- alias fact and fact-version identifiers match the classification;
- alias value matches `matched_model`;
- alias status is `APPROVED`;
- alias scope matches the requested scope; and
- the fact version canonical value matches `locked_model`.

Caller-supplied `match_type` and `alias_scope` alone cannot bypass the exact
model constraint.

## P0-4 Approval Actor Propagation

The confirmation actor is now passed into the FactVersion and Snapshot factories.
For one confirmation operation, `HumanApproval.approved_by`, `AuditEvent.actor_id`,
`ProjectFactVersion.confirmed_by`, and `ProjectFactSnapshot.created_by` must be
the same value.

## Review Package Reproduction

Tests prefer `../prototype/project-fact-r4.json` inside a self-contained review
package, then fall back to `../uiux-prototype/project-fact-r4.json` in the source
workspace. No symbolic links or manual test-path edits are needed.
