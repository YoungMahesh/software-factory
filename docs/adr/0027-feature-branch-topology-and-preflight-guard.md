# Feature Branch Topology and Pre-Flight Guard

To support multi-ticket feature development safely across external repositories, we decided to accumulate ticket commits onto a shared feature branch (`factory/<feature>`), enforce a strict pre-flight guard validating `/setup-matt-pocock-skills` prerequisites upon sandbox boot, and standardize the default model to `DeepSeek V4.1 Flash` with CLI override to `MiMo-V2.6-Flash`.

## Considered Options

- **Isolated Per-Ticket Branches**: Create a new branch `factory/<feature>-<issue>` for each ticket. Rejected because dependent tickets (`Blocked by: 01`) in an autonomous batch (`--all`) require the working tree and code changes introduced by earlier tickets. A shared feature branch maintains continuous working tree state across tickets.
- **Permissive / Auto-Scaffold Pre-Flight**: Allow projects lacking `/setup-matt-pocock-skills` to run by guessing conventions. Rejected because missing `.scratch/` specifications or domain vocabularies causes unpredictable agent wandering; enforcing a strict pre-flight check guarantees that target repositories adhere to standardized issue tracking and domain boundaries.
- **Dynamic Model Fallback across Multiple Vendors**: Fall back across various external models. Rejected in favor of explicit configuration within OpenCode Go models (`DeepSeek V4.1 Flash` by default, `MiMo-V2.6-Flash` via `--model mimo`), ensuring predictable pricing, stable context windows, and zero vendor sprawl.

## Consequences

- All tickets executed under `.scratch/<feature>/` commit and push to `origin factory/<feature>`.
- The sandbox immediately validates the existence of `.scratch/<feature>/spec.md`, `CONTEXT.md`, and issue tracking setup, aborting with a clean error if missing.
- Default model execution uses `DeepSeek V4.1 Flash` via OpenCode Go, overridable to `MiMo-V2.6-Flash` via `--model`.
