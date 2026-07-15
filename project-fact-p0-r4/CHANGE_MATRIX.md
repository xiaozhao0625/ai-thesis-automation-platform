# ProjectFact r3 To r4 Change Matrix

| Review finding | r3 behavior | r4 correction | Verification |
| --- | --- | --- | --- |
| Conflict state consistency | `CONFLICT` fact kept a current version and an active current snapshot | Current version is null, last locked version is historical, current snapshot is `SUSPENDED` | Conflict-state and full-payload schema tests |
| Model replacement protection | Detected only same-prefix replacements | Detects candidate models by MCU, sensor, wireless, and display slots | DHT11/SHT31, ESP8266/NRF24L01, SSD1306/SH1106, STM32/ATmega negative tests |
| Confirmed alias | Caller could claim `CONFIRMED_ALIAS` without persisted proof | Requires an approved FactAlias with matching fact, version, value, and scope | Missing, foreign-fact, and scope-mismatch alias tests |
| Approval actor | Version and snapshot used a fixed operator | Confirming actor is propagated throughout the audit chain | Approval, audit, version, and snapshot actor equality test |
| Schema verification | Schema files were checked, not all generated objects | Complete generated review payload is instance-validated | Full payload validation test |
| Package hygiene | Older package retained cache artifacts and BOM manifest risk | r4 package excludes `__pycache__` and `.pyc`; manifests are UTF-8 without BOM | Packaging manifest verification |
