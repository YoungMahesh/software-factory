This repository is about creating scripts for modal.com sandboxes

Documentation: https://modal.com/docs/sdk/py/latest/Sandbox

## Domain docs

- Single-context layout: [`CONTEXT.md`](CONTEXT.md) and [`docs/adr/`](docs/adr/) at root.
- Adhere strictly to the domain glossary in [`CONTEXT.md`](CONTEXT.md).
- Consult [`docs/adr/`](docs/adr/) before modifying architecture; flag any conflicts before proposing contradictory designs.

## Code standards

### Universal file line budget and ratchet

- **Limit**: All production code files and executable automated test files (`.py`) in this repository must not exceed 500 physical lines (`wc -l`).
- **Exemptions**: Shell scripts (`.sh`) and external static fixture data files (e.g. raw JSON fixtures, plain text data files, and environment templates) are exempt.
- **Decomposition pattern**: Decompose large files into directory modules with private internal files behind a single small public interface (`__init__.py`), adhering to deep module principles. Test suites approaching or exceeding 500 lines must be decomposed into modular directory packages or subsystem test modules. Do not create shallow pass-through modules.
