# ProjectFact P0 r5 Test Results

Run date: 2026-07-15
Candidate: `v0.3.2-P0-r5` / `v1.2.4-P0-r5`

| Check | Result |
| --- | --- |
| Python standard-library unit tests | 41/41 passed |
| Generated review-payload schema instances | passed |
| UI static contract | passed |
| Playwright/Chromium browser regression | 13/13 passed |

The Python suite covers four real input formats and locators; server-computed
match classification; `EXACT_MODEL` and `SERIES_MATCH` spoofing; structured
bindings; DHT11/HDC1080, ESP8266-01S/HC-05, SSD1306/LCD1602,
STM32F103C8T6/RP2040 and GD32 replacements; current Snapshot Alias validation;
and request-driven conflict resolution, approval, audit, invalidation, and
fingerprint behavior.

The bundled validator covers the Draft 2020-12 keywords used by these closed
schemas. Independent review should continue to validate the generated payload
with an official Draft 2020-12 implementation.

These results support submission for independent review only, not a freeze,
release, or push.
