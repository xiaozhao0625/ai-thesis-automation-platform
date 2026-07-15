# ProjectFact P0 r4 Test Results

Run date: 2026-07-15  
Candidate: `v0.3.2-P0-r4` / `v1.2.4-P0-r4`

| Check | Result |
| --- | --- |
| Python standard-library unit tests | 41/41 passed |
| Generated review-payload schema instances | passed |
| UI static contract | passed |
| Playwright/Chromium browser regression | 13/13 passed |

The Python tests cover DOCX, source-code, spreadsheet, and image/OCR extraction;
structured locators; input changes; conflict closure; selective invalidation;
snapshot and fingerprint changes; cross-series model substitutions; FactAlias
registry binding; approval actor propagation; and full generated-payload schema
validation.

This result supports submission of the r4 candidate for independent review only.
It does not represent a formal freeze, release, or push.
