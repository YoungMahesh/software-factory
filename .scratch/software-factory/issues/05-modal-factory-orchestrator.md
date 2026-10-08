# 05: Modal Factory Sandbox Spawner and Container Entrypoint

**What to build:** The Modal sandbox provisioning engine and container entrypoint for the software factory. When given a target repository secret name (`secrets/<project-name>` or `secrets_testing/<project-name>` when `--testing` is set), feature slug, and optional ticket ID, it provisions an ephemeral Modal Sandbox (Standard Sandbox by default, dynamically promoted to VM Sandbox when `--vm` is requested) with a 16-hour timeout. It mounts organization secrets (`share0` for SOPS bootstrap), stages project secrets (`secrets/<project-name>/` or `secrets_testing/<project-name>/`), prefixes the Modal app name with `test-` when testing per ADR 0029, and mounts the local factory harness (`sandbox/factory/`) into `/root/factory/`. Inside the container, a dedicated factory entrypoint decrypts fetch credentials, clones the target repository, checks out `factory/<feature>`, preserves `GH_TOKEN` for assembly line pushing, decrypts OpenCode credentials, and invokes the in-sandbox pipeline.

**Blocked by:** 04: Assembly Line Pipeline and Self-Correction Loop

**Status:** resolved

- [x] Implements the Modal sandbox creation helper using `modal.Sandbox.create()` and the unified base image
- [x] Mounts the local factory TypeScript harness (`sandbox/factory/`) to `/root/factory/` inside the sandbox
- [x] Reuses standard sandbox timeout configuration (16 hours) from `sandbox/main.py`
- [x] Defaults to Standard Sandboxes with burstable memory, supporting dynamic promotion to VM Sandboxes with `--vm`
- [x] Supports `--testing` mode staging secrets from `secrets_testing/<project-name>/` and prefixing the Modal app name with `test-` per ADR 0029
- [x] Provides a dedicated in-sandbox factory entrypoint script that clones the target repository and checks out `factory/<feature>`
- [x] Preserves `GH_TOKEN` in the assembly line environment for git branch pushing
- [x] Decrypts OpenCode credentials ephemerally into `/root/.config/opencode/opencode.env`
- [x] Streams live execution logs from the running sandbox and exits cleanly with the pipeline's exit code

## Comments

Implemented the Modal factory sandbox spawner and dedicated in-sandbox container entrypoint across four modular seams following TDD:

1. **Dedicated In-Sandbox Factory Entrypoint (`shared/factory_entrypoint.sh`)**:
   - Parses `--feature <slug>`, optional `--issue <id>`, and optional `--model <model>` with positional fallback.
   - Decrypts OpenCode credentials ephemerally from `/root/secrets/opencode.env` into `/root/.config/opencode/opencode.env` (0600) using SOPS and `AGE_PRIVATE_KEY` from `share0`, exporting `OPENCODE_GO_API_KEY` and `OPENCODE_API_KEY`.
   - Decrypts target repository fetch secret (`/root/secrets/repo/fetch.env`), extracts `GH_REPO` and `GH_TOKEN`, and clones the target repository to `/root/<repo-name>`.
   - Checks out `factory/<feature>` branch, tracking `origin/factory/<feature>` if present or branching from HEAD.
   - Decrypts mapped repository environment secrets from `env.map` into the cloned repository.
   - Scrubs staging directories and temporary SOPS state while strictly preserving `GH_TOKEN` in the environment for git branch pushing.
   - Automatically ensures target repository and factory harness dependencies are installed.
   - Invokes `/root/factory/pipeline.ts` with `--workspace`, `--feature`, `--issue`, and `--model`, exiting cleanly with the pipeline's exact return code.
   - Tested in `tests/test_entrypoint.py`.

2. **Image Builder & Secrets Resolver (`factory/spawner.py`)**:
   - `resolve_secrets_dir`: Validates `fetch.env` existence in `secrets/<project>/` or `secrets_testing/<project>/`.
   - `get_factory_app_name`: Prefixes app names with `test-` when `--testing` is set per ADR 0029.
   - `build_factory_image`: Built on the unified base image (`shared.image.base_image`), stages OpenCode secret, factory entrypoint script, target project secrets, and mounts the TypeScript harness (`sandbox/factory/`) to `/root/factory/`.

3. **Modal Sandbox Spawner & Execution Streamer (`factory/spawner.py`)**:
   - `create_factory_sandbox` / `spawn_factory_sandbox`: Creates an ephemeral sandbox with 16-hour timeout (`FACTORY_TIMEOUT_SECS`) and 4-hour idle timeout (`FACTORY_IDLE_TIMEOUT_SECS`), burstable memory `(128, 16384)` by default, dynamically promoted to VM Sandbox (`memory_gb * 1024` MiB and `experimental_options={"vm_runtime": True}`) with `--vm`.
   - Mounts organizational secret `share0` for SOPS bootstrap.
   - `stream_sandbox_logs`: Concurrently streams `sandbox.stdout` and `sandbox.stderr` in real time, waits for container completion, and propagates the exit code.
   - `run_factory_sandbox`: End-to-end spawner and streaming execution helper.
   - Tested in `tests/test_spawner.py`.

4. **Orchestrator Interface & Public API (`factory/orchestrator.py` & `factory/__init__.py`)**:
   - Provides `dispatch_job` for orchestrating jobs from Python.
   - Re-exports configuration classes, constants, and runner functions at the top-level package.
   - Tested in `tests/test_orchestrator.py`.

5. **Test Coverage & Quality**:
   - 18 passing Python unit tests (`pytest tests/` / `python -m unittest discover tests`).
   - 100% clean typecheck (`mypy --explicit-package-bases factory/ shared/image.py tests/`).
   - All 81 TypeScript unit/integration tests passing (`pnpm --prefix sandbox/factory test`).
