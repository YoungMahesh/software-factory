"""Run the production remote scripts against local files and a Docker adapter."""

import json
import os
from pathlib import Path
import shlex
import shutil
import sys
from types import SimpleNamespace

import pytest

from sandbox.caddy_deploy import CaddyConfig
from sandbox.infra_deploy import VpsSshConfig


@pytest.fixture
def ingress(tmp_path, monkeypatch):
    root = tmp_path / "caddy"
    source = Path(__file__).resolve().parents[3] / "resource-plane" / "caddy"
    shutil.copytree(source, root)
    state_path = tmp_path / "docker-state.json"
    state_path.write_text(json.dumps({
        "running": True, "cloudflare": True, "networks": ["dbhost-network"], "active": {},
    }))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker_fixture = Path(__file__).with_name("_docker.py")
    (bin_dir / "docker").write_text(
        f"#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(docker_fixture))} \"$@\"\n"
    )
    (bin_dir / "ss").write_text("#!/bin/sh\nexit 0\n")
    for executable in bin_dir.iterdir():
        executable.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("INGRESS_TEST_ROOT", str(root))
    monkeypatch.setenv("INGRESS_TEST_STATE", str(state_path))
    monkeypatch.delenv("CLOUDFLARE_DNS_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.setattr("sandbox.host_ingress._runtime.resolve_factory_root", lambda: tmp_path)
    monkeypatch.setattr("sandbox.caddy_store._sync.resolve_factory_root", lambda: tmp_path)
    for module in (
        "sandbox.host_ingress._apply",
        "sandbox.caddy_deploy",
        "sandbox.caddy_wildcard",
        "sandbox.caddy_store._vps",
    ):
        monkeypatch.setattr(f"{module}.build_ssh_cmd", lambda _config, cmd: ["bash", "-c", cmd])
    config = CaddyConfig(
        caddy_dir=str(root), caddyfile_path=str(root / "conf" / "Caddyfile"),
        sites_dir=str(root / "conf" / "sites"),
        site_path=str(root / "conf" / "sites" / "resource-plane.caddy"),
    )

    def state(**changes):
        current = json.loads(state_path.read_text())
        if changes:
            current.update(changes)
            state_path.write_text(json.dumps(current))
        return current

    return SimpleNamespace(
        root=root, source=source, state=state, config=config, tmp_path=tmp_path,
        vps=VpsSshConfig(host="unused.invalid", key_path=tmp_path / "unused-key"),
        bin_dir=bin_dir,
    )
