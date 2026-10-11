# 02: Studio Prompt Endpoint Sandbox Reuse & Auto-Provisioning

**What to build:** Route Factory Studio chat prompts to the active Unified Studio Sandbox instead of spawning new containers. When chatting against a repository with no active preview, automatically provision the Unified Studio Sandbox first and execute the prompt within that single container, transitioning branches in place.

**Blocked by:** 01: Container Entrypoint Supervisor & In-Sandbox Registry Execution

**Status:** resolved

- [x] Submitting a prompt via the Factory Studio prompt endpoint for a repository with an active running sandbox reuses that container, delegating execution via in-sandbox process execution.
- [x] Submitting a prompt for a repository with no active container automatically provisions a Unified Studio Sandbox, waits for the dev server to start serving on port 3000, and executes the prompt within that container.
- [x] When starting a prompt on a newly synthesized feature or milestone, in-sandbox execution checks out or creates the target branch (`factory/<feature>`) in place within the working directory without container restarts.
- [x] The prompt response payload returns the unified sandbox state and live preview tunnel URL (`https://<sandbox-id>-3000.modal.host`).
- [x] In Studio mode, the Deterministic Verifier runs tests and typechecks without triggering full production builds that collide with the active dev server.
- [x] Integration tests verify prompt dispatch against active containers, implicit auto-provisioning when inactive, and in-place branch transition behavior.
