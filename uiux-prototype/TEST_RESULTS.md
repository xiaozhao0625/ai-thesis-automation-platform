# UI/UX v1.2.4-P0-r5 Test Results

Run date: 2026-07-15

| Check | Result |
| --- | --- |
| UI static contract | passed |
| ProjectFact executable tests | 41/41 passed |
| Browser interaction regression | 13/13 passed |

The browser suite verifies that the existing conflict modal can select the
alternative `STM32F407VET6` candidate, send the selected source, reason, and
approver to the server, and render the returned fact version and snapshot.

These results support r5 independent review only. They do not indicate a formal
freeze, release, or push.
