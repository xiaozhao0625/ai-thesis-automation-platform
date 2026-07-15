# ProjectFact P0 r6 Test Results

Run date: 2026-07-15
Candidate: `v0.3.2-P0-r6` / `v1.2.4-P0-r6`

| Check | Result |
| --- | --- |
| Python standard-library unit tests | 54/54 passed |
| Generated review-payload bundled Schema validation | passed |
| UI static contract | passed |
| Playwright/Chromium browser regression | 13/13 passed |

The suite covers real DOCX, source, XLSX, and OCR extraction and locators;
Snapshot-owned Retrieval; caller-owned lock/version rejection; generic model
families; dynamic fifth-slot bindings; unified output content; non-ACTIVE
Snapshot blocking; server-resolved context; token false positives; aliases;
conflict resolution; dependency propagation; audit; and fingerprints.

The bundled validator covers the Draft 2020-12 keywords used by these closed
schemas. The current local Python runtime does not include the third-party
`jsonschema` package, so independent review should also run an official Draft
2020-12 implementation against the generated payload.

These results support submission for independent review only, not a freeze,
release, or push.
