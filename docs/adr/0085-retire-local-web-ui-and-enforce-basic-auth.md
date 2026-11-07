# Retire Local Web UI and Enforce Strict HTTP Basic Authentication

**Status**: Accepted (Amends [ADR 0079](0079-hosted-sandbox-control-plane-function.md) and [ADR 0084](0084-sandbox-runner-web-ui-and-snapshot-registry.md))

We retire local Web UI hosting via convenience scripts and direct Uvicorn execution, consolidating the Sandbox Web Dashboard exclusively into the cloud-hosted Modal Control Plane (`sandbox/function.py`). We eliminate permissive authentication mode and enforce strict HTTP Basic Authentication for the Web UI, reserving Bearer token authentication exclusively for machine-to-machine API endpoints.

## Context

In ADR 0084, the Sandbox Web Dashboard was introduced with dual hosting options:
1. Local execution via `scripts/web_ui.py` or `uvicorn sandbox.web:app`.
2. Cloud deployment via `modal deploy sandbox/function.py`.

Additionally, authentication in `sandbox/web.py` permitted unauthenticated access when credentials were not configured (permissive mode), and accepted `MODAL_SANDBOX_AUTH_TOKEN` interchangeably as either a Bearer token or as an HTTP Basic Auth password.

This dual-hosting and blended authentication model introduced several liabilities:
1. **Redundant Local Serving Surface**: Running the dashboard locally required maintaining local Uvicorn processes and CLI arg-parsing bloat in `sandbox/web.py`, duplicating functionality already provided by Modal's cloud ASGI app (`modal serve` / `modal deploy`).
2. **Insecure Permissive Fallback**: In environments without explicit authentication secrets, permissive mode left the Web UI and underlying sandbox management endpoints completely unprotected.
3. **Overloaded Authentication Schemes**: Allowing `MODAL_SANDBOX_AUTH_TOKEN` to unlock browser sessions blurred the boundary between interactive user interfaces and headless automated pipelines (`POST /launch`, `POST /snapshot`).

## Decisions

1. **Retire Local Web UI Launcher & Uvicorn CLI Entrypoint**:
   - Delete `scripts/web_ui.py`.
   - Remove `main()` and CLI argument parsing from `sandbox/web.py`.
   - The Web UI is strictly served as an ASGI router mounted within the Modal Cloud application (`sandbox/function.py`). Developers run `modal serve sandbox/function.py` for interactive development or `modal deploy sandbox/function.py` for hosted ingress.

2. **Strict HTTP Basic Authentication for Web UI (`sandbox/web.py`)**:
   - `check_authentication` in `sandbox/web.py` validates requests strictly against `WEB_UI_USERNAME` and `WEB_UI_PASSWORD` using constant-time digest comparison (`secrets.compare_digest`).
   - All Bearer token logic and `MODAL_SANDBOX_AUTH_TOKEN` checks are removed from `sandbox/web.py`.
   - Permissive fallback is eliminated: if `WEB_UI_USERNAME` or `WEB_UI_PASSWORD` is unconfigured at runtime, the endpoint fails closed with `HTTP 500 Internal Server Error`.
   - `GET /favicon.ico` and `GET /health` remain accessible without credentials.

3. **Deploy & Serve-Time Credential Enforcement (`sandbox/function.py`)**:
   - Top-level initialization in `sandbox/function.py` eagerly validates that `WEB_UI_USERNAME` and `WEB_UI_PASSWORD` exist in `os.environ` or `.env` / `secrets/.env`.
   - If either required variable is missing during `modal deploy` or `modal serve`, execution aborts immediately with a descriptive `RuntimeError`.
   - `MODAL_SANDBOX_AUTH_TOKEN` is retained strictly for headless machine-to-machine API routes (`POST /launch`, `POST /snapshot`) and is not enforced at Web UI deployment time.
   - Validation is bypassed under `pytest` execution to allow isolated unit testing.

## Consequences

- The attack surface is hardened: no unauthenticated Web UI instances can be deployed or accessed.
- Code complexity is reduced by removing redundant local Uvicorn runners.
- Separation of concerns is restored: Web UI uses HTTP Basic Auth; headless machine-to-machine APIs use Bearer tokens.
- All code files strictly adhere to the universal 500 physical line budget ratchet (ADR 0057 / AGENTS.md).
