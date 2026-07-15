# ProjectFact r4 To r5 Change Matrix

| Review finding | r4 behavior | r5 correction | Verification |
| --- | --- | --- | --- |
| Retrieval match type | Trusted caller `match_type` | Recomputes the model relationship and rejects a mismatch | ESP32-as-exact and ATmega-as-series negative tests |
| Model protection | Fixed known-brand text patterns | Project outputs must carry fact bindings compared to the current snapshot | HDC1080, HC-05, LCD1602, RP2040, GD32 binding tests |
| Alias currentness | Checked a version existed | Requires Schema-valid alias, current LOCKED ProjectFactVersion, current fact, and ACTIVE Snapshot ref | Superseded, missing-snapshot-ref, and malformed-alias tests |
| Conflict confirmation | Fixed selected value and static prototype response | Validates request body and creates dynamic version, snapshot, approval, and audit | Alternate candidate, source, reason, actor, stale hash, and authorization tests |
| Snapshot history | One ID appeared as active and suspended | Current conflict snapshot is suspended with an explicit status transition | Conflict transition test |
