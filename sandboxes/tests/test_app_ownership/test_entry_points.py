"""Scaffolding, deployment and GitHub source mode use consistent app identity."""

from dataclasses import replace
import json
import shutil

import pytest

from sandbox.app_deploy import _deploy, deploy_app
from sandbox.app_deploy._cli import main as deploy_app_main
from sandbox.app_deploy._config import resolve_deploy_target
from sandbox.env_store import VaultBundle
from scripts.create_app import main as create_app_main


def test_create_app_and_deploy_app_work_without_github_owner(apps, monkeypatch):
    dotenv = apps.factory / ".env"
    dotenv.write_text("\n".join(
        line for line in dotenv.read_text().splitlines() if not line.startswith(("GH_ORG_NAME=", "GH_TOKEN="))
    ) + "\n")
    monkeypatch.delenv("GH_ORG_NAME")
    monkeypatch.delenv("GH_TOKEN")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("sandbox.app_scaffolder._cloud.resolve_factory_root", lambda: apps.factory)
    monkeypatch.setattr(_deploy, "resolve_factory_root", lambda: apps.factory)

    def deploy(request, **kwargs):
        return deploy_app(
            replace(request, remote_base_dir=str(apps.remote_base)), **kwargs,
        )

    monkeypatch.setattr("sandbox.app_deploy.deploy_app", deploy)
    monkeypatch.setattr("sandbox.app_deploy._cli.deploy_app", deploy)
    directory = apps.ingress.tmp_path / "new-app"
    result = create_app_main([
        str(directory), "--deploy", "--no-install", "--no-git", "--no-skills",
        "--no-db", "--no-auth", "--skip-migrate",
    ])
    assert result == 0
    assert json.loads((apps.registry / "new-app.json").read_text())["owner"] is None
    assert deploy_app_main([str(directory), "--skip-migrate"]) == 0
    assert json.loads((apps.registry / "new-app.json").read_text())["owner"] is None


def test_github_mode_pulls_vault_and_owns_the_deployed_repository(apps, monkeypatch):
    source = apps.project("demo")
    monkeypatch.setattr(_deploy, "resolve_sandbox_bundle", lambda *args, **kwargs: VaultBundle(env_dict={"BETTER_AUTH_SECRET": "vault-value"}))

    def sync(_config, owner, name, branch, remote_dir, token):
        assert (owner, name, branch) == ("test-org", "demo", "main")
        shutil.copytree(source, remote_dir, ignore=shutil.ignore_patterns(".env"))

    monkeypatch.setattr(_deploy, "sync_github_app_on_vps", sync)
    result = deploy_app(apps.request(repo="test-org/demo"), repo_root=apps.factory)
    assert result.source_mode == "github"
    assert "BETTER_AUTH_SECRET=vault-value" in (apps.remote_base / "demo/.env").read_text()
    assert json.loads((apps.registry / "demo.json").read_text())["owner"] == "test-org"


@pytest.mark.parametrize("repo", ["../demo", "owner/../demo", "owner/name/extra", "owner/name'"])
def test_invalid_app_names_are_rejected_before_host_operations(tmp_path, repo):
    with pytest.raises(ValueError, match="Invalid Hosted App"):
        resolve_deploy_target(repo=repo, cwd=tmp_path)
