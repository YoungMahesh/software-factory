# OpenCode Go Provider and Target Project Prerequisite

To power the software factory sustainably and standardize task boundaries, we decided to standardize model inference on the OpenCode Go subscription (`OPENCODE_GO_API_KEY`) using strictly `MiMo-V2.6-Flash` and `DeepSeek V4.1 Flash`, isolate `software-factory`'s `.scratch/` directory exclusively to self-modifications, and require that all target projects have their issue tracker and domain docs pre-configured via `/setup-matt-pocock-skills`.

## Considered Options

- **Direct Vendor Commercial APIs (Anthropic / OpenAI / Google)**: Require separate API keys for Claude or Gemini. Rejected in favor of the existing OpenCode Go subscription (`OPENCODE_GO_API_KEY`) pre-configured in `secrets/opencode.env`, avoiding redundant credential management and consolidating billing.
- **Centralized Ticket Pool in `software-factory` for All Projects**: Maintain `.scratch/<project>/` tickets in `software-factory`. Clarified and rejected for external projects: each target project must own its own `.scratch/` directory on its own repository so issue histories, ADRs, and specs stay co-located with the project source. `software-factory`'s `.scratch/` is strictly for modifying the factory itself.
- **Ad-hoc Repository Ingestion**: Allow the factory to work on repositories without structured issue tracking. Rejected because unstandardized repos lack predictable issue formats, triage labels, and domain vocabularies; requiring `/setup-matt-pocock-skills` guarantees uniform ticket reading, claiming, and resolution workflows.

## Consequences

- The Pi Agent harness inside the sandbox connects to OpenCode Go using `OPENCODE_GO_API_KEY` decrypted from `secrets/opencode.env`.
- Supported models for assembly line execution are strictly `MiMo-V2.6-Flash` and `DeepSeek V4.1 Flash`.
- Target projects must have executed `/setup-matt-pocock-skills` prior to factory dispatch, providing `.scratch/<feature>/spec.md` and `.scratch/<feature>/issues/<NN>-<slug>.md`.
- Modifications to `software-factory` itself use `.scratch/` at the repository root.
- The CLI Dispatcher supports single-ticket execution by default and autonomous batch mode via `--all`.
