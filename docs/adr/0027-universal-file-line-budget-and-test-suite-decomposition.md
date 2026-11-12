# Universal File Line Budget and Systematic Test Suite Decomposition

**Status**: Accepted (Supersedes the test suite exemption in [ADR 0005](0026-production-file-line-budget-and-ratchet.md))

We established a Universal File Line Budget by extending the 500 physical line budget (`wc -l`) to all executable automated test files in this repository, formally repealing the test suite exemption in ADR-0005, while continuing to exempt procedural shell scripts and external static fixture files.

## Context

In ADR-0005, we instituted a 500 physical line budget for production code files to maintain cognitive locality, prevent LLM hallucination during automated code modification, and uphold deep module decomposition principles. However, automated test suites (`tests/`, `*.test.ts`, `*.test.tsx`) were initially granted an exemption to encourage test co-location and avoid premature test splitting.

Over time, this exemption permitted 14 test suites across the Python backend, React frontend, and sandbox agent harness to expand far beyond maintainable thresholds—with mega-monoliths reaching upwards of 4,700 lines. These oversized test suites:
1. Obscured subsystem boundaries and degraded readability during development and debugging.
2. Incurred significant cognitive fatigue and elevated prompt token consumption for automated coding agents, increasing the risk of hallucinations when modifying tests for localized features.
3. Slowed down targeted test runs and made locating failures cumbersome.
4. Created an inconsistent engineering standard between production code (strictly capped at 500 lines) and test code.

## Decision

1. **Universal 500 Physical Line Budget**: All executable code files—both production code (`.py`, `.ts`, `.tsx`, `.js`) and executable automated test suites (`tests/`, `*.test.ts`, `*.test.tsx`)—must not exceed 500 physical lines (`wc -l`).
2. **Repeal of ADR-0005 Test Exemption**: The automated test suite exemption declared in ADR-0005 is formally repealed and superseded by this decision.
3. **Exemptions Boundary**:
   - Shell scripts (`.sh`) remain exempt to preserve unbroken procedural container bootstrap and tooling setup flows.
   - External static fixture files (such as raw JSON payloads, plain text fixture files, and environment templates) remain exempt. This encourages developers and agents to externalize large static payloads into dedicated data files rather than inlining multiline literal strings into test code.
4. **Directory Module and Subsystem Test Decomposition**: When a test suite approaches or exceeds 500 lines, it must be decomposed into modular directory packages (e.g. `tests/<suite>/`) or subsystem test files (e.g. `<component>.<subsystem>.test.tsx` or `<module>.<subsystem>.test.ts`) adhering to deep module principles. Shared test helper functions and fixtures should be organized cleanly in helper modules within the test package.
5. **Zero Test Modification Invariant**: Test suite decomposition must be a purely structural refactoring. No existing assertions, test cases, or mock verifications may be deleted, commented out, or weakened. All decomposed tests must maintain 100% test pass fidelity across Python `unittest`, Vitest, and Node test runners.
6. **Discovery Compatibility**: Test discovery across Python `unittest` (`-m unittest discover tests`), React frontend Vitest (`pnpm --filter frontend test`), and Node test runner (`node --test`) must discover and execute all decomposed test files without manual configuration hurdles.

## Consequences

- The canonical domain terms **Universal File Line Budget** and **Test Suite Decomposition** are recorded in `CONTEXT.md`.
- `AGENTS.md` is updated under **Code standards** to specify the universal 500-line budget for all production and test files.
- All 14 legacy monolithic test files exceeding 500 lines across Python backend, React frontend, and sandbox harness are decomposed into modular test suites of $\le 500$ physical lines.
- Developers and automated coding agents can read, understand, and modify individual subsystem test files with high cognitive locality and low token overhead.
