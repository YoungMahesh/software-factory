# Consolidate Control Plane, Vault, Configuration, and Presentation Seams

**Status**: Accepted (Amends [ADR 0040](0040-hosted-sandbox-control-plane-function.md), [ADR 0041](0041-automatic-ssh-config-registration-for-sandboxes.md), [ADR 0051](0051-control-plane-secret-staging-and-credential-validation.md), [ADR 0057](0057-central-env-store-and-host-side-secret-injection.md), [ADR 0078](0078-create-db-cli-for-db-host-postgres-connections.md), and [ADR 0079](0079-create-s3-cli-for-db-host-s3-object-storage.md)).

## Context

Across successive growth iterations of the software factory, four operational boundaries accumulated coupling, scattered file parsing, and wide parameter surfaces:

1. **`db-host` and `s3-host` Cross-Module Coupling**: `sandbox/s3_host.py` directly imported private transport functions (`call_mcp_tool`, `ensure_project`, `fetch_db_host_ca_cert`) from `sandbox/db_host.py`, coupling object storage provisioning directly to the database CLI module.
2. **Fragmented Vault Bundle Resolution**: Central Environment Store secret decryption, Git identity fetching, and base64 `.env` packaging were scattered between `sandbox/env_store.py`, `scripts/pull_repo_env.py`, and `sandbox/launcher.py`. In addition, `scripts/pull_repo_env.py` contained an inline production test inspection hack (`hasattr(..., "assert_called")`).
3. **Redundant Factory Configuration & .env File Parsing**: Ad-hoc line-by-line `.env` parsing loops existed independently in `sandbox/function.py`, `sandbox/main.py`, and `sandbox/config.py` for Web UI credentials (`WEB_UI_USERNAME`, `WEB_UI_PASSWORD`) and Modal secret extraction.
4. **Wide Presentation Surface & Uncoordinated SSH Registration**: `sandbox/formatting.py:print_access_info` exposed a 21-parameter signature. Callers in `sandbox/main.py` had to unpack response payloads manually and make separate, explicit calls to `append_ssh_config`.

## Decision

We consolidate these boundaries into four cohesive deep modules adhering to deep module principles and the repository's universal 500-line budget:

1. **`DbHostClient` (`sandbox/db_host_client.py`)**:
   - Encapsulates JSON-RPC over HTTP transport, Bearer token authentication, root CA certificate caching, and project scoping into a single reusable transport seam.
   - Refactored both `sandbox/db_host.py` and `sandbox/s3_host.py` to consume `DbHostClient`, completely eliminating cross-module imports between `s3_host` and `db_host`.

2. **`EnvStoreVault` and `VaultBundle` (`sandbox/env_store.py` & `sandbox/env_store_push.py`)**:
   - Introduced `VaultBundle` to encapsulate decrypted `.env` dictionary, raw text, base64 payload, and Git identity.
   - Added `resolve_sandbox_bundle()` to unify vault resolution for sandbox launches.
   - Extracted vault push/commit routines to `sandbox/env_store_push.py` to keep both modules safely within the 500-line file limit.
   - Eliminated the `hasattr(..., "assert_called")` production test hack in `scripts/pull_repo_env.py`.

3. **`FactoryConfiguration` (`sandbox/config.py`)**:
   - Centralized repository `.env` discovery across candidate search paths (`.env`, `.secrets/.env`, `secrets/.env`, and system paths).
   - Added `resolve_web_ui_credentials()` and `compile_control_plane_secrets()` in `sandbox/config.py`.
   - Refactored `sandbox/function.py` and `sandbox/main.py` to delegate Web UI credential and secret resolution to `FactoryConfiguration`, eliminating all duplicate ad-hoc parsing loops.

4. **`display_launch_summary` (`sandbox/formatting.py`)**:
   - Unified presentation seam that accepts either a domain `LaunchResponse` model or a serialized dictionary.
   - Automatically coordinates ANSI banner rendering, QR code generation, and atomic SSH client configuration appending (`append_ssh_config`).
   - Replaced multi-argument unpacking blocks in `sandbox/main.py` with concise `display_launch_summary` calls.

## Consequences

- **Universal Line Budgets**: All affected files remain strictly under 500 lines (`wc -l` verified by `tests/test_standards.py`).
- **Deep Seams**: Subsystems interact via high-level abstractions (`DbHostClient`, `EnvStoreVault`, `FactoryConfiguration`, `display_launch_summary`) without leaking internal protocols or formatting details.
- **Backward Compatibility**: All existing CLI flags, public function signatures, and test mocks are preserved without breaking changes.
