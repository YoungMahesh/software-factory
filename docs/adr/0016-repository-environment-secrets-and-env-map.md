# Repository Environment Secrets and In-Sandbox Mapping (`env.map`)

Cloned applications—particularly monorepos—often require multiple repository environment files (`.env`, `.env.local`, etc.) positioned at specific paths across subpackages (e.g. `apps/web/.env`, `apps/mobile/.env`). Previously, the local repository secrets architecture (ADR 0003) only handled repository clone credentials via `secrets/<secret-name>/fetch.env`. We decided to introduce Repository Environment Secrets: co-located, SOPS-encrypted `.env` files stored under `secrets/<secret-name>/` and mapped to destination file paths in the cloned repository via an optional mapping manifest `secrets/<secret-name>/env.map`.

The sandbox launcher (`sandbox/main.py`) stages the entire `secrets/<secret-name>/` directory into the container image at `/root/secrets/repo/`. During container boot, `shared/startup.sh` extracts clone credentials from `fetch.env`, clones the repository, and parses `env.map` to decrypt each mapped secret into its target file path with restrictive permissions (`chmod 600`), immediately purging `/root/secrets/repo/` from disk before scrubbing `AGE_PRIVATE_KEY` from memory.

## Considered Options

- **Directory target mapping (`web.env=apps/web`)**: Mapping to target directories and inferring the file name as `.env`. Rejected because it creates ambiguity and prevents applications from configuring framework-specific environment filenames such as `.env.local`, `.env.production`, or `.env.staging`.
- **Embedding environment definitions in `fetch.env`**: Embedding multi-file environment contents into `fetch.env` variables. Rejected because it couples repository clone credentials with application runtime environment configurations and degrades readability and modular editing of separate project configs.
- **Host-side SOPS decryption and injection via Modal secrets**: Decrypting `.env` files on developer machines prior to container creation and injecting them as environment variables. Rejected because it requires host machines to possess `AGE_PRIVATE_KEY`, breaking decoupled runner execution (ADR 0003 and ADR 0003).
- **In-sandbox SOPS decryption via explicit `env.map`**: Baking encrypted environment files and their mapping manifest into `/root/secrets/repo/`, decrypting directly into the cloned repository during container boot using `share0`'s `AGE_PRIVATE_KEY`, and atomically cleaning up the staging directory before user session handoff. Accepted because it maintains end-to-end zero-leakage security, explicit destination paths, and friction-free monorepo support.

## Consequences

- `sandbox/main.py` stages `secrets/<secret-name>/` into `/root/secrets/repo/` in the container image via `image.add_local_dir`.
- `shared/startup.sh` reads `fetch.env` from `/root/secrets/repo/fetch.env` (with fallback to `/root/secrets/fetch.env` for backwards compatibility).
- If `env.map` is present, `shared/startup.sh` decrypts each mapped file into `$TARGET_DIR/<dest_path>` and applies `chmod 600`.
- Missing mapped source files or failed `sops decrypt` operations strictly terminate container startup with exit code 1 (fail-fast).
- `/root/secrets/repo/` is unconditionally scrubbed (`rm -rf`) immediately after processing.
- `env.map` is optional; repositories without environment mappings execute without changes.
