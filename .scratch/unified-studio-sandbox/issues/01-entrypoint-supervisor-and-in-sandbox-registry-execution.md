# 01: Container Entrypoint Supervisor & In-Sandbox Registry Execution

**What to build:** Persist decrypted credentials inside the container environment and supervise the background development server, while enabling the job registry to execute multi-agent assembly line tasks directly inside the active container via in-sandbox process execution (`sandbox.exec`), streaming logs to the agent event stream and emitting a preview refresh event upon completion.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Container bootstrap writes decrypted organization/repository tokens and LLM credentials to a protected container-local environment file (`/root/.factory.env`, mode 0600) so subsequent subshell processes inherit authenticated access.
- [ ] Container entrypoint wraps the background development server (`pnpm dev --port 3000 --host 0.0.0.0`) in a resilient auto-restart supervisor loop that automatically recovers from transient syntax or bundler errors during code generation.
- [ ] The job registry detects when a running container is associated with the target repository and invokes the assembly line pipeline inside that container using `sandbox.exec()` instead of spawning a new container.
- [ ] In-sandbox process execution sources the protected container environment file before executing the pipeline harness.
- [ ] Standard output and standard error from in-sandbox execution are captured in real time and broadcast across the agent event stream.
- [ ] Upon successful completion of an in-sandbox pipeline run, the registry broadcasts a `preview_refresh` event to signal preview resynchronization.
- [ ] Unit tests verify container entrypoint environment persistence, supervisor loop behavior, and registry execution delegation to active sandboxes.
