# Production File Decomposition

## Overview

Following [ADR-0051](file:///root/software-factory/docs/adr/0051-production-file-line-budget-and-ratchet.md), all production source files in `software-factory` are subject to a **500 physical line budget** (`wc -l`).

This feature initiative covers the systematic decomposition of all **15 legacy production files** currently exceeding 500 lines into cohesive directory packages and modular components adhering to deep module principles ([`.agents/skills/codebase-design/SKILL.md`](file:///root/software-factory/.agents/skills/codebase-design/SKILL.md)).

## Architectural Rules

1. **Drop-in Package Migration**:
   - Python files `factory/ui/<name>.py` convert to package directories `factory/ui/<name>/__init__.py`.
   - TypeScript modules convert to directory packages with `index.ts`.
   - All existing public functions, classes, and constants must be re-exported from `__init__.py` / `index.ts` to ensure 100% backward compatibility for all existing call sites.
2. **Strict Line Budget**:
   - Every newly created private internal file (`_client.py`, `_models.py`, etc.) must be $\le 500$ physical lines (`wc -l`).
   - Package entrypoints (`__init__.py` / `index.ts`) should be concise re-export and orchestration files, ideally well under 200 lines.
3. **Zero Test Modifications**:
   - Existing automated tests (e.g., `tests/test_ui.py`, `tests/test_sandbox.py`, `sandbox/factory/events.test.ts`, frontend tests) must pass completely unmodified.
4. **Deep Module Cohesion**:
   - Private helpers must be grouped logically by subsystem, not artificially paginated.

## Delivery Sequence

### Tier 1: High Cognitive Risk (> 1,000 lines)
- **Ticket 01**: [`01-decompose-factory-ui-github.md`](./issues/01-decompose-factory-ui-github.md) (`factory/ui/github.py`, 1,472 lines)
- **Ticket 02**: [`02-decompose-factory-ui-registry.md`](./issues/02-decompose-factory-ui-registry.md) (`factory/ui/registry.py`, 1,353 lines)
- **Ticket 03**: [`03-decompose-factory-ui-grill.md`](./issues/03-decompose-factory-ui-grill.md) (`factory/ui/grill.py`, 1,284 lines)
- **Ticket 04**: [`04-decompose-sandbox-factory-events.md`](./issues/04-decompose-sandbox-factory-events.md) (`sandbox/factory/events.ts`, 1,164 lines)
- **Ticket 05**: [`05-decompose-factory-ui-app.md`](./issues/05-decompose-factory-ui-app.md) (`factory/ui/app.py`, 1,120 lines)
- **Ticket 06**: [`06-decompose-studio-view.md`](./issues/06-decompose-studio-view.md) (`factory/ui/frontend/src/views/StudioView.tsx`, 1,052 lines)

### Tier 2: Medium Bloat (650 – 853 lines)
- **Ticket 07**: [`07-decompose-frontend-app.md`](./issues/07-decompose-frontend-app.md) (`factory/ui/frontend/src/App.tsx`, 853 lines)
- **Ticket 08**: [`08-decompose-issue-drawer.md`](./issues/08-decompose-issue-drawer.md) (`factory/ui/frontend/src/components/IssueDrawer.tsx`, 715 lines)
- **Ticket 09**: [`09-decompose-sandbox-factory-harness.md`](./issues/09-decompose-sandbox-factory-harness.md) (`sandbox/factory/harness.ts`, 708 lines)
- **Ticket 10**: [`10-decompose-factory-ui-db.md`](./issues/10-decompose-factory-ui-db.md) (`factory/ui/db.py`, 687 lines)
- **Ticket 11**: [`11-decompose-sandbox-main.md`](./issues/11-decompose-sandbox-main.md) (`sandbox/main.py`, 681 lines)
- **Ticket 12**: [`12-decompose-live-preview.md`](./issues/12-decompose-live-preview.md) (`factory/ui/frontend/src/components/LivePreview.tsx`, 660 lines)

### Tier 3: Quick Wins (500 – 550 lines)
- **Ticket 13**: [`13-decompose-github-tracker.md`](./issues/13-decompose-github-tracker.md) (`sandbox/factory/tracker/github-tracker.ts`, 548 lines)
- **Ticket 14**: [`14-decompose-factory-spawner.md`](./issues/14-decompose-factory-spawner.md) (`factory/spawner.py`, 522 lines)
- **Ticket 15**: [`15-decompose-testing-console-view.md`](./issues/15-decompose-testing-console-view.md) (`factory/ui/frontend/src/views/TestingConsoleView.tsx`, 514 lines)
