# 06: CLI Dispatcher and Autonomous Batch Execution

**What to build:** The command-line interface for developers to dispatch tasks to the software factory. When invoked with a feature slug, it inspects `.scratch/<feature>/issues/`, finds the next open unblocked ticket on the frontier, marks it claimed, and dispatches the job to the serverless Modal Factory Orchestrator while streaming progress logs to the terminal. When run with `--all`, it operates in autonomous batch mode: upon completing each ticket, it refreshes the frontier and dispatches subsequent unblocked tickets sequentially until all tickets in the feature tree are resolved or an unresolvable error occurs.

**Blocked by:** 05: Modal Factory Orchestrator and Ephemeral Sandbox Spawner

**Status:** ready-for-agent

- [ ] Implements the CLI dispatcher entry point accepting `--feature <slug>`
- [ ] Supports `--issue <id>` to target a specific ticket, defaulting to the next unblocked ticket on the frontier
- [ ] Supports `--all` to run an autonomous loop across all unblocked tickets until the feature is fully resolved
- [ ] Supports `--model` to toggle between `DeepSeek V4.1 Flash` and `MiMo-V2.6-Flash`
- [ ] Connects to the Modal Factory Orchestrator and streams execution logs to stdout
- [ ] Updates ticket statuses and local tracking files upon completion
