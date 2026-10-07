# Factory Hub and Ticket Lifecycle Architecture

To manage multi-repo development cleanly, we decided to establish `software-factory` as a Factory Hub maintaining local markdown tickets in `.scratch/`, executing single-ephemeral-sandbox ticket lifecycles per issue with a 2-retry self-correction loop, and dispatching runs via a local CLI dispatcher.

## Considered Options

- **Target Repo Co-location of Tickets**: Storing `.scratch/` tickets directly inside the target repository. Rejected because it pollutes external repositories with factory-specific planning files, requires immediate remote push access for spec drafting, and prevents centralized oversight of multiple external repositories.
- **Multi-Sandbox Stage Separation**: Provisioning a separate Modal Sandbox for each stage (Planner, Coder, Verifier, Reviewer) attached to a shared Modal Volume. Rejected due to volume synchronization latency, cold-start compilation overhead, and risk of environment inconsistencies between stages.
- **Unbounded Self-Correction Loop**: Allowing the coding agent to retry indefinitely until tests pass. Rejected because circular debugging loops quickly burn API token budgets; capping retries at 2 balances automated recovery with timely human escalation.

## Consequences

- `.scratch/` specifications, task maps, and issue tickets are managed centrally in `software-factory`.
- Each assembly line execution provisions exactly one ephemeral Modal Sandbox that runs all stages sequentially on the warm checkout.
- If verification tests or code reviews fail, the error trace feeds back to the coding agent for up to 2 retries before marking the ticket `Status: ready-for-human`.
- The entry point for starting work is a local CLI Dispatcher (`factory/dispatch.py`).
