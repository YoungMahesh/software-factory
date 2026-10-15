# 13: Decompose sandbox/factory/tracker/github-tracker.ts

**What to build:**
Decompose `sandbox/factory/tracker/github-tracker.ts` (548 physical lines) by extracting GitHub delivery gate operations into a dedicated internal helper:
- Create `sandbox/factory/tracker/github-delivery-gates.ts`:
  - Methods: `initDeliveryGate()`, `updateDeliveryGate()`, `finalizeDeliveryGate()`, and PR comment formatting.
- Refactor `github-tracker.ts`:
  - Retain `GitHubIssueTracker` class focusing on issue discovery, ticket claiming, status transitions, and issue resolution.
  - Delegate delivery gate lifecycle calls to `github-delivery-gates.ts`.
  - Target size for `github-tracker.ts`: $\le 350$ physical lines.
- Invariant: Both files must be $\le 500$ physical lines (`wc -l`).
- Verification: Run `pnpm test` in `sandbox/factory` to ensure GitHub issue tracker operations and delivery gates pass without modification.

**Blocked by:** 12-decompose-live-preview

**Status:** ready-for-agent
**Triage:** ready-for-agent

- [ ] Create `sandbox/factory/tracker/github-delivery-gates.ts` and migrate delivery gate evaluation logic.
- [ ] Refactor `GitHubIssueTracker` in `github-tracker.ts` to delegate delivery gate operations.
- [ ] Ensure all touched files are $\le 500$ physical lines.
- [ ] Verify `pnpm test` passes in `sandbox/factory`.
