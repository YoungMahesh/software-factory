# Centralized Organization Credentials and In-Repository Encrypted Environment Mapping

## Problem Statement

Currently, repository access credentials and environment configurations are fragmented across the codebase. Adding or developing a new repository requires managing local directories under `secrets/<repo>/` containing distinct `fetch.env` tokens, while multi-application environment files (`.env`, `.env.local`) require host-managed `secrets/<repo>/env.map` manifests staged into the container image. Furthermore, an experimental `secrets_org/` convention was introduced with separate `token` and `permissions.yml` files per organization.

This creates several operational problems:
1. **Host-Side Directory Sprawl**: Every repository requires dedicated local directories and manual encryption setup on the developer machine before a sandbox can be launched.
2. **Decoupled Environment Configurations**: Monorepo `.env` file locations (`env.map`) live on the launcher host instead of version-controlled alongside the application code, preventing branch-specific environment updates or seamless PR workflows.
3. **Token Duplication and Management Overhead**: Fine-grained personal access tokens must be individually configured and duplicated across multiple `fetch.env` files instead of relying on a centralized organization-level credential.

## Solution

1. **Centralized Organization Credentials (`secrets/github-orgs.env`)**:
   - Retire the `secrets_org/` directory completely.
   - Introduce a single, SOPS-encrypted configuration file `secrets/github-orgs.env` storing fine-grained organization tokens (e.g. `sFactory0`).
   - The sandbox runner extracts the token matching the target repository's GitHub organization during sandbox initialization.
2. **In-Repository Encrypted Environment Secrets (`.secrets/`)**:
   - Retire all repository-specific directories in `secrets/` (`intrifund`, `neon`, `repo-horizon`, `software-factory`).
   - Move encrypted `.env` files and the repository environment mapping manifest (`env.map`) directly into each repository root under `.secrets/`.
   - The container startup script automatically inspects the cloned repository for `.secrets/env.map`, decrypts all mapped environment files into their destination paths using the Shared Workspace Secret (`share0`), and applies strict file permissions (`0600`).
3. **Repository Migration**:
   - Clone existing source repositories from `anveshak71` and push them as private repositories under the `sFactory0` GitHub organization, equipped with their `.secrets/` directory and `env.map`.

## User Stories

1. As a developer, I want all organization GitHub personal access tokens stored in a single encrypted file `secrets/github-orgs.env`, so that I do not have to maintain separate token files and directories per repository or organization.
2. As a developer, I want to eliminate all project-specific subdirectories inside `secrets/`, so that the local repository root remains clean and contains only shared host configurations.
3. As a developer, I want repository environment files (`.env`) and their mapping manifest (`env.map`) stored directly inside each target repository, so that environment layouts are version-controlled alongside application code.
4. As a developer, I want `.secrets/env.map` to define relative destination paths inside monorepos, so that multiple subpackages receive their decrypted `.env` files automatically upon sandbox launch.
5. As a developer, I want to migrate `software-factory`, `repo-horizon`, `intrifund`, and `neon` to the `sFactory0` organization, so that all active development repositories are centralized under our dedicated organization.
6. As a sandbox runner, I want to determine the target repository's organization from its repository name and select the correct token from `secrets/github-orgs.env`, so that authentication is seamless.
7. As a sandbox runner, I want `secrets/github-orgs.env` to support multiple GitHub organizations simultaneously, so that future organizations can be added without altering the runner architecture.
8. As a developer launching a sandbox, I want the container bootstrap routine to decrypt in-repository secrets using `AGE_PRIVATE_KEY` from the Shared Workspace Secret (`share0`), so that no extra decryption keys need to be mounted.
9. As a security-conscious engineer, I want all decrypted `.env` files in the repository to have restrictive permissions (`0600`), so that unauthorized system processes cannot read sensitive configuration.
10. As a developer working on a repository without environment secrets (e.g. `neon`), I want the container bootstrap routine to proceed cleanly when `.secrets/env.map` is absent, so that unnecessary configuration is not mandatory.
11. As a developer pushing changes to feature branches, I want environment changes to be reviewable in pull requests without altering global launcher files, so that feature branches can safely test new environment variable configurations.
12. As a developer inspecting repository history, I want all `.secrets/*.env` files committed to Git to be SOPS-encrypted with Age, so that credentials are never exposed in plaintext in source control.
13. As a developer launching a sandbox, I want the startup routine to purge intermediate token staging files before handing over the terminal, so that credentials do not linger on the filesystem.
14. As an automated test runner, I want sandbox creation to succeed without requiring legacy `fetch.env` files, so that automated verification scripts run reliably with the centralized token.

## Implementation Decisions

- **Organization Token Store (`secrets/github-orgs.env`)**:
  - Format: Standard SOPS-encrypted key-value environment file.
  - Variable naming convention: `<ORGANIZATION>_GH_TOKEN` (uppercased organization name, e.g. `SFACTORY0_GH_TOKEN`), supporting multi-organization token resolution.
  - Staging: Runner decrypts or stages `secrets/github-orgs.env` so that the target container entrypoint can read the organization PAT into memory as `GH_TOKEN`.
- **Directory Retirement**:
  - `secrets_org/` is completely deleted.
  - All project subdirectories in `secrets/` (`secrets/software-factory/`, `secrets/repo-horizon/`, `secrets/intrifund/`, `secrets/neon/`) are deleted.
  - Global shared configurations in `secrets/` (`antigravity.env`, `antigravity-oauth-token*.json`, `cloudflare.env`, `modal.toml`, `opencode.env`) are retained.
- **In-Repository Secret Manifest (`.secrets/env.map`)**:
  - Located at `<repo-root>/.secrets/env.map`.
  - Format: `<source_file>=<repo_relative_dest_path>`, ignoring empty lines and `#` comments.
  - Example shape:
    ```properties
    web.env=apps/web/.env
    mobile.env=apps/mobile/.env
    ```
- **Container Bootstrap Sequence (`startup.sh`)**:
  - Extracts the organization token from the decrypted credential payload.
  - Clones the target repository `sFactory0/<repo>` over HTTPS.
  - Checks for `$TARGET_DIR/.secrets/env.map`.
  - For each mapped pair, runs SOPS decryption against `$TARGET_DIR/.secrets/<source_file>`, writes to `$TARGET_DIR/<repo_relative_dest_path>`, and sets file permissions to `0600`.
  - Scrubs `AGE_PRIVATE_KEY` and temporary staging directories before handing over session control.
- **Architectural Documentation**:
  - Author a new ADR documenting the consolidation into `secrets/github-orgs.env` and in-repository `.secrets/env.map`, superseding ADR 0019 (local repository `env.map`) and ADR 0031 (`secrets_org/`).

## Testing Decisions

- **What makes a good test**: Tests must verify the external behavioral contracts of the launcher and container bootstrap:
  - Correct extraction of the organization PAT from `secrets/github-orgs.env`.
  - Successful authenticated repository clone.
  - Correct materialization and permissions (`0600`) of mapped `.env` files in target paths.
  - Clean container initialization when `.secrets/env.map` is absent.
  - No secret leakage in container logs or persistent disk files.
- **Modules Tested**:
  - Sandbox Launcher: CLI parameter parsing, target organization resolution, and container secret staging.
  - Container Startup Script: Token extraction, Git checkout, and in-repo `.secrets/` decryption loop.
- **Prior Art**:
  - Live sandbox integration tests in `scripts/` (e.g. `test_standard_sandbox.py`, `test_vm_sandbox.py`) and ADR 0019 test cases.

## Out of Scope

- Storing plaintext secrets in GitHub repository variables or GitHub action secrets.
- Automatic rotation or generation of GitHub fine-grained PATs.
- Automatic migration of legacy branches or pull requests on `anveshak71` that are not targeted for the `sFactory0` cutover.

## Further Notes

- `AGE_PRIVATE_KEY` continues to be securely provided by the Modal secret `share0`.
- All files placed in `.secrets/` inside repositories must remain strictly encrypted using SOPS with the project Age recipient public key before committing.
