# Shared Workspace Secret (share0) for SOPS Age Key

Previously, `AGE_PRIVATE_KEY` was expected inside each repository's `--secret-collection`, duplicating the master Age private key across multiple secret collections and coupling repository cloning credentials with organizational encryption keys. We decided to decouple secret resolution: repository secret collections passed via `--secret-collection` provide only repository-scoped variables (`GH_REPO`, `GH_TOKEN`, `DOTENV_PRIVATE_KEY`), while a dedicated Modal secret collection named `share0` provides shared workspace credentials, specifically `AGE_PRIVATE_KEY`. Sandbox runners conditionally mount `modal.Secret.from_name("share0")` whenever credentials decryption is requested (`--agy`, `--modal`, or `--opencode`).

## Considered Options

- **Require `AGE_PRIVATE_KEY` in every repository secret collection**: Continue expecting each repository's Modal secret collection to contain `AGE_PRIVATE_KEY`. Rejected because it creates operational overhead and key duplication across dozens of repository secret collections.
- **Unconditionally mount `share0` across all sandboxes**: Mount `modal.Secret.from_name("share0")` on every sandbox launch alongside `--secret-collection`. Rejected because bare sandbox runs (which only clone and run public or basic repos without agent/tooling credentials) should not fail if `share0` is absent from the Modal workspace.
- **Configurable CLI secret flag `--shared-secret`**: Add an optional CLI flag defaulting to `"share0"`. Rejected to keep CLI invocation clean and concise, standardizing on `"share0"` as the workspace convention.
- **Decoupled conditional mounting of `share0`**: Define `SHARED_SECRET_NAME = "share0"` in `shared/image.py` and conditionally append `modal.Secret.from_name(SHARED_SECRET_NAME)` to `sandbox_secrets` when `--agy`, `--modal`, or `--opencode` is requested. Accepted because it isolates repository credentials from shared master keys, avoids unnecessary dependencies for bare sandboxes, and guarantees consistent secret resolution across both Standard and VM sandboxes.

## Consequences

- `shared/image.py` exports `SHARED_SECRET_NAME = "share0"`.
- `standard_sandbox/main.py` and `vm_sandbox/main.py` conditionally append `modal.Secret.from_name(SHARED_SECRET_NAME)` to `sandbox_secrets` when `args.agy or args.modal or args.opencode` is true.
- `--secret-collection` is strictly scoped to repository credentials (`GH_REPO`, `GH_TOKEN`, and optional `DOTENV_PRIVATE_KEY`).
- `shared/startup.sh` provides explicit diagnostics when `AGE_PRIVATE_KEY` is missing, informing users to configure `AGE_PRIVATE_KEY` in Modal secret `'share0'`.
- Running sandboxes with `--agy`, `--modal`, or `--opencode` requires Modal secret `'share0'` to exist in the target Modal workspace.
