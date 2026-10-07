# 05: Modal Factory Orchestrator and Ephemeral Sandbox Spawner

**What to build:** A serverless Modal application that acts as the cloud orchestrator for the software factory. When given a target repository secret and feature/ticket parameters, it provisions an ephemeral Modal Sandbox (Standard Sandbox by default, dynamically promoted to VM Sandbox when Docker daemon or swap is required). It mounts organization secrets (`share0` for SOPS decryption), decrypts repository fetch credentials ephemerally, stages the factory assembly line harness, clones the target repository into the sandbox, and executes the assembly line while streaming execution logs back to the caller.

**Blocked by:** 04: Assembly Line Pipeline and Self-Correction Loop

**Status:** ready-for-agent

- [ ] Implements the serverless Modal application for the Factory Orchestrator
- [ ] Provisions ephemeral Modal Sandboxes using the unified base image
- [ ] Defaults to Standard Sandboxes with burstable memory, supporting dynamic promotion to VM Sandboxes
- [ ] Ephemerally mounts `share0` and decrypts repository fetch credentials and OpenCode keys during boot
- [ ] Clones the target repository and invokes the in-sandbox assembly line pipeline
- [ ] Streams live execution logs from the running sandbox back to the caller
- [ ] Terminates the ephemeral sandbox cleanly upon pipeline completion or error
