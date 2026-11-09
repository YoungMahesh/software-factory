# Modal Sandboxes

Toolkit for provisioning, managing, and snapshotting isolated cloud execution environments and control planes on Modal.

Consult the `modal` skill (`.agents/skills/modal/SKILL.md`) when writing or modifying Modal SDK code.

## Agent skills

### Issue tracker

Local markdown files under `.scratch/<feature-slug>/`. See [`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md).

### Triage labels

Canonical five-role triage vocabulary. See [`docs/agents/triage-labels.md`](docs/agents/triage-labels.md).

### Domain docs

Single-context layout (`GLOSSARY.md` and `docs/adr/` at repo root). See [`docs/agents/domain.md`](docs/agents/domain.md).

## Code & Verification standards

### Verification

- **Automated tests**: Run `pytest` before finalizing changes. All tests and line budgets must pass cleanly.
- **Sandbox live verification**: When running end-to-end tests against live Modal infrastructure, strictly target the test baseline (`sFactory0/test-live-test1` using `--testing` or `scripts/test_live_sandbox.py`) and ensure immediate termination of launched sandboxes.

### Universal file line budget and ratchet

- **Limit**: All production code files and executable automated test files (`.py`) in this repository must not exceed 500 physical lines (`wc -l`), verified by `tests/test_standards.py`.
- **Exemptions**: Shell scripts (`.sh`) and external static fixture data files (e.g. raw JSON fixtures, plain text data files, and environment templates) are exempt.
- **Decomposition pattern**: Decompose large files into directory modules with private internal files behind a single small public interface (`__init__.py`), adhering to deep module principles. Test suites approaching or exceeding 500 lines must be decomposed into modular directory packages or subsystem test modules. Do not create shallow pass-through modules.
