# Central Environment Store and Host-Side Secret Injection

**Status**: Accepted (Amends [ADR 0077](0077-centralized-org-credentials-and-in-repo-secrets.md) and [ADR 0092](0092-consolidate-secrets-to-single-dotenv-and-retire-legacy-staging.md))

We establish a dedicated private GitHub repository (`env-store` under `${GH_ORG_NAME}`) as the centralized, SOPS-encrypted secrets vault for all public and private target repositories, shift secret decryption entirely host-side in `SandboxLauncher` using native `modal.Secret.from_dict()`, and introduce zero-clone developer CLI tools (`push-repo-env` and `pull-repo-env`) to eliminate in-repo encrypted files and SOPS metadata from open-source codebases.

## Context

Under [ADR 0077](0077-centralized-org-credentials-and-in-repo-secrets.md), target repositories stored encrypted environment files directly in version control within `<repo>/.secrets/` accompanied by an `env.map` manifest. While effective for internal private repositories, this in-repo model introduces significant friction for open-source software (OSS) projects:
1. **Security Scanner False Alarms**: Automated secret scanners (GitGuardian, TruffleHog, GitHub Secret Scanning) regularly trigger on high-entropy SOPS ciphertexts committed to public repositories.
2. **Confusing Contributor Experience**: Open-source contributors expect a clean repository with a `.env.example` template where external contributors supply their own credentials ("BYOK"). An encrypted `.secrets/` directory clutters public trees with inaccessible blobs.
3. **Sandbox Key Exposure**: In-container decryption during `shared/startup.sh` required temporarily staging `AGE_PRIVATE_KEY` inside the sandbox before scrubbing, creating unnecessary risk if container initialization was interrupted or inspected by untrusted code.
4. **Permanent Public Git History Risk**: If an Age private key were ever compromised, all historical encrypted secrets stored across public Git logs would be retroactively readable.

## Decisions

1. **Central Environment Store (`env-store`)**:
   - Create a dedicated private repository at `github.com/${GH_ORG_NAME}/env-store` to house all target repository environment configurations.
   - Organize secrets by project directory: `env-store/<repo-name>/default.env` (SOPS-encrypted with the organization's Age public key) and an optional `env.map` for monorepo destination mapping (e.g. `web.env=apps/web/.env`).
   - Authenticate access using the existing `GH_TOKEN` configured in the factory `.env`.

2. **Host-Side Decryption & Isolation (`SandboxLauncher`)**:
   - Shift decryption completely out of the sandbox container and into `SandboxLauncher` on the host/control plane.
   - When launching for target repository `<repo>`, `SandboxLauncher`:
     1. Fetches the encrypted secret file(s) directly from `env-store` using the GitHub Contents REST API (`api.github.com/repos/${GH_ORG_NAME}/env-store/contents/<repo>/`).
     2. Decrypts the secret in host memory using `AGE_PRIVATE_KEY` via `sops decrypt`.
     3. Injects decrypted variables directly into `modal.Sandbox.create(..., secrets=[modal.Secret.from_dict(...)])`.
   - `AGE_PRIVATE_KEY` and `env-store` access tokens never enter the container filesystem or process environment.

3. **In-Container Filesystem Materialization**:
   - Because application toolchains (e.g., Next.js, Vite, Prisma, Docker Compose) explicitly read a physical `.env` file on disk, `shared/startup.sh` materializes the injected environment variables as a local file at `/root/<repo>/.env` (and any mapped subpaths) with restricted `0600` permissions.

4. **Zero-Clone Developer CLI Tooling (`push-repo-env` and `pull-repo-env`)**:
   - Provide `scripts/push_repo_env.py` (aliased as `push-repo-env`):
     - Requires only the organization's public Age recipient key (`age1zwr6flwy...`), allowing any team member or contributor to encrypt and push secrets without possessing the private key.
     - Auto-detects the repository name from `git remote get-url origin`.
     - Automatically verifies and guards `.gitignore` to prevent accidental commits of local plaintext `.env` files.
     - Commits the encrypted file directly to `env-store` via the GitHub Contents API without requiring a local clone of `env-store`.
   - Provide `scripts/pull_repo_env.py` (aliased as `pull-repo-env`):
     - Enables authorized developers holding `AGE_PRIVATE_KEY` to retrieve and decrypt a project's `.env` locally when onboarding a new workstation.

5. **Transitional Backward Compatibility**:
   - `SandboxLauncher` checks `env-store` first. If no secrets are found in `env-store`, it falls back to inspecting the legacy target repository `.secrets/env.map` and logs a deprecation warning, ensuring zero downtime for unmigrated repositories.

## Consequences

- Public open-source repositories remain 100% clean, containing only standard `.env.example` templates and code.
- Developers configure project secrets once via `push-repo-env`; all subsequent sandbox launches across any machine automatically pull and inject secrets.
- `AGE_PRIVATE_KEY` is fully eliminated from the container sandbox environment, hardening container isolation.
- `sops` can eventually be pruned from the Shared Base Image once all legacy in-repo repositories are migrated.
- All code modules remain strictly within the Universal File Line Budget (<= 500 physical lines).
