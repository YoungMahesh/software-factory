"""Deploy real app workflows using the local SSH and Docker test adapters."""

import json
from types import SimpleNamespace

import pytest

from sandboxes.tests.test_host_ingress.conftest import ingress
from sandbox.app_deploy import _caddy, _deploy
from sandbox.app_deploy._config import AppDeployRequest


@pytest.fixture
def apps(ingress, monkeypatch):
    factory = ingress.tmp_path / "factory"
    factory.mkdir()
    key = factory / "key"
    key.write_text("unused test key")
    key.chmod(0o600)
    (factory / ".env").write_text(
        f"RESOURCE_PLANE_SSH_HOST=unused.invalid\nRESOURCE_PLANE_SSH_KEY={key}\n"
        "APPS_BASE_DOMAIN=apps.example.com\nGH_ORG_NAME=test-org\nGH_TOKEN=unused-test-token\n"
    )
    remote_base = ingress.tmp_path / "hosted"
    remote_base.mkdir()
    registry = ingress.root / ".factory-apps"
    (ingress.root / "conf/sites/apps-wildcard.caddy").write_text("*.apps.example.com {}")
    monkeypatch.setattr("sandbox.app_deploy._ownership.REGISTRY_DIR", str(registry))
    monkeypatch.setattr("sandbox.app_deploy._ownership.APPS_DIR", str(ingress.root / "conf/apps"))
    for module in ("sandbox.app_deploy._ownership", "sandbox.app_deploy._deploy"):
        monkeypatch.setattr(f"{module}.build_ssh_cmd", lambda _config, command: ["bash", "-c", command])
    monkeypatch.setattr(_deploy, "check_ssh_connection", lambda _config: True)
    monkeypatch.setattr(_deploy, "check_remote_docker", lambda _config: (True, "Docker available"))
    monkeypatch.setattr(_deploy, "stage_remote_ca_cert", lambda *args, **kwargs: False)
    read_remote = _deploy._read_remote

    def read(config, path, *args, **kwargs):
        if path.startswith("/opt/caddy/"):
            path = path.replace("/opt/caddy/", f"{ingress.root}/", 1)
        return read_remote(config, path, *args, **kwargs)

    monkeypatch.setattr(_deploy, "_read_remote", read)
    monkeypatch.setattr(
        _deploy, "ensure_app_caddy_route",
        lambda *args, **kwargs: _caddy.ensure_app_caddy_route(*args, caddy_dir=str(ingress.root), **kwargs),
    )
    monkeypatch.setattr(
        _deploy, "remove_app_caddy_route",
        lambda *args, **kwargs: _caddy.remove_app_caddy_route(*args, caddy_dir=str(ingress.root), **kwargs),
    )
    for env_key in (
        "RESOURCE_PLANE_SSH_HOST",
        "RESOURCE_PLANE_SSH_USER",
        "RESOURCE_PLANE_SSH_PORT",
        "RESOURCE_PLANE_SSH_KEY",
        "RESOURCE_PLANE_REMOTE_DIR",
        "RESOURCE_PLANE_DOMAIN",
        "APPS_BASE_DOMAIN",
        "CLOUDFLARE_DNS_API_TOKEN",
        "CLOUDFLARE_API_TOKEN",
    ):
        monkeypatch.delenv(env_key, raising=False)
    monkeypatch.setenv("GH_ORG_NAME", "test-org")
    monkeypatch.setenv("GH_TOKEN", "unused-test-token")

    def project(name):
        directory = ingress.tmp_path / "local" / name
        directory.mkdir(parents=True)
        (directory / "package.json").write_text(json.dumps({"name": name}))
        (directory / "Dockerfile").write_text("FROM scratch\n")
        (directory / "docker-compose.yml").write_text("services:\n  web:\n    image: test\n")
        (directory / ".env").write_text("NODE_ENV=development\nBETTER_AUTH_SECRET=test\n")
        return directory

    def request(directory=None, **kwargs):
        return AppDeployRequest(
            target=str(directory) if directory else None, remote_base_dir=str(remote_base), **kwargs,
        )

    return SimpleNamespace(
        ingress=ingress, factory=factory, remote_base=remote_base,
        registry=registry, project=project, request=request,
    )
