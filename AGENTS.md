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

## Interaction Protocol

### Factory Studio: Grill Before Changing
When the user sends a chat message requesting changes, features, or fixes for Factory Studio, do NOT make code changes immediately. Instead, activate `/grill-with-docs` (executing `grilling` and `domain-modeling`) to interview the user, stress-test requirements, sharpen domain terminology, and align understanding before proposing or implementing any modifications.

