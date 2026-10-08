# 06: CLI Runner and Host Dispatcher

**What to build:** The host-side command-line interface (`factory/run.py`) used by developers to launch software factory jobs against target projects. It accepts `--project <name>` (referencing `secrets/<project-name>/` or `secrets_testing/<project-name>/` when `--testing`), `--feature <slug>`, optional `--issue <id>` (defaulting to full autonomous batch mode across unblocked frontier tickets), optional `--vm` (for full virtualization), optional `--model` (`DeepSeek V4.1 Flash` by default or `MiMo-V2.6-Flash`), and optional `--testing` / `--test` (for test repository fixtures). It validates locally that the target project `fetch.env` exists, triggers the Modal sandbox spawner, streams live execution logs to stdout, and propagates the sandbox's final exit code to the terminal.

**Blocked by:** 05: Modal Factory Sandbox Spawner and Container Entrypoint

**Status:** resolved

- [x] Implements the host CLI entry point (`factory/run.py`) accepting `--project <name>` and `--feature <slug>`
- [x] Validates locally that `fetch.env` exists in `secrets/<project-name>/` (or `secrets_testing/<project-name>/` when testing) before attempting cloud launch
- [x] Supports `--testing` / `--test` flag to target isolated test repositories under `secrets_testing/`
- [x] Supports `--issue <id>` to target a specific ticket, defaulting to the full unblocked feature frontier
- [x] Supports `--vm` to dynamically launch a VM Sandbox instead of the default Standard Sandbox
- [x] Supports `--model` to toggle between `DeepSeek V4.1 Flash` (default) and `MiMo-V2.6-Flash`
- [x] Streams live sandbox logs to the terminal via `modal.enable_output()`
- [x] Returns the sandbox process exit code cleanly upon completion

## Comments

Implemented the host CLI entry point (`factory/run.py`) and dispatcher engine following TDD across three modular seams:

1. **CLI Argument Parser & Model Normalization (`factory/run.py`)**:
   - Accepts `--project` (`-p`) and `--feature` (`-f`) as required flags.
   - Accepts `--issue` (`-i`), defaulting to `None` for Autonomous Feature Batch execution.
   - Supports `--vm` (with optional `--memory <GB>`) for full VM sandboxes.
   - Supports `--testing` / `--test` to target test fixtures under `secrets_testing/`.
   - Supports `--model` (`-m`), defaulting to `DeepSeek V4.1 Flash` (`deepseek-v4.1-flash`) and allowing toggling to `MiMo-V2.6-Flash` (`mimo-v2.6-flash`). Normalizes case, aliases, and hyphenation while rejecting unsupported models with clean CLI errors.
   - Enhanced `sandbox/factory/provider.ts` to normalize model display names with spaces identically.

2. **Local Pre-Flight Secret Validation (`validate_project_secrets`)**:
   - Validates that `fetch.env` exists in `secrets/<project>/` or `secrets_testing/<project>/` prior to cloud launch.
   - Rejects missing secret bundles cleanly on stderr with exit code 1 without calling Modal APIs.

3. **Execution Dispatch & Log Streaming (`main`)**:
   - Wraps sandbox execution in `modal.enable_output()` context.
   - Dispatches via `factory.orchestrator.dispatch_job` with live streaming to stdout/stderr.
   - Propagates the sandbox process return code cleanly to the terminal (0 on success, non-zero on failure).
   - Re-exports `main`, `run_cli`, and secret validation at top-level `factory` package.

4. **Test Verification & Quality**:
   - 41 passing Python unit tests (`pytest`).
   - 82 passing TypeScript unit tests (`pnpm test` in `sandbox/factory`).
   - Clean static typecheck with zero errors across all modules (`mypy factory/ tests/`).
   - Verified live in Modal Cloud Sandbox via `./factory/run.py --project test3 --feature slug-generator --testing` with end-to-end log streaming, successful ticket resolution, remote GitHub push (`factory/slug-generator`), and clean exit code 0.
