# Consolidate Secrets to Single .env and Retire Legacy Staging

**Status**: Accepted (Amends [ADR 0014](0014-shared-workspace-secret-share0-for-age-private-key.md), [ADR 0077](0077-centralized-org-credentials-and-in-repo-secrets.md), [ADR 0082](0082-sandbox-dot-directories-for-secrets-and-scripts.md), and [ADR 0090](0090-control-plane-secret-staging-and-credential-validation.md))

We consolidate all factory control plane credentials, single-organization GitHub tokens, ingress tokens, and AI tooling credentials into a single root `.env` configuration file (templated via `.env.example`), inject them as native container process environment variables via Modal Secrets, and retire the legacy `secrets/` directory and in-image secret staging.

## Context

Previously, credentials across the software factory were dispersed across multiple files:
- `secrets/github-orgs.env`: Multi-organization GitHub Personal Access Tokens.
- `secrets/cloudflare.env`: Ingress tunnel credentials.
- `secrets/opencode.env`: OpenCode provider API keys.
- `secrets/antigravity.env` & `secrets/antigravity-oauth-token*.json`: Antigravity environment and separate OAuth token files.
- `secrets/modal.toml`: Modal CLI configuration.
- `.secrets/`: Legacy Factory Studio in-repo manifests (`env.map` and `studio.env`).

These files required mandatory SOPS encryption via a shared Modal secret `share0` (`AGE_PRIVATE_KEY`). Sandbox launching staged encrypted files into the container image filesystem via `image.add_local_file()`, requiring in-container `sops decrypt` routines during boot in `shared/startup.sh`, followed by disk deletion.

This multi-file architecture created operational friction for open-source adoption:
1. Contributors needed to configure Age and SOPS just to run base tooling.
2. File-based staging risked baking sensitive credentials into cached image layers and snapshots.
3. Adding or updating credentials required juggling multiple encryption targets and `.sops.yaml` regex patterns.

## Decisions

1. **Unified Environment Configuration (`.env` and `.env.example`)**:
   - Standardize on a single root `.env` file as the sole source of truth for all software-factory infrastructure and tooling credentials.
   - Maintain a comprehensive, tracked `.env.example` documenting all required and optional environment keys.
   - Completely remove the legacy `secrets/` and root `.secrets/` directories from this repository.

2. **Native Modal Secret Injection**:
   - Inject `.env` directly into Modal sandboxes and the hosted control plane as native environment variables using `modal.Secret.from_dotenv(".env")` (or `modal.Secret.from_dict(...)` when launching from the control plane).
   - Eliminate file-based secret staging (`add_local_file`) in `shared/image.py` and `sandbox/launcher.py`.

3. **Single GitHub Organization Configuration**:
   - Replace the multi-file, multi-org mapping with two explicit environment variables: `GH_TOKEN` (for cloning and `gh` CLI) and `GH_ORG_NAME` (e.g. `sFactory0`).

4. **Multi-Profile Antigravity Tokens as JSON Array**:
   - Parameterize Antigravity OAuth tokens via `ANTIGRAVITY_TOKENS` in `.env` as a JSON array of profile objects:
     ```bash
     ANTIGRAVITY_TOKENS='[{"name": "Work", "token": "1//refresh_token_alpha"}, {"name": "Personal", "token": "1//refresh_token_beta"}]'
     ```
   - In `scripts/setup.sh`, dynamically parse this array to register T3 Code provider instances and ACP profiles, setting the first profile as primary. If empty or absent, Antigravity setup is skipped.

5. **Optional SOPS Decryption**:
   - Demote SOPS and `AGE_PRIVATE_KEY` (`share0`) from a mandatory boot prerequisite to an optional dependency.
   - SOPS is only invoked if a cloned target repository provides an In-Repo Secret Manifest (`.secrets/env.map`).

6. **Preflight `.env` Schema Validation**:
   - Validate `.env` configuration at launch (`sandbox/main.py`) and deploy time (`sandbox/function.py`), failing fast with actionable guidance if required variables are missing.

## Consequences

- Zero credentials or encrypted secret files are baked into container image layers.
- Operational onboarding is simplified to copying `.env.example` to `.env`.
- Base tooling startup inside sandboxes is streamlined and runs without SOPS overhead.
- All code modules remain strictly within the universal <= 500 lines physical budget (ADR 0057 / AGENTS.md).
