# Organization Credentials and Canonical Test Organization

**Status**: Accepted

To replace fragmented per-repository test secrets with scoped organization-level access, we decided to introduce Organization Credentials (`secrets_org/<org-name>/` containing a SOPS-encrypted `token` and `permissions.yml`), designate `software-factory-09-test` as the canonical Test Organization for automated verification and sandboxes, and retire the `secrets_testing/` directory.

## Considered Options

- **Retaining `secrets_testing/<repo>/fetch.env`**: Managing distinct SOPS-encrypted tokens and repository URLs per test target. Rejected because adding new test fixtures required issuing individual PATs and encrypted `fetch.env` files, creating maintenance friction and token sprawl.
- **Dynamic In-Memory Synthesis of `fetch.env` on Host**: Generating ephemeral `fetch.env` files on the host dispatcher before sandbox launch. Rejected because it exposes decrypted tokens or creates temporary artifacts on the host filesystem rather than preserving in-sandbox SOPS decryption via `share0`.
- **Organization Credentials (`secrets_org/`) with Sandbox-Native Token Staging**: Accepted because an organization fine-grained PAT provides unified access across member repositories, isolates test operations within a dedicated GitHub organization (`software-factory-09-test`), and allows container entrypoints to decrypt `/root/secrets/org/token` natively into memory before scrubbing it from disk.

## Consequences

- All test repositories are housed under the GitHub organization `software-factory-09-test` (`https://github.com/software-factory-09-test/<repo>`).
- Organization credentials live under `secrets_org/<org-name>/` with encrypted `token` and descriptive `permissions.yml`.
- `secrets_testing/` is eliminated from version control.
- CLI runners (`factory/run.py` and `sandbox/main.py`) resolve `--testing --project <repo>` to `software-factory-09-test/<repo>` and accept explicit `<org>/<repo>` path syntax, passing the target repo via `GH_REPO` container environment variable and mounting `/root/secrets/org/token`.
- Container startup scripts (`startup.sh` and `factory_entrypoint.sh`) support organization token authentication alongside legacy repository fetch secrets.
