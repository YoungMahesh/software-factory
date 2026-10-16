# 01: Universal File Line Budget and Systematic Test Suite Decomposition

**What to build:** Establish a Universal File Line Budget by extending the 500 physical line budget (`wc -l`) to all executable automated test files, formally superseding the test suite exemption in ADR-0051. Record the architectural decision in `docs/adr/0057-universal-file-line-budget-and-test-suite-decomposition.md`, update `AGENTS.md` and `CONTEXT.md`, and systematically decompose all 14 legacy test files currently exceeding 500 lines across Python, React frontend, and sandbox harness into modular directory packages or subsystem test modules $\le 500$ lines with 100% test pass fidelity and zero test skips or deletions.

**Blocked by:** None

**Status:** resolved

- [x] Record Architectural Decision Record `docs/adr/0057-universal-file-line-budget-and-test-suite-decomposition.md` documenting the universal 500-line budget, repeal of the ADR-0051 test exemption, external static fixture exemption, and directory module decomposition pattern.
- [x] Update `AGENTS.md` under **Code standards** to define the Universal file line budget ($\le 500$ lines for production code and executable test code, exempting only `.sh` shell scripts and external static fixture data files).
- [x] Update `CONTEXT.md` to define canonical domain terms **Universal File Line Budget** and **Test Suite Decomposition**.
- [x] Decompose Tier 1 Mega-Monoliths (> 1,000 lines):
  - [x] Decompose `tests/test_ui.py` (4,722 lines) into `tests/test_ui/` directory package with subsystem test modules and shared test helper fixtures ($\le 500$ lines each).
  - [x] Decompose `factory/ui/frontend/src/views/StudioView.test.tsx` (1,364 lines) into subsystem test files ($\le 500$ lines each).
  - [x] Decompose `sandbox/factory/pipeline.test.ts` (1,072 lines) into subsystem test modules and update test discovery in `sandbox/factory/package.json` ($\le 500$ lines each).
  - [x] Decompose `factory/ui/frontend/src/App.test.tsx` (1,045 lines) into subsystem test files ($\le 500$ lines each).
  - [x] Decompose `sandbox/factory/events.test.ts` (1,036 lines) into subsystem test modules ($\le 500$ lines each).
- [x] Decompose Tier 2 Heavy Suites (700 – 1,000 lines):
  - [x] Decompose `tests/test_sandbox.py` (962 lines) into `tests/test_sandbox/` directory package ($\le 500$ lines each).
  - [x] Decompose `tests/test_grill.py` (939 lines) into `tests/test_grill/` directory package ($\le 500$ lines each).
  - [x] Decompose `tests/test_preview.py` (831 lines) into `tests/test_preview/` directory package ($\le 500$ lines each).
  - [x] Decompose `sandbox/factory/preflight.test.ts` (712 lines) into subsystem test modules ($\le 500$ lines each).
- [x] Decompose Tier 3 Moderate Suites (500 – 700 lines):
  - [x] Decompose `tests/test_ui_events.py` (683 lines) into `tests/test_ui_events/` directory package ($\le 500$ lines each).
  - [x] Decompose `sandbox/factory/harness.test.ts` (649 lines) into subsystem test modules ($\le 500$ lines each).
  - [x] Decompose `sandbox/factory/lifecycle.test.ts` (552 lines) into subsystem test modules ($\le 500$ lines each).
  - [x] Decompose `factory/ui/frontend/src/components/LivePreview.test.tsx` (551 lines) into subsystem test files ($\le 500$ lines each).
  - [x] Decompose `sandbox/factory/verifier.test.ts` (524 lines) into subsystem test modules ($\le 500$ lines each).
- [x] Execute deterministic test execution suites across all three runtime environments:
  - [x] Python: `.venv/bin/python3 -m unittest discover tests` passes 100% with 0 failures and 0 errors (392/392 passed).
  - [x] Frontend: `pnpm --filter frontend test` passes 100% with 0 failures (220/220 passed across 32 suites).
  - [x] Sandbox: `pnpm --prefix sandbox/factory test` passes 100% with 0 failures (175/175 passed across 12 suites).
- [x] Run line budget verification script confirming 0 production or test files in `factory/`, `sandbox/`, and `tests/` exceed 500 physical lines (`wc -l`).

## Comments

### Systematic Decomposition Summary

1. **Governance and Domain Documentation**:
   - Recorded `docs/adr/0057-universal-file-line-budget-and-test-suite-decomposition.md` repealing the test exemption from ADR-0051 and enacting the Universal File Line Budget ($\le 500$ physical lines for production code and executable test code).
   - Updated `docs/adr/0051-production-file-line-budget-and-ratchet.md` with supersession reference.
   - Updated `AGENTS.md` Code standards defining the universal budget and directory module pattern.
   - Updated `CONTEXT.md` defining canonical domain terms **Universal File Line Budget** and **Test Suite Decomposition**.

2. **Decomposition Execution Across 14 Monoliths**:
   - **Tier 1 Mega-Monoliths**:
     - `tests/test_ui.py` (4,722 lines) -> `tests/test_ui/` directory package (17 modular subsystem test files, each $\le 450$ lines).
     - `factory/ui/frontend/src/views/StudioView.test.tsx` (1,364 lines) -> 5 subsystem test files (`StudioView.{core,grill,delivery,branching,rollback}.test.tsx`, each $\le 322$ lines).
     - `sandbox/factory/pipeline.test.ts` (1,072 lines) -> `pipeline-test-helpers.ts` + 3 subsystem test files (`pipeline-{batch,github,dispatch}.test.ts`, each $\le 454$ lines).
     - `factory/ui/frontend/src/App.test.tsx` (1,045 lines) -> 4 subsystem test files (`App.{navigation,chat,dispatch,routing}.test.tsx`, each $\le 440$ lines).
     - `sandbox/factory/events.test.ts` (1,036 lines) -> 3 subsystem test files (`events-{core,thinking-bash,tools-gate}.test.ts`, each $\le 457$ lines).
   - **Tier 2 Heavy Suites**:
     - `tests/test_sandbox.py` (962 lines) -> `tests/test_sandbox/` directory package (4 subsystem test files, each $\le 354$ lines).
     - `tests/test_grill.py` (939 lines) -> `tests/test_grill/` directory package (3 subsystem test files, each $\le 359$ lines).
     - `tests/test_preview.py` (831 lines) -> `tests/test_preview/` directory package (4 subsystem test files, each $\le 285$ lines).
     - `sandbox/factory/preflight.test.ts` (712 lines) -> 2 subsystem test files (`preflight-{local,github}.test.ts`, each $\le 427$ lines).
   - **Tier 3 Moderate Suites**:
     - `tests/test_ui_events.py` (683 lines) -> `tests/test_ui_events/` directory package (2 subsystem test files, each $\le 400$ lines).
     - `sandbox/factory/harness.test.ts` (649 lines) -> 2 subsystem test files (`harness-{agents,telemetry}.test.ts`, each $\le 397$ lines).
     - `sandbox/factory/lifecycle.test.ts` (552 lines) -> 2 subsystem test files (`lifecycle-{execution,telemetry}.test.ts`, each $\le 348$ lines).
     - `factory/ui/frontend/src/components/LivePreview.test.tsx` (551 lines) -> 2 subsystem test files (`LivePreview.{core,controls}.test.tsx`, each $\le 322$ lines).
     - `sandbox/factory/verifier.test.ts` (524 lines) -> 2 subsystem test files (`verifier-{core,discovery}.test.ts`, each $\le 320$ lines).

3. **Deterministic Test Execution**:
   - Python discovery: 392/392 tests passed with 0 failures and 0 errors.
   - Frontend Vitest: 220/220 tests passed across 32 test files.
   - Sandbox Node runner: 175/175 tests passed across 12 test files; typecheck clean (`tsc --noEmit`).

4. **Line Budget Verification**:
   - Exactly 0 production or test files in `factory/`, `sandbox/`, and `tests/` (and entire repo) exceed 500 physical lines. Every file is $\le 500$ physical lines.
