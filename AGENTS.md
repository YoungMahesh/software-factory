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

### Universal file line budget and ratchet

- **Limit**: All production code files and executable automated test files (`.py`, `.ts`, `.tsx`, `.js`) in this repository must not exceed 500 physical lines (`wc -l`).
- **Exemptions**: Shell scripts (`.sh`) and external static fixture data files (e.g. raw JSON fixtures, plain text data files, and environment templates) are exempt.
- **Decomposition pattern**: Decompose large files into directory modules with private internal files behind a single small public interface (`__init__.py` or `index.ts`), adhering to deep module principles ([`.agents/skills/codebase-design/SKILL.md`](.agents/skills/codebase-design/SKILL.md)). Test suites approaching or exceeding 500 lines must be decomposed into modular directory packages or subsystem test modules. Do not create shallow pass-through modules.
- **Ratchet on legacy files**: Any newly created production or test file must be <= 500 lines. Any modified legacy file currently > 500 lines must not increase in line count (`net_lines_added <= 0`). See [`docs/adr/0051-production-file-line-budget-and-ratchet.md`](docs/adr/0051-production-file-line-budget-and-ratchet.md) and [`docs/adr/0057-universal-file-line-budget-and-test-suite-decomposition.md`](docs/adr/0057-universal-file-line-budget-and-test-suite-decomposition.md).

### Frontend build artifacts

- **Freshness mandate**: Whenever modifying any code or dependencies under `factory/ui/frontend/` (such as `src/`, `package.json`, or config files), you MUST run `pnpm --dir factory/ui/frontend build` to recompile the static production bundle into `factory/ui/static/dist/`.
- **Atomic commit**: Always commit the updated `factory/ui/static/dist/` bundle in the same commit or PR as the frontend source changes. Never leave `factory/ui/static/dist/` stale or divergent from `factory/ui/frontend/src/`.
- **Automated enforcement**: Subsystem test `tests/test_ui/test_frontend_dist_freshness.py` validates production bundle integrity and verifies that `factory/ui/static/dist/` has zero uncommitted diff after running `pnpm build`.

