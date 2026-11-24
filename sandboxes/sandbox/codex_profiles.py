"""Workspace-scoped Codex login volumes and launcher-owned reservations."""

from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import hmac
import io
import json
from pathlib import PurePosixPath
import time
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import modal

from sandbox.config import TIMEOUT_SECS

if TYPE_CHECKING:
    from sandbox.core import LaunchRequest

LABELS = ("A", "B", "C")
CODEX_HOME = "/root/.codex-profile"
OWNER = "/owner.json"
AUTH_FILE = "/codex-home/auth.json"
STATUS_PATH = "/api/codex/profiles"


@dataclass
class Profile:
    label: str
    volume: modal.Volume
    saved_login: bool
    state: str
    sandbox_name: str | None

    def status(self) -> dict:
        return {
            "profile": self.label, "saved_login": self.saved_login,
            "state": self.state, "sandbox": self.sandbox_name,
        }

    def attach(self, env: dict, volumes: dict, tags: dict) -> None:
        self.record(tags["instance_name"], tags["app_name"], None)
        env.update(CODEX_PROFILE=self.label, CODEX_HOME=CODEX_HOME)
        volumes[CODEX_HOME] = self.volume.with_mount_options(sub_path="/codex-home")
        tags["codex_profile"] = self.label
        tags["codex_attempt"] = tags["instance_name"]

    def record(self, name: str, app: str, sandbox_id: str | None) -> None:
        record = {"name": name, "app": app, "id": sandbox_id}
        with self.volume.batch_upload(force=True) as upload:
            upload.put_file(io.BytesIO(json.dumps(record).encode()), OWNER, mode=0o600)


def _owner_state(volume: modal.Volume, client: modal.Client | None) -> tuple[str, str | None]:
    try:
        raw = b"".join(volume.read_file(OWNER))
    except FileNotFoundError:
        return "available", None
    name = None
    try:
        owner = json.loads(raw)
        name = owner["name"]
        if not isinstance(name, str) or not name:
            return "unknown", None
        if owner["id"]:
            sandbox = modal.Sandbox.from_id(owner["id"], client=client)
        else:
            sandbox = modal.Sandbox.from_name(
                owner["app"], name, include_terminated=True, client=client,
            )
            if sandbox.get_tags().get("codex_attempt") != name:
                return "unknown", name
        return ("in use", name) if sandbox.poll() is None else ("available", None)
    except (KeyError, ValueError, TypeError, modal.exception.Error):
        return "unknown", name if isinstance(name, str) else None


def list_profiles(
    prefix: str, client: modal.Client | None = None, *, create: bool = False,
) -> list[Profile]:
    profiles = []
    if not prefix:
        return profiles
    for label in LABELS:
        volume = modal.Volume.from_name(
            f"{prefix}-{label.lower()}", version=2, create_if_missing=create, client=client,
        )
        try:
            volume.hydrate()
            try:
                saved = any(PurePosixPath(entry.path).name == "auth.json"
                            for entry in volume.listdir(AUTH_FILE))
            except (FileNotFoundError, modal.exception.NotFoundError):
                saved = False
            state, name = _owner_state(volume, client)
        except modal.exception.NotFoundError:
            state, name, saved = "not created", None, False
        except (modal.exception.Error, OSError):
            state, name, saved = "unknown", None, False
        profiles.append(Profile(label, volume, saved, state, name))
    return profiles


def select_profile(prefix: str, client: modal.Client | None) -> Profile | None:
    available = [p for p in list_profiles(prefix, client, create=True) if p.state == "available"]
    return next((p for p in available if p.saved_login), available[0] if available else None)


def status_access(
    endpoint: str, secret: str, profile: str | None, testing: bool, ttl: int,
) -> dict[str, str]:
    if not secret or urlsplit(endpoint).scheme != "https" or not urlsplit(endpoint).netloc:
        return {}
    payload = base64.urlsafe_b64encode(json.dumps([profile, testing, int(time.time()) + ttl]).encode())
    signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return {
        "CODEX_STATUS_URL": endpoint.rstrip("/") + STATUS_PATH,
        "CODEX_STATUS_TOKEN": f"{payload.decode()}.{signature}",
    }


def decode_status_access(token: str, secret: str) -> tuple[str | None, bool]:
    payload, signature = token.split(".", 1)
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not secret or not hmac.compare_digest(signature.encode(), expected.encode()):
        raise ValueError("Invalid Codex status token")
    profile, testing, expires = json.loads(base64.urlsafe_b64decode(payload))
    if expires < time.time():
        raise ValueError("Expired Codex status token")
    return profile, testing


def pool_prefix(prefix: str, testing: bool) -> str:
    return f"test-{prefix}" if prefix and testing else prefix


def prepare_profile(config: dict[str, str], req: LaunchRequest, client: modal.Client | None,
                    env: dict, volumes: dict, tags: dict) -> Profile | None:
    prefix = pool_prefix(config.get("CODEX_PROFILE_VOLUME_PREFIX", ""), req.testing)
    if prefix:
        env.update(status_access(config.get("MODAL_SANDBOX_ENDPOINT_URL", ""),
                                 config.get("CODEX_STATUS_SECRET", ""),
                                 req.profile, req.testing, TIMEOUT_SECS + 300))
    profile = select_profile(prefix, client)
    if profile:
        profile.attach(env, volumes, tags)
    return profile
