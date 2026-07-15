# ProjectFact P0 r6 Minimal Correction

## P0-1 Snapshot-Owned Retrieval Context

The closed Retrieval Request Schema excludes `locked_model`, `fact_version_id`,
`match_type`, support flags, and alias scope. Runtime resolves the fact, current
LOCKED FactVersion, and canonical value through the ACTIVE Snapshot and rejects
missing, stale, suspended, or conflicting state.

## P0-2 Slot-Semantic Extraction

Model extraction begins with labels such as controller, sensor, communication,
display, RTC, motor driver, and RFID slots. Captured values are not limited to a
brand list. Source-code extraction also accepts structured constants and device
mapping dictionaries. Unknown but classifiable slots remain ProjectFact
candidates instead of disappearing.

## P0-3 Dynamic Fact Bindings

`fact_bindings` accepts dynamic keys. Every value contains `fact_id`,
`fact_version_id`, and `canonical_value`. Required model slots are calculated
from the ACTIVE Snapshot; r6 includes `rtc_model` as a fifth fixture slot.

## P0-4 Unified Output Content

Schema and runtime both use `content`. Each output also carries its surface type,
NodeDefinition identifier, server-resolved context role, and structured bindings.

## P0-5 Fail-Closed Generation

Content validation returns `FACT_SNAPSHOT_NOT_ACTIVE / BLOCKING` for any
non-ACTIVE Snapshot. Current facts and FactVersions must remain LOCKED and match
the exact Snapshot references.

## P0-6 Server-Resolved Context

Comparison and background exemptions come from the server-side NodeDefinition
registry. A project body that submits `COMPARISON_ONLY` cannot gain an exemption.

## P0-7 Slot-Aware Text Checks

Labelled model substitutions are blocking. Other model-like identifiers are only
`REVIEW_REQUIRED`. `Python3`, `UART2`, `ISO9001`, `HTTP200`, and `WiFi6` are
recognized as normal technical identifiers and do not create blocking issues.
