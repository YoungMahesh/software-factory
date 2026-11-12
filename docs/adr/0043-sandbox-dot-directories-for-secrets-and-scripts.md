# Sandbox Dot Directories for Staged Secrets and Scripts

**Status**: Accepted (Amends [ADR 0005](0017-in-sandbox-tooling-secrets-and-setup-script-staging.md), [ADR 0023](0023-organization-credentials-and-canonical-test-organization.md), and [ADR 0035](0035-multi-account-antigravity-provider-instances-in-t3-code.md))

We transition in-sandbox staging directories for secrets and helper scripts from visible top-level paths (`~/secrets` and `~/scripts`) to hidden dot directories (`~/.secrets` and `~/.scripts`, corresponding to `/root/.secrets` and `/root/.scripts`), keeping the user workspace clean and uncluttered.

## Context

When launching a new Modal sandbox with `sandbox/main.py` or the hosted control plane (`sandbox/function.py`), files from the repository were historically staged into `/root/secrets` and `/root/scripts`:
- Tooling and organization secrets (`github-orgs.env`, `opencode.env`, `modal.toml`, `cloudflare.env`, `antigravity.env`) were staged into `/root/secrets`.
- Setup scripts and developer CLI symlinks (`setup.sh`, `agyq`, `ghls`, `ghpr`, `ghclone`, `agyprofile`) were staged into `/root/scripts`.

Because the default user in the container is `root`, `~/` corresponds directly to `/root`. Consequently, when connecting via SSH or browsing the workspace in IDE file explorers (T3 Code or OpenCode), running `ls` or viewing the home directory displayed `secrets` and `scripts` directly alongside the cloned repository (e.g. `/root/software-factory`).

Furthermore:
- Encrypted secrets staged into `~/secrets` are only needed ephemerally during container boot and are scrubbed by `shared/startup.sh`. Even after files are scrubbed, an empty `/root/secrets` directory remained visible in user listings.
- Developer CLI tools are already installed into `/usr/local/bin` (which is in `$PATH`), rendering top-level `~/scripts` redundant and cluttered for everyday terminal and editor workflows.

## Considered Options

- **Retain Visible Directories (`~/secrets` and `~/scripts`)**: Keep existing paths. Rejected because it exposes transient staging directories in default `ls` listings and editor file trees.
- **Remove `scripts` Symlinks Entirely and Inline All Secrets into Environment Variables**: Avoid staging files on disk altogether. Rejected because SOPS decryption, multi-account Antigravity token resolution, and Cloudflared credentials require disk files during container boot.
- **Adopt In-Sandbox Dot Directories (`~/.secrets` and `~/.scripts`) with Backward-Compatible Fallbacks**:
  1. Stage container-destined secret files into `/root/.secrets/` (e.g., `/root/.secrets/github-orgs.env`, `/root/.secrets/cloudflare.env`, etc.).
  2. Stage the setup script into `/root/.scripts/setup.sh` and convenience links into `/root/.scripts/`.
  3. Update `shared/startup.sh`, `scripts/setup.sh`, and `scripts/agyprofile` to prefer `/root/.secrets` and `/root/.scripts`, while maintaining transparent fallbacks to `/root/secrets` and `/root/scripts` for existing snapshots or legacy environments.
  4. Prune the ephemeral staging directory `/root/.secrets` upon secret scrubbing.
  5. Retain local workstation compatibility so `scripts/setup.sh` running outside containers continues to resolve local `secrets/` seamlessly.
  Accepted.

## Consequences

- **Home Directory Hygiene**: Running `ls ~` or opening `/root` in T3 Code or OpenCode now only displays the active project repository (and any explicit user files), hiding transient system staging directories.
- **Ephemerality & Security**: Staged encrypted files reside in `~/.secrets` until decrypted and wiped by `startup.sh`, which also removes `/root/.secrets` if empty.
- **Developer Tooling Accessibility**: Developer CLI utilities (`agyq`, `ghls`, `ghpr`, `ghclone`, `agyprofile`, `t3`) remain globally executable in `/usr/local/bin` on `$PATH`.
- **Backward Compatibility**: Container startup scripts and tools check `/root/.secrets` first with fallback to `/root/secrets`, ensuring existing filesystem snapshots resume without disruption.
- **Repository Parity**: The host repository layout (`scripts/` and `secrets/`) remains unchanged for developer machines and version control.
