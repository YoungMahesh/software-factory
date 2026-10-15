This repository is about creating scripts for modal.com sandboxes

Documentation: https://modal.com/docs/sdk/py/latest/Sandbox

## Domain docs

- Single-context layout: [`CONTEXT.md`](CONTEXT.md) and [`docs/adr/`](docs/adr/) at root.
- Adhere strictly to the domain glossary in [`CONTEXT.md`](CONTEXT.md).
- Consult [`docs/adr/`](docs/adr/) before modifying architecture; flag any conflicts before proposing contradictory designs.

## Agent skills

### Issue tracker

Local markdown files under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical five-role triage labels. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: `CONTEXT.md` and `docs/adr/` at root. See `docs/agents/domain.md`.

## Code standards

### Production file line budget and ratchet

- **Limit**: Production code files (`.py`, `.ts`, `.tsx`, `.js`) in this repository must not exceed 500 physical lines (`wc -l`).
- **Exemptions**: Automated test files (`tests/`, `*.test.ts`, `*.test.tsx`) and shell scripts (`.sh`) are exempt.
- **Decomposition pattern**: Decompose large files into directory modules with private internal files behind a single small public interface (`__init__.py` or `index.ts`), adhering to deep module principles ([`.agents/skills/codebase-design/SKILL.md`](.agents/skills/codebase-design/SKILL.md)). Do not create shallow pass-through modules.
- **Ratchet on legacy files**: Any newly created production file must be <= 500 lines. Any modified legacy production file currently > 500 lines must not increase in line count (`net_lines_added <= 0`). See [`docs/adr/0051-production-file-line-budget-and-ratchet.md`](docs/adr/0051-production-file-line-budget-and-ratchet.md).
