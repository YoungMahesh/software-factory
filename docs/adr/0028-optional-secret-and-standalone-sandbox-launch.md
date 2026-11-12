# Optional Secret and Standalone Sandbox Launch

Previously, passing `-s` / `--secret` was mandatory for all standard sandbox launches in `sandbox/main.py` (ADR 0003), coupling sandbox provisioning directly to repository cloning and SOPS secret decryption. When resuming from snapshots (ADR 0024), `--secret` was made optional by requiring `--name`. We decided to make `-s` / `--secret` optional for all sandbox launches, enabling Standalone Sandboxes provisioned without target repository fetch. When launched without `--secret`, `--name <app-name>` is mandatory, repository-specific flags (`--github-branch` and `--testing`) are rejected, and `shared/startup.sh` sets the workspace at `/root/<name>`, initializing an empty Git repository with a default `.gitignore` and an initial commit.

## Considered Options

- **Auto-generated app name (e.g. `sandbox-<uuid>`) without mandatory `--name`**: Allow omitting both `--secret` and `--name`. Rejected because requiring `--name` guarantees a predictable, deterministic workspace directory and container application identity, maintaining parity with snapshot restoration rules.
- **Root home directory (`/root`) as workspace**: Setting `TARGET_DIR` directly to `/root`. Rejected because placing the user workspace directly in `/root` pollutes system files, dotfiles (`.bashrc`, `.ssh`, `.config`), and credentials with application source code. Isolating to `/root/<name>` keeps projects clean and modular.
- **Bare workspace directory without Git initialization**: Creating `/root/<name>` without running `git init`. Rejected because agent harnesses (Pi Agent), T3 Code Server (`t3 serve`), and developer tooling expect an active Git repository. Pre-initializing `main` with `.gitignore` and an initial commit provides zero-friction immediate use.

## Consequences

- `-s` / `--secret` is optional across both standard and snapshot sandbox launches.
- When `-s` / `--secret` is omitted, `--name <app-name>` is strictly required; missing `--name` produces a CLI parser validation error.
- Passing `--github-branch` (non-default) or `--testing` without `-s` / `--secret` produces an explicit CLI validation error.
- `sandbox/main.py` skips repository secret staging and injects `NO_REPO=1` into the sandbox container environment.
- `shared/startup.sh` recognizes `NO_REPO=1`, skips repository fetch secret decryption and `git clone`, creates `/root/${APP_NAME}`, initializes an empty Git repository (`git init -b main`), adds a standard `.gitignore` (`.env`, `node_modules/`, `dist/`, `.venv/`, `__pycache__/`), and records an initial commit.
- Cloudflare Tunnel ingress, OpenCode, AgY, T3 Code Server, and all toolchain flags continue to work seamlessly in Standalone Sandboxes.
