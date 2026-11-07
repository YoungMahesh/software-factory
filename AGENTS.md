This repository is about creating scripts for modal.com sandboxes

Documentation: https://modal.com/docs/sdk/py/latest/Sandbox

## Agent skills

### Issue tracker

Local markdown files under `.scratch/<feature-slug>/`. See [`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md).

### Triage labels

Canonical five-role triage vocabulary. See [`docs/agents/triage-labels.md`](docs/agents/triage-labels.md).

### Domain docs

Single-context layout (`GLOSSARY.md` and `docs/adr/` at repo root). See [`docs/agents/domain.md`](docs/agents/domain.md).

## Code standards

### Universal file line budget and ratchet

- **Limit**: All production code files and executable automated test files (`.py`) in this repository must not exceed 500 physical lines (`wc -l`).
- **Exemptions**: Shell scripts (`.sh`) and external static fixture data files (e.g. raw JSON fixtures, plain text data files, and environment templates) are exempt.
- **Decomposition pattern**: Decompose large files into directory modules with private internal files behind a single small public interface (`__init__.py`), adhering to deep module principles. Test suites approaching or exceeding 500 lines must be decomposed into modular directory packages or subsystem test modules. Do not create shallow pass-through modules.
