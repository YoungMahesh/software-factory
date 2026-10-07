# Target Repo Ticket Co-location and In-Sandbox Batch Execution

**Status**: Accepted (Supersedes [ADR 0024](0024-factory-hub-and-ticket-lifecycle.md))

To streamline multi-project development and eliminate duplicated parsing logic across languages, we decided to co-locate `.scratch/` specifications and issue tickets directly inside target repositories, execute pre-flight prerequisite checks and ticket discovery solely within ephemeral Modal sandboxes via TypeScript, and run autonomous feature batches inside a single warm sandbox provisioned via a lightweight Python host launcher using project secrets (`secrets/<project-name>`).

## Considered Options

- **Centralized Ticket Storage in Factory Hub (ADR 0024)**: Maintaining `.scratch/` tickets centrally in `software-factory`. Superseded because target repositories need to own their own requirements in version control, and forcing the host to scan target tickets before launch coupled host workflows to target repository filesystems.
- **Dual Host and Sandbox Ticket Parsing (`factory/preflight.py` and `sandbox/factory/preflight.ts`)**: Maintaining parallel Python and TypeScript pre-flight and ticket parser implementations. Rejected because it introduces dual maintenance burden and behavioral drift; ticket discovery is only needed where the target repository is actually cloned (inside the sandbox).
- **Ephemeral Sandbox Per Ticket**: Spinning up a separate Modal sandbox for every ticket in a feature. Rejected due to repetitive container initialization latency, repository clone overhead, and package installation delays between dependent tickets.
- **In-Sandbox Co-located Tickets with Single Warm Batch Sandbox**: The host passes `--project <name> --feature <slug> [--issue <id>]`, provisions a single warm sandbox with mounted factory harness code, and executes an in-sandbox autonomous batch pipeline against the cloned repository. Accepted because it maintains clean separation of concerns, guarantees crash resilience by pushing per resolved ticket, and optimizes execution time.

## Consequences

- Target repositories track `.scratch/<feature>/spec.md` and `.scratch/<feature>/issues/` in Git under version control.
- `factory/preflight.py` and `tests/test_preflight.py` are removed; `sandbox/factory/preflight.ts` is the single source of truth for repository prerequisite validation and frontier discovery.
- The host launcher (`python factory/run.py`) validates that `secrets/<project-name>/fetch.env` exists locally and calls `modal.Sandbox.create()` with mounted `sandbox/factory/` code, reusing the 16-hour timeout from `sandbox/main.py`.
- The sandbox boots via a dedicated factory entrypoint that clones the repo, checks out `factory/<feature>` (forking from `main` if remote branch is absent), preserves `GH_TOKEN` for pushing, and executes the TypeScript assembly line harness.
- Tickets are processed in numerical frontier order: each resolved ticket is committed and pushed to `origin factory/<feature>` immediately. If a ticket fails after 2 retries and marks `Status: ready-for-human`, the batch halts immediately with diagnostics committed to the feature branch.
