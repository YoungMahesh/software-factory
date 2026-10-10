"""HTTP Basic Authentication and Local Development Security for Factory Studio.

Provides credential retrieval with environment variables (FACTORY_AUTH_USER,
FACTORY_AUTH_PASS), secure constant-time credential verification, local development
fallback with startup warnings, and ASGI BasicAuthMiddleware protecting all
routes, API endpoints, static assets, and SSE streams.
"""

import base64
import binascii
import logging
import os
import secrets
from typing import NamedTuple, Sequence

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("factory.ui.auth")

DEFAULT_DEV_USER: str = "admin"
DEFAULT_DEV_PASS: str = "admin"
AUTH_REALM: str = "Factory Studio"
ENV_AUTH_USER: str = "FACTORY_AUTH_USER"
ENV_AUTH_PASS: str = "FACTORY_AUTH_PASS"


class AuthCredentials(NamedTuple):
    """Container for authentication credentials."""

    username: str
    password: str
    is_fallback: bool


def get_auth_credentials() -> AuthCredentials:
    """Retrieves authentication credentials from environment variables.

    Returns:
        AuthCredentials: (username, password, is_fallback)
        is_fallback is True when default local development credentials are used.
    """
    env_user = os.getenv(ENV_AUTH_USER)
    env_pass = os.getenv(ENV_AUTH_PASS)

    if env_user and env_pass:
        return AuthCredentials(env_user, env_pass, False)

    missing = []
    if not env_user:
        missing.append(ENV_AUTH_USER)
    if not env_pass:
        missing.append(ENV_AUTH_PASS)

    logger.warning(
        "⚠️  SECURITY WARNING: %s not set. "
        "Falling back to default local development credentials ('%s':'%s'). "
        "Do NOT use default credentials in production environments!",
        " and ".join(missing),
        DEFAULT_DEV_USER,
        DEFAULT_DEV_PASS,
    )
    return AuthCredentials(DEFAULT_DEV_USER, DEFAULT_DEV_PASS, True)


def verify_credentials(
    username: str,
    password: str,
    expected_user: str,
    expected_pass: str,
) -> bool:
    """Performs constant-time comparison of username and password."""
    user_match = secrets.compare_digest(
        username.encode("utf-8"),
        expected_user.encode("utf-8"),
    )
    pass_match = secrets.compare_digest(
        password.encode("utf-8"),
        expected_pass.encode("utf-8"),
    )
    return user_match and pass_match


class BasicAuthMiddleware:
    """ASGI Middleware enforcing HTTP Basic Authentication on all HTTP endpoints."""

    def __init__(
        self,
        app: ASGIApp,
        realm: str = AUTH_REALM,
    ) -> None:
        self.app = app
        self.realm = realm
        self.creds = get_auth_credentials()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers: Sequence[tuple[bytes, bytes]] = scope.get("headers", [])
        auth_header: str | None = None
        for raw_name, raw_value in headers:
            if raw_name.lower() == b"authorization":
                try:
                    auth_header = raw_value.decode("latin1")
                except UnicodeDecodeError:
                    pass
                break

        # Scheme check per RFC 7617/7235 is case-insensitive
        if not auth_header or not auth_header[:6].lower() == "basic ":
            await self._send_unauthorized(send)
            return

        b64_creds = auth_header[6:].strip()
        try:
            decoded = base64.b64decode(b64_creds).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            await self._send_unauthorized(send)
            return

        parts = decoded.split(":", 1)
        if len(parts) != 2:
            await self._send_unauthorized(send)
            return

        username, password = parts
        if not verify_credentials(username, password, self.creds.username, self.creds.password):
            await self._send_unauthorized(send)
            return

        await self.app(scope, receive, send)

    async def _send_unauthorized(self, send: Send) -> None:
        www_authenticate = f'Basic realm="{self.realm}"'.encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"www-authenticate", www_authenticate),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": b"Unauthorized",
        })
