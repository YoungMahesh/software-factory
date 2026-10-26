# 04: Delivery Gate Visual Telemetry and Preview Badge in Web UI

**What to build:**
Visual verification surfacing and screenshot inspection in Factory Studio, enabling developers to visually confirm UI state before merging pull requests. Implements a backend REST endpoint to serve captured viewport screenshots and metadata, and updates the Delivery Gate Card in the web frontend to display a visual verification status badge, test summary, and an expandable screenshot modal.

**Blocked by:** 03: In-Sandbox Headless Visual QA and Console Crash Detection

**Status:** resolved

- [x] REST API endpoint serves the latest captured visual QA screenshot and metadata for a repository and branch.
- [x] Delivery Gate Card displays a Visual QA status badge alongside deterministic test pass/fail results.
- [x] Delivery Gate Card renders a screenshot thumbnail with an indicator showing desktop and mobile capture status.
- [x] Clicking the thumbnail opens an expandable high-resolution preview modal displaying the captured UI screenshot before merging.
- [x] If visual verification failed with console errors, the card renders warning telemetry details and disables merge controls until resolved.
- [x] Automated backend tests verify the screenshot endpoint and frontend component tests verify card badge rendering, empty states, and modal expansion.
