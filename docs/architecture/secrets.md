# Secrets and Credential Lifecycle

Software Factory passes configuration through Modal Secrets and then configures tools inside the sandbox. Some of those tools require credentials on disk. Treat a running sandbox, its filesystem snapshots, and its credential volumes as sensitive environments.

## Launch-time injection

The implementation is in `sandboxes/sandbox/config.py`, `sandboxes/sandbox/launcher.py`, and `sandboxes/shared/startup.sh`.

- The hosted control plane collects the factory root `.env`, required dashboard credentials, provenance, and selected host environment fallbacks at deployment time. Changes to deployed credentials require redeployment.
- A child launch with a factory `.env` generally passes that file through `modal.Secret.from_dotenv()`. When the file contains `CODEX_STATUS_SECRET`, the launcher builds a filtered dictionary excluding that signing key.
- Without a factory `.env`, the launcher forwards a selected set of host environment keys. This includes GitHub, Age, Modal, ingress, provider, dashboard, and Resource Plane credentials; see [environment resolution](../reference/environment.md#resolution-and-propagation).
- Repository secrets are fetched and decrypted from `env-store` on the launch host, then sent to the sandbox as environment values and encoded file bundles.

A standalone launch requires no GitHub credentials, but it can still receive configured factory secrets through the same injection path. Standalone mode does not guarantee an empty credential environment.

Modal documents [Secrets as environment injection](https://modal.com/docs/guide/secrets). Application behavior after injection determines whether values also reach disk; this project does not promise RAM-only handling or immediate erasure from platform storage after termination.

## Where credentials persist

| Credential or data | Sandbox storage and behavior |
| :--- | :--- |
| Repository environment files | Mapped destinations such as `.env` and `apps/web/.env`, written with mode `0600` |
| Decrypted vault cache | Repository common Git directory under `env-vault/`; directory mode `0700`, files `0600` |
| GitHub token | Used for cloning and tooling; startup also writes it into `/root/.bashrc` and `/etc/environment` |
| Antigravity and OpenCode provider credentials | Provider configuration and authentication files; Antigravity credentials may be preserved in filesystem snapshots |
| Modal profiles with `--modal` | `/root/.modal.toml`, populated from `MODAL_TOKENS` |
| Age key | Can enter the sandbox through factory injection. Normal startup removes temporary SOPS state and unsets `AGE_PRIVATE_KEY`; `--sops` deliberately retains it in configuration and shell files |
| Codex saved login | With an assigned profile, a dedicated Modal Volume mounted at `/root/.codex-profile`; otherwise local sandbox state |
| T3 history and transcripts | Copied between local state and the `t3code-usage-v1` volume mounted at `/root/.t3-storage` when persistence is enabled |

Removing an environment variable from a shell does not erase copies already written to files, child processes, logs, snapshots, or volumes. `0600` restricts file access; it does not exclude a file from a filesystem snapshot.

## Filesystem snapshots

[Modal filesystem snapshots](https://modal.com/docs/guide/sandbox-snapshots) preserve filesystem state. They do not resume running processes. Files written by startup or an agent can include `.env`, the Git vault cache, shell exports, provider credentials, and retained SOPS or Modal configuration.

**A filesystem snapshot is not automatically safe to share.** The factory does not sanitize credential files before capture. Limit access as you would for the original sandbox, and use an independently prepared, inspected image when a credential-free environment is required. Mounted volumes have a separate lifecycle; terminating a sandbox does not remove saved Codex logins or T3 history from those volumes.

Resumption injects launch configuration again and reuses existing files. Fresh injection does not remove credentials already present in the image. See [snapshot behavior](snapshots.md) for restore and persistence details.

## Central Environment Store (`env-store`)

The organization's private `env-store` repository holds SOPS-encrypted files under `<repo>/`, using Age recipients. `<repo>/env.map` maps vault filenames to workspace destinations, for example `web.env=apps/web/.env`. Legacy manifests inside application repositories are retired; see [ADR 0057](../adr/0057-central-env-store-and-host-side-secret-injection.md) and [ADR 0065](../adr/0065-retire-in-repo-env-map-and-standardize-ghclone-on-env-store.md).

`push-repo-env` encrypts and pushes mapped files. `pull-repo-env` decrypts them into local destinations, and `ghclone` invokes the pull workflow after cloning. Manual pulls need usable GitHub access and an Age key on the machine performing the pull. Host-side decryption does not imply that `GH_TOKEN` and `AGE_PRIVATE_KEY` are excluded from child sandbox injection.

## Worktree propagation

Startup caches decrypted files in the repository's common Git directory under `env-vault/`. The global `/root/.git-hooks/post-checkout` hook copies mapped files into newly created worktrees with restricted permissions, without overwriting existing destination files. This lets worktrees reuse the initial secret bundle after normal startup has scrubbed the Age key; see [ADR 0067](../adr/0067-git-worktree-environment-propagation-and-central-env-map.md).

The cache is outside tracked Git content, but remains plaintext on the sandbox filesystem and can be captured by a filesystem snapshot. Changes to a worktree's `.env` do not automatically update the vault or other worktrees.

## VPS deployment boundary

Infrastructure and Hosted App deployment use an explicit SSH private key on the deployment host. Keep the key in an ignored file such as `.secrets/resource_plane_ssh`, rather than embedding it in `.env`. Normal runtime database and storage clients use the Resource Plane API, database roles, and bucket credentials.

A file mapped into a target repository through `env-store` will be materialized there. Do not map deployment SSH keys into ordinary application sandboxes if you want to maintain the host deployment boundary.
