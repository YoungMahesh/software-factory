# 01: In-Sandbox GitHub Issue Tracker Provider and Pre-Flight Guard

**What to build:** An in-sandbox GitHub integration and issue tracking provider abstraction that discovers feature milestones, queries issues, parses dependency edges (`Blocked by: #<id>`), computes the unblocked execution frontier in topological order, and updates pre-flight validation so repositories using GitHub do not require local `.scratch/` directories while still enforcing domain context prerequisites (`CONTEXT.md`).

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] A typed GitHub REST client operates inside the sandbox environment using Node.js native fetch and authenticates via repository environment credentials without external npm dependencies.
- [x] An issue tracker provider abstraction interface defines contracts for pre-flight validation, milestone/spec retrieval, frontier issue discovery, claiming, and resolving tickets.
- [x] A GitHub issue tracker provider queries remote milestones and issues, parses `Blocked by: #<id>` dependencies from issue descriptions, and sorts unblocked open candidate tickets into a valid frontier.
- [x] A local issue tracker provider wraps existing local markdown `.scratch/` parsing to guarantee backward compatibility with existing test suites.
- [x] Pre-flight validation checks environment token credentials and remote milestone availability when in GitHub mode, and confirms the presence of domain documentation (`CONTEXT.md` or `GLOSSARY.md`), succeeding without `.scratch/` trees present.
- [x] Comprehensive unit tests verify mock GitHub milestone and issue parsing, frontier sorting with dependencies, and pre-flight validation success/failure paths.

## Comments

### Quality Gate Audit

- All 102 TypeScript tests in `sandbox/factory` pass (including 20+ new tests for `GitHubClient`, `GitHubIssueTracker`, `LocalScratchTracker`, tracker auto-detection, and GitHub preflight validation).
- Full Python test suite (65 tests) passes.
- TypeScript typecheck (`tsc --noEmit`) passes with zero errors.

