# Multi-Modal Account Profiles in .env and Native Sandbox Provisioning

**Status**: Accepted (Amends [ADR 0003](0006-opt-in-modal-development-tooling-in-sandboxes.md), [ADR 0024](0045-sandbox-runner-web-ui-and-snapshot-registry.md), and [ADR 0053](0053-consolidate-secrets-to-single-dotenv-and-retire-legacy-staging.md))

We introduce multi-account Modal credential configuration via `MODAL_TOKENS` in `.env` as a JSON array of profile objects, purge legacy single-account variables (`MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET`) with zero backward compatibility, and provision all configured workspace profiles directly into the sandbox container filesystem (`/root/.modal.toml`).

## Context

In ADR 0024, we introduced multi-profile workspace discovery in `sandbox/profiles.py` by parsing the host's `~/.modal.toml`. In ADR 0053, we consolidated secrets into a single root `.env` configuration file, injecting credentials into containers and the hosted control plane via native `modal.Secret`.

However, Modal cloud credentials in `.env` remained constrained to a single account pair: `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET`. Consequently:
1. Developers and operators managing multiple Modal workspaces (e.g. personal, work, client, or team organizations) could not declare multiple Modal accounts in `.env`.
2. When launching sandboxes with `--modal`, `scripts/setup.sh` generated only a single `[default]` profile in `/root/.modal.toml`. Multi-tenant tools, cross-account sandboxes, and agent tasks requiring multi-workspace operations could not switch accounts from inside the sandbox.
3. In headless CI/CD and containerized control planes lacking `~/.modal.toml`, only a single fallback profile was available.
4. Staging host `~/.modal.toml` into the control plane image (`sandbox/function.py`) risked leaking local host configuration and violated the zero-credential-at-rest invariant from ADR 0053.

## Decisions

1. **Multi-Profile Credential Configuration (`MODAL_TOKENS`)**:
   - Parameterize Modal account credentials via `MODAL_TOKENS` in `.env` (templated in `.env.example`) as a JSON array of profile objects:
     ```bash
     MODAL_TOKENS='[{"name": "work", "token_id": "ak-...", "token_secret": "as-..."}, {"name": "personal", "token_id": "ak-...", "token_secret": "as-...", "active": true}]'
     ```
   - Each profile object supports `name` (or `profile`), `token_id`, `token_secret`, optional `active: bool`, and optional `environment: str` (defaults to `"main"`).

2. **Zero Backward Compatibility Purge**:
   - Completely remove `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` across the codebase (`.env.example`, `sandbox/launcher.py`, `sandbox/profiles.py`, `scripts/setup.sh`, `readme.md`, `GLOSSARY.md`).
   - If `--modal` is requested without valid `MODAL_TOKENS`, fail fast immediately during launcher preflight validation.

3. **Authoritative Precedence over Host `~/.modal.toml`**:
   - When `MODAL_TOKENS` is defined in `.env` or the process environment, `sandbox/profiles.py` uses it as the authoritative source of truth for workspace profiles. Host `~/.modal.toml` is used only as a secondary fallback when `MODAL_TOKENS` is completely absent.
   - Retire legacy file-staging in `sandbox/function.py` (`image.add_local_file(str(modal_toml), "/root/.modal.toml")`), ensuring the control plane discovers profiles dynamically from `MODAL_TOKENS` passed via `modal.Secret`.

4. **In-Sandbox Multi-Profile Provisioning (`scripts/setup.sh`)**:
   - When `--modal` is passed (`ENABLE_MODAL=1`), `scripts/setup.sh` parses `MODAL_TOKENS` and generates `/root/.modal.toml` (mode `0600`) containing TOML tables for every profile in the array.
   - If a specific profile is targeted via `--profile <name>` (passed as `MODAL_PROFILE`), that profile is marked `active = true` in the sandbox; otherwise, the profile with `"active": true` in `MODAL_TOKENS` (or the first profile) is set as active.

5. **Sandbox Launcher Profile Alignment (`sandbox/launcher.py` & `sandbox/cli.py`)**:
   - Support `--profile <name>` in `sandbox/cli.py` and `LaunchRequest.profile` in `sandbox/core.py`.
   - `sandbox/launcher.py` resolves the Modal client for the specified profile via `get_client_for_profile()`, launches the sandbox in that account, and exports `MODAL_PROFILE` into the sandbox container environment.

## Consequences

- Full parity with `ANTIGRAVITY_TOKENS` for multi-account management in `.env`.
- Sandboxes launched with `--modal` have complete multi-account tooling (`modal profile list`, `modal profile switch <name>`) pre-configured in `/root/.modal.toml`.
- Zero credentials or host configuration files are baked into container image layers.
- Strict preflight schema validation prevents launching broken containers when Modal tooling is requested with invalid or missing credentials.
