# 01: Dedicated Port 3010 and HTTP Basic Auth Security

**What to build:** The web application server binds to port 3010 by default (overrideable via environment variable) to prevent port collisions with guest preview applications on port 3000. All routes, static assets, and API endpoints are protected by HTTP Basic Authentication using credentials configured via environment variables, returning HTTP 401 Unauthorized for missing or invalid credentials and granting access when authenticated.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Web application defaults to listening on port 3010 when launched, with support for environment variable port override.
- [ ] CLI dispatch flags for launching the web interface reflect the default port 3010.
- [ ] Unauthenticated requests to web pages and API endpoints return HTTP 401 with standard WWW-Authenticate header.
- [ ] Valid HTTP Basic credentials configured via environment variables grant access to all routes and SSE streams.
- [ ] A documented local development fallback is provided with a startup warning when authentication environment variables are not set.
- [ ] Integration tests verify that unauthenticated requests fail with 401 and authenticated requests succeed with 200.
