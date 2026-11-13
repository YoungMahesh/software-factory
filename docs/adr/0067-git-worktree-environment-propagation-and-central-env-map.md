# Git Worktree Environment Secret Propagation and Central env.map

**Status**: Accepted (Amends [ADR 0057](0057-central-env-store-and-host-side-secret-injection.md) and [ADR 0065](0065-retire-in-repo-env-map-and-standardize-ghclone-on-env-store.md))

We introduce automatic Git worktree environment secret propagation via a global `post-checkout` hook, cache decrypted secrets outside Git tracking in `$TARGET_DIR/.git/env-vault/`, implement multi-file monorepo destination mapping via plaintext `env.map` in the Central Environment Store (`env-store`), and extend `SandboxLauncher`, `startup.sh`, and `pull-repo-env` to seamlessly hydrate linked worktrees created in T3 Code Web UI.

## Context

When users or agent processes in T3 Code Web UI start a chat in a new worktree, T3 Code's Git VCS driver executes `git worktree add`. Because Git worktrees only check out tracked files from version control, untracked runtime configurations such as `.env` and subproject environment files were missing in newly created worktrees. Consequently, test suites, builds, and local development servers executed within worktrees failed immediately due to missing configuration keys.

Furthermore:
1. **Age Private Key Inaccessibility**: Under ADR 0057, `AGE_PRIVATE_KEY` is scrubbed from standard sandboxes upon container boot for security isolation. A newly created worktree cannot decrypt secrets from `env-store` on the fly inside the sandbox; it must hydrate from previously decrypted secrets stored on disk.
2. **Untracked Secret Storage**: Secrets and mapping manifests must not be placed within the tracked repository tree (avoiding `.gitignore` modifications or scanner alerts), but must be accessible to any worktree linked to that repository.
3. **Monorepo Seam**: While ADR 0057 anticipated `env.map` for destination mapping (e.g. `web.env=apps/web/.env`), active code only supported a single `default.env` file injected into `$TARGET_DIR/.env`.

## Decisions

1. **Git Worktree Secret Propagation via Global `post-checkout` Hook**:
   - Install a global Git hook at `/root/.git-hooks/post-checkout` registered in `/root/.gitconfig` via `[core] hooksPath = /root/.git-hooks`.
   - Git automatically executes `post-checkout` upon `git worktree add`, `git switch`, and `git checkout` with checkout flag `$3 = 1`.
   - The hook resolves the parent repository via `git rev-parse --git-common-dir` and discovers cached secrets.
   - Preserves custom in-repo hooks by chaining to `$GIT_DIR/hooks/post-checkout` if present.

2. **Isolated Storage Outside Git in `$TARGET_DIR/.git/env-vault/`**:
   - Store decrypted secrets and mapping manifests in `.git/env-vault/` within the repository's common Git directory.
   - Because `.git/` is never tracked by Git, no `.gitignore` modifications are required.
   - Files are secured with restrictive permissions (`0700` directory, `0600` files).
   - All linked worktrees natively access this directory via `$(git rev-parse --git-common-dir)/env-vault`.

3. **Non-Destructive Physical Copies**:
   - The hook physically copies secrets into the worktree (`chmod 600`), ensuring complete isolation so that port or configuration changes in one worktree do not contaminate sibling worktrees or the main workspace.
   - The hook is strictly non-destructive: if a destination file already exists in the worktree, it is preserved, preventing branch switches from overwriting local edits.

4. **Plaintext `env.map` in `env-store`**:
   - Support `github.com/${GH_ORG_NAME}/env-store/<repo>/env.map` for monorepo path mapping (e.g. `web.env=apps/web/.env`).
   - `env.map` must be plaintext (paths only). If an encrypted `env.map` is encountered, a warning is logged and decryption is skipped.
   - If mapped secret files are missing or unmigrated, a warning is emitted and provisioning proceeds with remaining files.

5. **Zero-Config Single-File Default & Fallback**:
   - When `env.map` is absent and only `default.env` exists in `env-store`, the system automatically synthesizes `default.env=.env` and caches it into `.git/env-vault/`.
   - If no vault manifest exists, the hook scans the main repository root for any top-level `.env*` files (`.env`, `.env.local`, etc.) and copies them into the new worktree.

6. **End-to-End Tooling Integration**:
   - **`SandboxLauncher`**: Fetches the vault bundle, injects `VAULT_ENV_BUNDLE_B64`, and populates Modal container secrets.
   - **`startup.sh`**: Unpacks `VAULT_ENV_BUNDLE_B64` into `.git/env-vault/` and target workspace paths, and configures `core.hooksPath`.
   - **`pull-repo-env` / `ghclone`**: Pulls multi-file bundles and caches `.git/env-vault/` on local developer machines.

## Consequences

- **Frictionless T3 Code Worktrees**: Starting a chat in a new worktree in T3 Code Web UI immediately provides all necessary `.env` files.
- **Security Maintained**: `AGE_PRIVATE_KEY` remains eliminated from standard sandboxes, with zero key leakage into worktrees.
- **Monorepo Ready**: Repositories with multi-package architectures (`apps/web`, `packages/api`) are first-class citizens.
- **Universal Line Budget Respected**: All production and test modules remain strictly <= 500 physical lines.
