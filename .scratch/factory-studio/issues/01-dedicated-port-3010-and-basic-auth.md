# 01: Dedicated Port 3010 and HTTP Basic Auth Security

**What to build:** The web application server binds to port 3010 by default (overrideable via environment variable) to prevent port collisions with guest preview applications on port 3000. All routes, static assets, and API endpoints are protected by HTTP Basic Authentication using credentials configured via environment variables, returning HTTP 401 Unauthorized for missing or invalid credentials and granting access when authenticated.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] Web application defaults to listening on port 3010 when launched, with support for environment variable port override.
- [x] CLI dispatch flags for launching the web interface reflect the default port 3010.
- [x] Unauthenticated requests to web pages and API endpoints return HTTP 401 with standard WWW-Authenticate header.
- [x] Valid HTTP Basic credentials configured via environment variables grant access to all routes and SSE streams.
- [x] A documented local development fallback is provided with a startup warning when authentication environment variables are not set.
- [x] Integration tests verify that unauthenticated requests fail with 401 and authenticated requests succeed with 200.

## Answer

Resolved by implementing dedicated port 3010 binding and HTTP Basic Authentication security across the web interface:

1. **Dedicated Port 3010**:
   - `factory/ui/server.py` defines `DEFAULT_PORT = 3010` and `get_default_port()` supporting override via the `PORT` environment variable.
   - `factory/run.py` reuses `get_default_port()` from `factory.ui.server`, defaulting CLI dispatch (`--ui` / `--console`) to port 3010 with `--port` override.
2. **HTTP Basic Auth Middleware**:
   - Implemented ASGI `BasicAuthMiddleware` in `factory/ui/auth.py` and registered globally in `factory/ui/app.py`.
   - Protects all HTML routes, static assets, REST APIs, and SSE streams (`/api/jobs/{id}/stream`).
   - Constant-time verification using `secrets.compare_digest` against `FACTORY_AUTH_USER` and `FACTORY_AUTH_PASS`.
   - Case-insensitive scheme parsing (`Basic` / `basic`).
   - Returns HTTP 401 Unauthorized with standard `WWW-Authenticate: Basic realm="Factory Studio"` header when missing or invalid.
3. **Local Development Fallback & Startup Warning**:
   - When `FACTORY_AUTH_USER` or `FACTORY_AUTH_PASS` is unset, `get_auth_credentials()` falls back to `admin:admin` and logs a security warning.
   - `factory/ui/server.py` emits a startup security warning banner displaying active auth status.
4. **Integration Testing**:
   - Added unit and integration tests in `tests/test_ui.py` covering port defaults, environment overrides, 401 unauthenticated responses, 200 authenticated responses, SSE stream protection, case-insensitive scheme matching, and static asset protection.
