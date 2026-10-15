# 15: Decompose factory/ui/frontend/src/views/TestingConsoleView.tsx

**What to build:**
Decompose `factory/ui/frontend/src/views/TestingConsoleView.tsx` (514 physical lines) by extracting the job launch form into a focused sub-component:
- Create `factory/ui/frontend/src/components/console/JobConfigPanel.tsx`:
  - Extract feature selector, custom feature input, issue dropdown, model picker, and VM/dev configuration checkboxes with launch button.
- Refactor `TestingConsoleView.tsx`:
  - Retain top-level layout combining repository header, `JobConfigPanel`, active job stage stepper, and terminal log stream.
  - Target size for `TestingConsoleView.tsx`: $\le 300$ physical lines.
- Invariant: Both files must be $\le 500$ physical lines (`wc -l`).
- Verification: Run `pnpm test` in `factory/ui/frontend` to ensure Testing Console UI interactions pass without modification.

**Blocked by:** 14-decompose-factory-spawner

**Status:** ready-for-agent
**Triage:** ready-for-agent

- [ ] Create `factory/ui/frontend/src/components/console/JobConfigPanel.tsx` and migrate job configuration form logic.
- [ ] Refactor `TestingConsoleView.tsx` to embed `JobConfigPanel`.
- [ ] Confirm all touched files are $\le 500$ physical lines.
- [ ] Verify `pnpm test` passes in `factory/ui/frontend`.
