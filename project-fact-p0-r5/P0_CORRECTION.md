# ProjectFact P0 r5 Minimal Correction

## P0-1 Server-Computed Model Relationship

`validate_retrieval_classification()` now computes the actual relationship from
`locked_model`, `matched_model`, and a verified alias. The submitted
`match_type` must equal that computed result. A caller cannot label `ESP32` as
`EXACT_MODEL` or `ATmega328P` as `SERIES_MATCH` to gain project-fact evidence.

## P0-2 Structured Fact Bindings

Project-specific outputs carry a `fact_bindings` object for all current hardware
and module fact slots. Runtime validation compares each output value with the
current ProjectFactSnapshot. Different values, missing bindings, and unbound
model-like free-text tokens in a project implementation output are blocking.

The primary enforcement is structured, so model protection is not dependent on a
fixed brand-prefix regular-expression list. Background and explicit comparison
outputs remain outside the project implementation binding requirement.

## P0-3 Current Alias Validation

Before a `CONFIRMED_ALIAS` classification is accepted, the service validates the
FactAlias instance against its schema and verifies its approved status, fact,
version, alias value, scope, current LOCKED ProjectFactVersion, current LOCKED
ProjectFact, and current ACTIVE ProjectFactSnapshot reference.

## P0-4 Request-Driven Conflict Confirmation

The resolver accepts and validates `conflict_id`, selected candidate value,
selected supporting SourceLinks, `decision`, `reason`, `approved_by`, and
`impact_snapshot_hash`. It rejects stale, unauthorized, mismatched, duplicate,
or unsupported input. A successful decision creates the new FactVersion and
Snapshot plus a separate HumanApproval and AuditEvent.

The prototype server sends the modal request body to the executable r5 CLI; it no
longer returns the pre-generated confirmation object for this endpoint.
