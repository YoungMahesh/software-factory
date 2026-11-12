# Production File Line Budget and Ratchet

We established a 500 physical line budget (`wc -l`) for all production code files in this repository, enforced via agent review standards and a non-expansion ratchet on existing legacy files.

## Context

As the codebase expanded across backend services, frontend React views, and sandbox agent harnesses, 15 production files grew past 500 lines (and several past 1,000 lines). Large files degrade cognitive locality and increase the risk of LLM hallucinations during automated modification turns. At the same time, arbitrary file splitting risks creating shallow pass-through modules that violate our deep module principles.

## Decision

1. **500 Physical Line Budget**: Production files (`.py`, `.ts`, `.tsx`, `.js`) in the `software-factory` repository must not exceed 500 physical lines (`wc -l`).
2. **Exemptions**: Automated test suites (`tests/`, `*.test.ts`, `*.test.tsx`) and shell scripts (`.sh`) were initially exempt to encourage comprehensive test co-location and unbroken procedural bootstrap flows. *(Note: The test suite exemption is superseded by [ADR 0027](0027-universal-file-line-budget-and-test-suite-decomposition.md), which establishes a universal 500-line budget across both production and test code).*
3. **Deep Module Decomposition**: When a module exceeds 500 lines, it must be decomposed into a directory module with private internal helper files behind a single public interface (`__init__.py` or `index.ts`), preserving interface depth and avoiding leaky abstractions.
4. **Agent Quality Gate Enforcement**: The policy is enforced through the Reviewer Agent quality gate and `AGENTS.md` guidelines rather than a hard deterministic CI build failure, keeping developer flow flexible while preventing automated agent bloat.
5. **Dynamic Ratchet**: To avoid blocking work across the 15 existing files that exceed 500 lines, we apply a dynamic Git ratchet invariant: new production files must be <= 500 lines, and edits to existing files currently > 500 lines must have `net_lines_added <= 0`.
