# Antigravity ACP Credential Preservation in Filesystem Snapshots

**Status**: Accepted (Amends [ADR 0024](0024-filesystem-snapshots-in-unified-sandbox-runner.md) and [ADR 0035](0035-multi-account-antigravity-provider-instances-in-t3-code.md))

We updated the Antigravity ACP provider configuration routines in `scripts/setup.sh` and `shared/startup.sh` to preserve pre-existing, valid `acp_token.json` credentials and `project_id` across filesystem snapshot resume cycles.

## Context

Under [ADR 0024](0024-filesystem-snapshots-in-unified-sandbox-runner.md), sandboxes launched from filesystem snapshots run with `RESUME_SNAPSHOT=1`, bypassing git clone, package installation, and SOPS secret decryption (`secrets/antigravity.env`).

Under [ADR 0035](0035-multi-account-antigravity-provider-instances-in-t3-code.md), sandboxes pre-authenticate multiple Antigravity provider instances (`antigravity`, `antigravity-anv`, and `antigravity-mgh`) by reading cached refresh tokens and synthesizing `acp_token.json` files for each instance. However, both `shared/startup.sh` and `scripts/setup.sh` fell back to `"dummy-client-id.apps.googleusercontent.com"` and `"dummy-client-secret"` if `ANTIGRAVITY_CLIENT_ID` was not present in the environment, and unconditionally overwrote existing `acp_token.json` files.

When resuming a sandbox from a snapshot:
1. `RESUME_SNAPSHOT=1` caused `antigravity.env` decryption to be skipped, so `ANTIGRAVITY_CLIENT_ID` and `ANTIGRAVITY_CLIENT_SECRET` were unset.
2. `shared/startup.sh` unconditionally generated a new `acp_token.json` populated with the dummy client ID and secret, clobbering the authenticated OAuth tokens preserved in the snapshot and stripping `project_id: "aicode-consumers"`.
3. T3 Code spawned `agy_acp_server.par`, which failed token refresh against Google OAuth due to the dummy client ID and emitted an interactive authorization URL. Because headless T3 provider sessions do not run interactive OAuth flows, T3 raised `AcpTransportError: ACP transport operation failed: Sign in to Antigravity in Settings before you continue`, failing session startup.

## Decision

1. **Non-Destructive Credential Discovery**:
   - Before synthesizing `acp_token.json`, inspect all target instance directories and `~/.gemini/antigravity-acp` for an existing `acp_token.json`.
   - If an existing file contains a valid non-dummy `client_id`, preserve the existing `client_id`, `client_secret`, and `project_id`.
2. **Precedence Hierarchy**:
   - Explicit environment variables (`ANTIGRAVITY_CLIENT_ID` / `GOOGLE_CLIENT_ID` and `ANTIGRAVITY_CLIENT_SECRET` / `GOOGLE_CLIENT_SECRET`) take highest precedence.
   - Pre-existing valid credentials on disk take second precedence (preserving snapshot state).
   - Placeholder strings (`dummy-client-id.apps.googleusercontent.com`) are only used as a last resort when neither environment variables nor existing files provide valid client credentials.
3. **Project ID Retention**:
   - Retain `project_id` (e.g. `aicode-consumers`) from the pre-existing `acp_token.json` or `ANTIGRAVITY_PROJECT_ID` environment variable.

## Consequences

- Resuming a sandbox from a filesystem snapshot preserves all authenticated Antigravity provider accounts without requiring interactive re-login or external SOPS keys.
- T3 Code provider sessions and orchestrator delegate tasks start cleanly immediately following snapshot resume.
- Both `scripts/setup.sh` and `shared/startup.sh` maintain identical fallback and preservation semantics.
- All modified files remain strictly within the 500-line budget.
