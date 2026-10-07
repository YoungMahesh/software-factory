# 05: Modal Factory Sandbox Spawner and Container Entrypoint

**What to build:** The Modal sandbox provisioning engine and container entrypoint for the software factory. When given a target repository secret name (`secrets/<project-name>`), feature slug, and optional ticket ID, it provisions an ephemeral Modal Sandbox (Standard Sandbox by default, dynamically promoted to VM Sandbox when `--vm` is requested) with a 16-hour timeout. It mounts organization secrets (`share0` for SOPS bootstrap), stages project secrets (`secrets/<project-name>/`), and mounts the local factory harness (`sandbox/factory/`) into `/root/factory/`. Inside the container, a dedicated factory entrypoint decrypts fetch credentials, clones the target repository, checks out `factory/<feature>`, preserves `GH_TOKEN` for assembly line pushing, decrypts OpenCode credentials, and invokes the in-sandbox pipeline.

**Blocked by:** 04: Assembly Line Pipeline and Self-Correction Loop

**Status:** ready-for-agent

- [ ] Implements the Modal sandbox creation helper using `modal.Sandbox.create()` and the unified base image
- [ ] Mounts the local factory TypeScript harness (`sandbox/factory/`) to `/root/factory/` inside the sandbox
- [ ] Reuses standard sandbox timeout configuration (16 hours) from `sandbox/main.py`
- [ ] Defaults to Standard Sandboxes with burstable memory, supporting dynamic promotion to VM Sandboxes with `--vm`
- [ ] Provides a dedicated in-sandbox factory entrypoint script that clones the target repository and checks out `factory/<feature>`
- [ ] Preserves `GH_TOKEN` in the assembly line environment for git branch pushing
- [ ] Decrypts OpenCode credentials ephemerally into `/root/.config/opencode/opencode.env`
- [ ] Streams live execution logs from the running sandbox and exits cleanly with the pipeline's exit code
