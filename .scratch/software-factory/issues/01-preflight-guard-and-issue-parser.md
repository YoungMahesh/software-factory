# 01: Pre-flight Guard and Issue Tracker Parser

**What to build:** A repository validation and ticket discovery module. When given a target repository workspace, it validates that the repository is configured for agent workflows under the domain standard, checking for the presence of the feature specification, domain context documentation, and local issue tracking setup. If any prerequisite is missing, it aborts with a clear, actionable error. When valid, it parses the local markdown issue files for a feature, resolves blocking dependencies, and identifies the next open, unblocked ticket on the frontier.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Validates presence of `.scratch/<feature>/spec.md` in the target repository
- [ ] Validates presence of `CONTEXT.md` at the repository root or in domain paths
- [ ] Validates presence of issue tracking configuration (`docs/agents/issue-tracker.md` or `## Agent skills` in `AGENTS.md`/`CLAUDE.md`)
- [ ] Aborts with an actionable error message if any prerequisite is missing
- [ ] Parses markdown ticket headers (`Status:`, `Blocked by:`) across `.scratch/<feature>/issues/`
- [ ] Identifies open and unblocked tickets on the frontier in numerical order
