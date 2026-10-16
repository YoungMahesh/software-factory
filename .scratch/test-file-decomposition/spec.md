# Spec: Universal File Line Budget and Test Suite Decomposition

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

Developers and automated coding agents operating in the repository face significant cognitive fatigue, elevated token consumption, and increased risk of hallucinations when interacting with massive test files. While all production code files in the repository adhere strictly to a 500 physical line budget established in ADR-0051, automated test files were previously exempt.

Over time, this exemption has permitted 14 test suites across the Python backend, React frontend, and sandbox agent harness to expand far beyond manageable limits—with extreme monoliths reaching upwards of 4,700 lines. These oversized test suites:
1. Obscure subsystem boundaries and degrade readability during local development.
2. Force automated coding agents to ingest thousands of irrelevant lines into context windows when updating tests for small, localized features.
3. Slow down targeted test execution and make locating failing test scenarios cumbersome.
4. Create an inconsistent engineering standard between production and test code.

## Solution

Establish a Universal File Line Budget by extending the 500 physical line budget to all executable automated test files, formally superseding the test suite exemption in ADR-0051.

Decompose all 14 legacy test files exceeding 500 lines into modular directory packages and subsystem test modules adhering to deep module principles. Keep shell scripts and externalized static test fixture assets exempt, while ensuring 100% test pass fidelity and zero test modifications or skips.

## User Stories

1. As a software engineer, I want all test files in the repository to adhere to a 500 physical line budget, so that every test suite remains readable, focused, and cognitively accessible.
2. As an automated coding agent, I want smaller, cohesive test files, so that I can inspect and edit relevant test scenarios without overflowing my prompt token context or hallucinating.
3. As a developer navigating Python backend test suites, I want monolithic test files decomposed into directory packages with subsystem test modules, so that I can quickly locate tests relevant to the subsystem I am modifying.
4. As a test author, I want shared test fixtures and test utilities localized to their respective test package directories, so that fixtures remain well-scoped rather than leaking into global test state.
5. As a frontend engineer, I want large React component test suites decomposed by feature or user interaction workflow, so that component test files remain concise and maintainable.
6. As a sandbox harness engineer, I want pipeline and agent lifecycle tests split into focused stage modules, so that testing runner behavior is modular and easy to debug.
7. As a developer running tests locally, I want standard test runner commands (Python unittest, Vitest, Node test runner) to discover and run all decomposed tests seamlessly without manual configuration changes.
8. As a developer working with large mock data payloads, I want external static fixture files (such as raw JSON dumps or simulated container log captures) to be exempt from the 500-line budget, so that realistic test payloads do not have to be artificially truncated.
9. As a software factory maintainer, I want the universal file line budget documented in `AGENTS.md` and recorded in a new Architectural Decision Record (superseding ADR-0051), so that team members and agents adhere to the updated standard.
10. As a software factory maintainer, I want the domain concepts defined in `CONTEXT.md`, so that the repository's domain glossary accurately reflects the universal file line budget and test suite decomposition patterns.
11. As a reviewer agent inspecting pull requests, I want the Reviewer Agent to enforce the 500-line limit across both production and test code, so that newly introduced test files never exceed 500 lines.
12. As a continuous integration runner, I want all decomposed test suites to pass 100% with identical coverage and zero skipped tests, so that test fidelity and regression detection are completely preserved.
13. As a developer, I want shell scripts to remain exempt from line limits, so that procedural container bootstrap flows and setup sequences remain unbroken.
14. As a developer modifying a single subsystem, I want to be able to execute only the relevant test file without having to run a 4,000-line monolithic test suite, so that my local feedback loop is fast.
15. As a maintainer planning work, I want a single unified issue tracking the codification of the policy and the phased execution of test suite decomposition, so that progress is clear and accountable.

## Implementation Decisions

- **Universal 500 Physical Line Budget**:
  - The line budget applies universally to all production code and executable automated test code files.
  - Sizing is determined strictly by physical line count (`wc -l <= 500`).
- **Repeal of ADR-0051 Test Exemption**:
  - The prior exemption for automated test suites in ADR-0051 is formally superseded by a new Architectural Decision Record.
  - `AGENTS.md` is updated to reflect that automated test files must not exceed 500 physical lines.
- **Exemptions Boundary**:
  - Shell scripts (`.sh`) remain exempt to preserve procedural setup flows.
  - External static fixture files (such as raw JSON files, plain text fixture files, and environment templates) remain exempt, encouraging developers to externalize large static payloads rather than inlining multiline strings into test code.
- **Decomposition Topology**:
  - Monolithic test files are decomposed into directory packages containing focused subsystem test modules.
  - Each directory package groups related test scenarios and includes local helper or fixture modules where appropriate.
  - Test runner discovery conventions (Python unittest discovery, Vitest test pattern matching, Node test runner pattern matching) are preserved or updated so that all tests run automatically.
- **Zero Test Modification Invariant**:
  - Test suite decomposition must be a pure structural refactoring.
  - No existing assertions, test cases, or mock verifications may be deleted, commented out, or weakened.
- **Immediate Bulk Refactoring Sequencing**:
  - Governance documentation and issue tracking are established first.
  - Decompositions proceed across three prioritized tiers (Tier 1: Mega-Monoliths > 1,000 lines; Tier 2: Heavy Suites 700–1,000 lines; Tier 3: Moderate Suites 500–700 lines).

## Testing Decisions

- **Good Test Criteria**:
  - A good test verifies external system behavior and observable contracts, not internal implementation mechanics.
  - Refactoring tests must preserve the exact same behavioral coverage and assertions as before the split.
- **Testing Seams**:
  - **Budget Verification Seam**: Deterministic line count validation asserting that every executable test file is $\le 500$ lines (`wc -l`).
  - **Python Test Runner Seam**: Full test discovery via Python's standard unittest runner asserting all unit tests pass with zero failures.
  - **Frontend Test Runner Seam**: Vitest runner asserting that all React component and hook test suites execute with zero failures.
  - **Sandbox Harness Test Runner Seam**: Node test runner asserting that all sandbox agent, pipeline, and telemetry tests execute with zero failures.
- **Prior Art**:
  - The successful production file decomposition initiative (ADR-0051 and its feature spec), which systematically decomposed 15 production files into sub-500-line directory packages without regressions.

## Out of Scope

- Rewriting, altering, or removing existing test assertions or business logic verifications.
- Changing production source code or public API signatures.
- Enforcing line limits on external non-code assets, mock JSON payloads, or shell scripts.

## Further Notes

- Following decomposition, the repository will achieve 100% compliance with the 500-line budget across both production and test files.
