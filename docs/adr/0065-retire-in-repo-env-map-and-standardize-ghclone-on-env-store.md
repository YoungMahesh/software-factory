# Retire In-Repo env.map Fallback and Standardize ghclone on Central Environment Store

**Status**: Accepted (Amends [ADR 0038](0038-centralized-org-credentials-and-in-repo-secrets.md), [ADR 0050](0050-developer-cli-tooling-precedence-and-dot-directory-resolution.md), and [ADR 0057](0057-central-env-store-and-host-side-secret-injection.md))

We completely remove legacy in-repo `.secrets/env.map` fallback decryption from `shared/startup.sh`, standardize the `ghclone` CLI helper to fetch and decrypt environment variables directly from `env-store` via `pull-repo-env`, and retire legacy `decrypt-repo-env` and `encrypt-repo-env` scripts from the shared image.

## Context

Under [ADR 0057](0057-central-env-store-and-host-side-secret-injection.md), the Central Environment Store (`env-store`) was established as the authoritative secrets vault, shifting target repository secret decryption host-side in `SandboxLauncher` and injecting credentials into Modal containers via `modal.Secret.from_dict()` and `VAULT_DOTENV_B64`.

However, several legacy seams persisted:
1. **Transitional Fallback in Sandbox Startup**: `shared/startup.sh` still contained an in-container SOPS decryption loop inspecting `$TARGET_DIR/.secrets/env.map`.
2. **`ghclone` Tied to In-Repo Manifests**: The `ghclone` CLI helper checked exclusively for `${TARGET_DIR}/.secrets/env.map` and invoked `decrypt-repo-env`, meaning repositories using `env-store` did not have their `.env` files populated upon `ghclone`.
3. **Legacy CLI Utilities Staged in Container Images**: Stale scripts `decrypt-repo-env` and `encrypt-repo-env` remained symlinked and maintained across `shared/image.py` and `shared/startup.sh`, despite being superseded by `pull-repo-env` and `push-repo-env`.

## Decisions

1. **Complete Removal of In-Repo `.secrets/env.map` Decryption**:
   - Remove the in-container SOPS decryption loop from `shared/startup.sh`.
   - Sandbox provisioning relies exclusively on `VAULT_DOTENV_B64` injected from `env-store`.
   - Any legacy `.secrets/env.map` files present in target repositories are silently ignored without warnings or errors.

2. **Standardize `ghclone` on `env-store`**:
   - Update `scripts/ghclone` to delegate post-clone decryption to `pull-repo-env`:
     ```bash
     pull-repo-env --optional -r "$REPO_NAME" -o "$TARGET_ORG" -d "${TARGET_DIR}/.env"
     ```
   - Passing `--no-decrypt` or `--skip-decrypt` to `ghclone` skips secret retrieval.

3. **Graceful Non-Fatal Secret Retrieval (`--optional`)**:
   - Add an `--optional` (alias `--ignore-missing`) flag to `scripts/pull_repo_env.py`.
   - When enabled, `pull-repo-env` exits with status `0` and prints an informational notice if:
     - The repository has no secrets configured in `env-store` (HTTP 404).
     - Decryption cannot proceed due to missing `AGE_PRIVATE_KEY` / `SOPS_AGE_KEY` (e.g. running inside a standard sandbox without `ENABLE_SOPS=1`).
     - GitHub credentials are not present.

4. **Retirement of Legacy CLI Utilities**:
   - Completely delete `scripts/decrypt_repo_env.py`, `scripts/encrypt_repo_env.py`, their symlinks, and their test suites (`tests/test_decrypt_repo_env.py`, `tests/test_encrypt_repo_env.py`).
   - Replace their entries in `shared/image.py` and `shared/startup.sh` with `push-repo-env` and `pull-repo-env`.

5. **Documentation & Glossary Alignment**:
   - Update `GLOSSARY.md` (Developer CLI Tooling Precedence) to list `push-repo-env` and `pull-repo-env`.
   - Update `docs/architecture/secrets.md` to document the unified `env-store` workflow for both sandbox provisioning and `ghclone`.

## Consequences

- **Single Source of Truth**: All target repository secrets live exclusively in `github.com/${GH_ORG_NAME}/env-store`.
- **Consistent DX**: Developers cloning via `ghclone` (locally or inside sandboxes) automatically pull and decrypt their `.env` file from `env-store`.
- **Public Repo Safety**: Public open-source codebases require no `.secrets/` directory or SOPS metadata in version control.
- **Clean Tooling**: Stale `decrypt-repo-env` and `encrypt-repo-env` utilities are removed from the image surface.
