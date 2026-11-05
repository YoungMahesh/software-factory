# Multi-Account Antigravity Provider Instances in T3 Code

**Status**: Accepted (Amends [ADR 0046](0046-t3-code-server-and-agent-control-surface.md))

We added support for multiple simultaneous Google Antigravity accounts inside Modal sandboxes launched with T3 Code (`--t3` or `--t3code`). Sandboxes automatically stage and decrypt three separate OAuth credentials (`antigravity-oauth-token.json`, `antigravity-oauth-token-mgh.json`, and `antigravity-oauth-token-anv.json`), synthesizing isolated ACP agent runtime credentials and status caches for each account in T3 Code (`antigravity`, `antigravity-mgh`, and `antigravity-anv`).

## Considered Options

- **Single Global Account with Manual Profile Switching**: Retaining only a single active Antigravity account in T3 Code and requiring developers to run `agyprofile` (formerly `switch-agy-profile.sh`) in the terminal to switch accounts. Rejected because T3 Code threads and background orchestrator delegates require distinct `providerInstanceId` targets to run tasks across accounts concurrently without clashing on local state or quota limits.
- **Renaming All Instances (`antigravity-m47`, `antigravity-mgh`, `antigravity-anv`)**: Renaming the default instance to `antigravity-m47`. Rejected to maintain full backwards compatibility with existing thread metadata, persisted project configurations, and default orchestrator delegates expecting `instanceId: "antigravity"`.
- **Pre-Decrypted Offline Profiles Directory**: Staging decrypted tokens into `~/.gemini/antigravity-cli/profiles/{m47,mgh,anv}` with 0600 permissions at container boot, enabling `scripts/agyprofile` to switch CLI profiles instantly without needing lingering raw files in `/root/secrets/` or live SOPS age keys. Accepted because it cleanly satisfies both T3 Code multi-account runtime requirements and the ephemeral secret scrubbing invariant.

## Consequences

- **Staging (`shared/image.py`)**: `LOCAL_ANTIGRAVITY_SECRET_MGH` and `LOCAL_ANTIGRAVITY_SECRET_ANV` are defined and staged alongside `LOCAL_ANTIGRAVITY_SECRET` whenever `--t3` or `--agy` is enabled.
- **Decryption & Provisioning (`scripts/setup.sh` and `shared/startup.sh`)**:
  - Automatically decrypts the three tokens into `~/.gemini/antigravity-cli/profiles/{m47,mgh,anv}` and initializes `~/.gemini/antigravity-cli/antigravity-oauth-token` to `m47`.
  - For each account (`antigravity`, `antigravity-mgh`, `antigravity-anv`), generates an isolated ACP token (`/root/.t3/userdata/providers/antigravity/<sha256>/antigravity-acp/acp_token.json`) and settings.
  - Registers each instance in `/root/.t3/userdata/settings.json` under `providerInstances` with respective display names (`Antigravity`, `Antigravity (MGH)`, `Antigravity (ANV)`).
  - Pre-seeds `/root/.t3/caches/{antigravity,antigravity-mgh,antigravity-anv}.json` with Gemini 3.8 models to eliminate initial UI sign-in and model probing latency.
- **Offline CLI Profile Switching (`scripts/agyprofile`)**: Updated to switch directly from `~/.gemini/antigravity-cli/profiles/<profile>` without requiring `/root/secrets/` (`switch-agy-profile.sh` retained as symlink).
- **Secret Scrubbing**: All `/root/secrets/antigravity-oauth-token*.json` files are wiped from disk immediately following setup.
- **Universal File Line Budget**: All modified code and test files remain strictly within the 500 line budget.
