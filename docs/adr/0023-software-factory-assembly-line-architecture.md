# Software Factory Assembly Line Architecture

To build a reliable software factory, we decided to structure the system as a serverless Modal application (Factory Orchestrator) that provisions ephemeral Modal Sandboxes per job, executing a sequential Assembly Line Pipeline (Planner, Coder, Verifier, Reviewer) driven by a Local Markdown Issue Tracker (`.scratch/`) and gated by a multi-tier Quality Gate, operating on external repositories via SOPS secrets.

## Considered Options

- **Single Generalist Agent Loop**: Run an unconstrained coding agent directly in a sandbox until it declares completion. Rejected due to high token waste, context degradation, lack of reproducible handoffs, and compounding hallucinations.
- **GitHub Pull Requests as Delivery Target**: Drive work through GitHub PRs and webhooks. Deferred/rejected in favor of a Local Markdown Issue Tracker (`.scratch/`) to enable offline/local-first iteration, reproducible specification trees, and seamless integration with existing repo-local agent skills.
- **Local CLI Orchestrator**: Run the orchestrator on a local developer machine dispatching sandboxes. Rejected in favor of a serverless Modal App to achieve cloud-native zero-idle-cost execution independent of local machine uptime.
- **Sequential Assembly Line with Multi-Tier Gate**: A serverless Modal orchestrator driving ephemeral Modal Sandboxes through discrete Planner -> Coder -> Verifier -> Reviewer stages backed by `.scratch/` and deterministic test verification. Accepted because it enforces strict transition artifacts, prevents hallucinations from reaching code, and guarantees clean ephemeral sandbox isolation.

## Consequences

- The Factory Orchestrator will be deployed as a serverless Modal application.
- Target issues and specifications will be read from and written to `.scratch/<feature>/` in the repository.
- Each assembly line job runs inside an ephemeral Modal Sandbox provisioned on demand.
- Stages hand off explicit structured artifacts (spec/plan -> code diff -> test execution log -> review verdict).
- A work item is only marked resolved in `.scratch/` after passing the multi-tier Quality Gate (deterministic tests, reproduction test, and independent review).
