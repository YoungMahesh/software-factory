# Secrets & Security Architecture

Modal Sandboxes enforces a defense-in-depth model for managing API keys, SSH credentials, and environment variables across local terminals, cloud control planes, and running sandboxes.

## Credential Tiers

| Tier | Required Secrets | In-Sandbox Scope | Use Case |
| :--- | :--- | :--- | :--- |
| **Tier 0: Standalone Sandbox** | None (`modal setup` only) | No external secrets injected | Basic development, quick tests, public tools |
| **Tier 1: Repository Clones** | `GH_TOKEN`, `GH_ORG_NAME` | Git clone credentials | Working on private/organization GitHub repos |
| **Tier 2: Ingress & Cloudflare** | Optional `CLOUDFLARE_TUNNEL_TOKEN` | Tunnel authentication | Stable custom web domains |
| **Tier 3: AI Tooling** | `ANTIGRAVITY_TOKENS`, `OPENCODE_GO_API_KEY` | Provider API access | Running autonomous or paired coding agents |
| **Tier 4: Encrypted Repo Secrets** | `AGE_PRIVATE_KEY` | Ephemeral decryption | Decrypting repository `.env` via SOPS |

---

## 1. Ephemeral In-Sandbox Credentials

Security sensitive keys injected for sandbox bootstrapping are strictly ephemeral:

- **Key Purging** (see [ADR 0007](../adr/0007-ephemeral-sops-credentials-in-sandboxes.md)): When secrets like `AGE_PRIVATE_KEY` are provided to decrypt repository `.env` files during `startup.sh`, the private keys are removed from `/root/.config/sops` and memory as soon as decryption finishes.
- **Opt-In Retention** (see [ADR 0030](../adr/0030-opt-in-sops-credential-retention.md)): If developers need to debug SOPS decryption interactively, passing the `--sops` flag retains keys in `~/.config/sops`.

---

## 2. Shared Workspace Secrets (`share0`)

For automated sandbox deployments, Modal Sandboxes supports mounting the `share0` Modal Secret (see [ADR 0014](../adr/0014-shared-workspace-secret-share0-for-age-private-key.md)).

- Stores shared configuration like default Age decryption keys and tunnel tokens.
- Bound securely through Modal's secrets infrastructure without committing keys to Git.

---

## 3. Dot-Directory Staging Layout

To prevent secret leakage and file conflicts (see [ADR 0082](../adr/0082-sandbox-dot-directories-for-secrets-and-scripts.md)):

```text
/root/
├── .secrets/              # Ephemeral environment files and credentials
├── .scripts/              # Staged startup and toolchain initialization scripts
└── <workspace-name>/      # Clean developer workspace directory
```

Target repositories are cloned directly into `/root/<workspace-name>`, ensuring application files never collide with internal sandbox scripts.
