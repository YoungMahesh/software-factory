# 04: In-Sandbox Dev Server Keep-Alive Daemon

**What to build:** The software factory container entrypoint and sandbox configuration keep the sandbox alive after the assembly line verification and review stages pass, running the target application's TanStack Start dev server (`pnpm dev --port 3000 --host 0.0.0.0`) in the background so that the live website remains continuously accessible for interactive preview via Cloudflare Tunnel at `https://3000.mahesh0.dev` until terminated or timed out.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] Sandbox entrypoint detects when dev preview mode is enabled and successfully launches `pnpm dev --port 3000 --host 0.0.0.0` following verification passes.
- [x] Container remains in an active serving keep-alive state instead of terminating immediately after pipeline completion.
- [x] Dev server binds properly to port 3000 inside the container, routing out through Cloudflare Tunnel ingress at `https://3000.mahesh0.dev`.
- [x] Emergency cancellation via `modal.Sandbox.terminate()` shuts down the dev server and cleans up resources immediately.
- [x] Automated tests verify that post-verification dev server execution logic triggers correctly and supports idle keep-alive.

## Answer

Resolved by implementing the in-sandbox dev server keep-alive daemon and Cloudflare Tunnel preview ingress:

1. **Dedicated Container Entrypoint Keep-Alive Daemon (`shared/factory_entrypoint.sh`)**:
   - Added `--dev` / `--preview` argument parsing and environment variable detection (`DEV_PREVIEW=1` / `ENABLE_DEV=1`).
   - Configured Cloudflare Tunnel bootstrap and background port watcher daemon (`cloudflared-port-watcher` monitoring port 3000) during container initialization before temporary SOPS credentials and age keys are scrubbed.
   - When the in-container assembly line pipeline succeeds (`EXIT_CODE=0`) and dev preview is enabled, enters Step 10: launches `pnpm dev --port 3000 --host 0.0.0.0` in the background with PID tracking.
   - Maintains the container in an active serving keep-alive state via `wait "$DEV_PID"` instead of exiting immediately.
   - Configured clean process shutdown and signal traps (`SIGTERM`, `SIGINT`, `SIGHUP`) to gracefully terminate the dev server process group when cancelled or terminated.
   - Ensured pipeline failures (`EXIT_CODE != 0`) halt immediately and do not start the dev server.
2. **Modal Sandbox Spawner & Orchestrator Configuration (`factory/spawner.py`, `factory/orchestrator.py`, `factory/run.py`)**:
   - Added `dev: bool = False` to `FactorySpawnConfig`.
   - In `create_factory_sandbox`, when `config.dev` is enabled, passes `--dev` to `entrypoint_args` and sets `DEV_PREVIEW="1"`, `ENABLE_CLOUDFLARE="1"`, and `PORT="3000"` in the container environment.
   - Updated `dispatch_job` in `factory/orchestrator.py` to accept `dev: bool = False`.
   - Added `--dev` / `--preview` CLI options to `factory/run.py` allowing developers to launch dev preview keep-alive sandboxes from the command line.
3. **Job Registry & UI Endpoint Integration (`factory/ui/registry.py`, `factory/ui/app.py`)**:
   - Added `SERVING = "SERVING"` to `JobStage` and regular expression pattern detecting active keep-alive serving state in log streams.
   - Added `dev` and `preview_url` fields to `FactoryJob` and `create_job` (defaulting to `https://3000.mahesh0.dev` when `dev=True`).
   - In `cancel_job`, emergency cancellation triggers `sandbox.terminate()`, instantly halting active dev server sandboxes and transitioning job status to `CANCELLED`.
   - Updated `StudioPromptRequest` / `POST /api/studio/prompt` to automatically provision jobs with `dev=True` and return `preview_url: "https://3000.mahesh0.dev"`.
   - Updated `LaunchJobRequest` / `POST /api/jobs` to support opt-in `dev` flag.
4. **Automated Unit & Integration Tests (`tests/test_entrypoint.py`, `tests/test_spawner.py`, `tests/test_orchestrator.py`, `tests/test_run.py`, `tests/test_ui.py`)**:
   - Verified that dev preview flag and usage help work correctly.
   - Verified that dev server is skipped when dev preview is disabled or when pipeline fails.
   - Verified that dev server starts `pnpm dev --port 3000 --host 0.0.0.0`, maintains active serving keep-alive state, and terminates cleanly upon SIGTERM.
   - Verified Cloudflare Tunnel service and port watcher configuration in dev mode.
   - Verified spawner configuration, CLI dispatcher flags, `JobStage.SERVING` detection, and emergency cancellation via `sandbox.terminate()`.
