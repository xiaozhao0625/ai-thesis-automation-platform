# ProjectFact r5 To r6 Change Matrix

| Review finding | r5 behavior | r6 correction | Verification |
| --- | --- | --- | --- |
| Retrieval lock source | Caller supplied lock and version strings | ACTIVE Snapshot resolves current fact, version, and value | Spoofed lock, stale version, and missing Snapshot tests |
| Model extraction | Fixed model patterns and symbols | Slot-label extraction plus structured source mappings | RP2040, HDC1080, HC-05, LCD1602, DS3231, GD32, NRF24L01, SH1106 tests |
| Fact Binding | Four fixed string properties | Dynamic structured dictionary derived from Snapshot | Fifth `rtc_model` Schema and runtime tests |
| Output text | Runtime `text` absent from Schema | Shared required `content` field | Payload Schema and static contract tests |
| Conflict state | SUSPENDED Snapshot could validate output | Non-ACTIVE Snapshot fails closed | `FACT_SNAPSHOT_NOT_ACTIVE` test |
| Context exemption | Caller controlled `context_role` | NodeDefinition registry resolves role | Spoofed comparison context test |
| Token false positives | All letter-number tokens blocked | Label conflicts block; unknowns review; common technical IDs ignored | Python3/UART2/ISO9001/HTTP200/WiFi6 test |
