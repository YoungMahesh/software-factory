# 06: CLI Runner and Host Dispatcher

**What to build:** The host-side command-line interface (`factory/run.py`) used by developers to launch software factory jobs against target projects. It accepts `--project <name>` (referencing `secrets/<project-name>/`), `--feature <slug>`, optional `--issue <id>` (defaulting to full autonomous batch mode across unblocked frontier tickets), optional `--vm` (for full virtualization), and optional `--model` (`DeepSeek V4.1 Flash` by default or `MiMo-V2.6-Flash`). It validates locally that `secrets/<project-name>/fetch.env` exists, triggers the Modal sandbox spawner, streams live execution logs to stdout, and propagates the sandbox's final exit code to the terminal.

**Blocked by:** 05: Modal Factory Sandbox Spawner and Container Entrypoint

**Status:** ready-for-agent

- [ ] Implements the host CLI entry point (`factory/run.py`) accepting `--project <name>` and `--feature <slug>`
- [ ] Validates locally that `secrets/<project-name>/fetch.env` exists before attempting cloud launch
- [ ] Supports `--issue <id>` to target a specific ticket, defaulting to the full unblocked feature frontier
- [ ] Supports `--vm` to dynamically launch a VM Sandbox instead of the default Standard Sandbox
- [ ] Supports `--model` to toggle between `DeepSeek V4.1 Flash` (default) and `MiMo-V2.6-Flash`
- [ ] Streams live sandbox logs to the terminal via `modal.enable_output()`
- [ ] Returns the sandbox process exit code cleanly upon completion
