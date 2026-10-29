# 05: End-to-End Live Sandbox Verification and Architectural Decision Record

**What to build:**
Record ADR 0077 documenting the centralized organization credential store (`github-orgs.env`) and in-repo `.secrets/env.map` architecture. Run a live sandbox test against `sFactory0/software-factory` verifying that authentication, repository cloning, in-repo `.secrets/env.map` decryption, and security scrubbing function end-to-end.

**Blocked by:** 02: Provision sFactory0/software-factory on GitHub with In-Repo .secrets/ Manifest, 03: Migrate repo-horizon, intrifund, and neon to sFactory0 with In-Repo .secrets/, 04: Update Sandbox Runner and Startup for Centralized Org Tokens and In-Repo Secret Decryption

**Status:** completed

- [x] ADR 0077 is recorded under `docs/adr/0077-centralized-org-credentials-and-in-repo-secrets.md` noting the retirement of `secrets_org/` and `secrets/<project>/`.
- [x] Context glossary and documentation updated to reflect the new architecture.
- [x] Live sandbox verification launched via `modal run sandbox/main.py --project software-factory` succeeds against `sFactory0/software-factory`.
- [x] In-sandbox verification confirms mapped `.env` files are decrypted in the repository with `0600` permissions.
- [x] Staging secrets and keys are completely scrubbed upon container readiness.
