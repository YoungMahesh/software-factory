# Unify Control Plane Basic Authentication and Retire Antigravity Project ID

**Status**: Accepted (Amends [ADR 0040](0040-hosted-sandbox-control-plane-function.md), [ADR 0025](0046-retire-local-web-ui-and-enforce-basic-auth.md), [ADR 0048](0048-antigravity-acp-credential-preservation-in-filesystem-snapshots.md), and [ADR 0049](0049-launch-fresh-sandboxes-from-web-control-plane.md))

We unify control plane authentication under standard HTTP Basic Authentication (`WEB_UI_USERNAME` and `WEB_UI_PASSWORD`) across both web UI and headless REST API routes (`/launch`, `/snapshot`), retiring `MODAL_SANDBOX_AUTH_TOKEN`. In addition, we retire `ANTIGRAVITY_PROJECT_ID` across configuration and container provisioning to align exclusively with subscription-based Antigravity credentials.

## Context

Prior architectural decisions separated interactive browser dashboard authentication from machine-to-machine API routes:
1. **Redundant Control Plane Credentials**: In [ADR 0025](0046-retire-local-web-ui-and-enforce-basic-auth.md), HTTP Basic Auth (`WEB_UI_USERNAME`, `WEB_UI_PASSWORD`) was enforced for the browser dashboard SPA, while Bearer token authentication (`MODAL_SANDBOX_AUTH_TOKEN`) was preserved for headless API routes (`POST /launch`, `POST /snapshot`). Because `WEB_UI_USERNAME` and `WEB_UI_PASSWORD` were strictly required at deploy time, `MODAL_SANDBOX_AUTH_TOKEN` became a redundant third credential. Remote CLI calls (`--remote`) required tracking a separate secret, creating configuration drift between browser and CLI operators.
2. **Subscription-Based Antigravity Credentials**: In [ADR 0048](0048-antigravity-acp-credential-preservation-in-filesystem-snapshots.md), Antigravity ACP configuration preserved `project_id: "aicode-consumers"` or `ANTIGRAVITY_PROJECT_ID` from the environment. However, Antigravity provider instances in this factory are authenticated using individual subscription keys rather than Google Cloud Platform project-scoped service accounts. Requiring or passing an unused `ANTIGRAVITY_PROJECT_ID` added dead configuration and risk of confusion across `.env`, launcher secrets forwarding, and container bootstrap scripts.

## Decisions

1. **Retire `MODAL_SANDBOX_AUTH_TOKEN` and Enforce HTTP Basic Auth Globally**:
   - In `sandbox/function.py`, removed `verify_bearer_token` and bound `POST /launch` and `POST /snapshot` to `check_authentication` from `sandbox/web.py`.
   - All control plane routes (except public probes `/health` and `/favicon.ico`) strictly validate incoming requests using constant-time digest comparison (`secrets.compare_digest`) against `WEB_UI_USERNAME` and `WEB_UI_PASSWORD`.
   - In `sandbox/main.py` (`run_remote_request`), remote CLI calls encode credentials as standard HTTP Basic Authentication (`Authorization: Basic <base64>`) sourced from the environment or `.env`, failing fast with a descriptive error if either is unset.
   - Removed `MODAL_SANDBOX_AUTH_TOKEN` from `.env`, `.env.example`, launcher secret forwarders, and documentation.

2. **Purge `ANTIGRAVITY_PROJECT_ID` and Strip `project_id` from ACP Tokens**:
   - Removed `ANTIGRAVITY_PROJECT_ID` from `.env`, `.env.example`, `sandbox/launcher.py`, and documentation.
   - In `scripts/setup.sh` and `shared/startup.sh`, removed all `ANTIGRAVITY_PROJECT_ID` reading and actively omit `project_id` when generating `/root/.t3/userdata/providers/antigravity/<hash>/antigravity-acp/acp_token.json`.
   - Legacy `"project_id": "aicode-consumers"` carried over from existing snapshots is stripped, ensuring generated tokens conform strictly to subscription OAuth fields (`client_id`, `client_secret`, `refresh_token`, `scopes`, `token_uri`).

## Consequences

- Configuration is simplified: `.env` requires only a single credential pair (`WEB_UI_USERNAME`, `WEB_UI_PASSWORD`) for all control plane interactions, whether via web browser or CLI `--remote`.
- Antigravity ACP configuration reflects true operational usage (individual subscription accounts) without residual GCP project fields.
- Universal File Line Budget (ADR 0027 / AGENTS.md) is maintained across all modified files.
