"""Existing deployments are adopted only when the available evidence agrees."""

import json
import shutil
import subprocess

import pytest

from sandbox.app_deploy import deploy_app, teardown_app


@pytest.mark.parametrize("operation", ["deploy", "down"])
def test_legacy_app_with_matching_container_is_adopted(apps, operation):
    local = apps.project("demo")
    deploy_app(apps.request(local), repo_root=apps.factory)
    (apps.registry / "demo.json").unlink()
    action = deploy_app if operation == "deploy" else teardown_app
    action(apps.request(local), repo_root=apps.factory)
    record = json.loads((apps.registry / "demo.json").read_text())
    assert record["remote_dir"] == str(apps.remote_base / "demo")
    assert record["repo_name"] == "demo"


@pytest.mark.parametrize("operation", ["deploy", "down"])
def test_legacy_slug_collision_is_rejected_using_container_labels(apps, operation):
    original = apps.project("notes_api")
    other = apps.project("notes-api")
    deploy_app(apps.request(original), repo_root=apps.factory)
    (apps.registry / "notes-api.json").unlink()
    action = deploy_app if operation == "deploy" else teardown_app
    with pytest.raises(ValueError, match="owned by another deployment|already owned"):
        action(apps.request(other), repo_root=apps.factory)
    assert apps.ingress.state()["apps"]["notes-api-web"]["running"]
    assert not (apps.registry / "notes-api.json").exists()


def test_available_repository_evidence_must_agree_with_legacy_app(apps):
    local = apps.project("demo")
    deploy_app(apps.request(local), repo_root=apps.factory)
    (apps.registry / "demo.json").unlink()
    remote = apps.remote_base / "demo"
    subprocess.run(["git", "init", "-q", str(remote)], check=True)
    subprocess.run(["git", "-C", str(remote), "remote", "add", "origin", "https://github.com/other-owner/demo.git"], check=True)
    with pytest.raises(ValueError, match="different repository owner"):
        teardown_app(apps.request(local), purge=True, repo_root=apps.factory)
    assert (remote / "docker-compose.yml").is_file()
    assert not (apps.registry / "demo.json").exists()


def test_orphaned_directory_without_verifiable_evidence_is_ambiguous(apps):
    local = apps.project("demo")
    remote = apps.remote_base / "demo"
    shutil.copytree(local, remote)
    with pytest.raises(ValueError, match="Cannot verify ownership"):
        teardown_app(apps.request(local), purge=True, repo_root=apps.factory)
    assert (remote / "docker-compose.yml").is_file()
    assert not (apps.registry / "demo.json").exists()


def test_invalid_ownership_directory_cannot_redirect_purge(apps):
    local = apps.project("demo")
    deploy_app(apps.request(local), repo_root=apps.factory)
    receipt = apps.registry / "demo.json"
    record = json.loads(receipt.read_text())
    record["remote_dir"] = str(apps.remote_base / "../victim")
    receipt.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="Invalid Hosted App ownership metadata"):
        teardown_app(apps.request(local), purge=True, repo_root=apps.factory)
    assert (apps.remote_base / "demo/docker-compose.yml").is_file()


def test_ownership_in_restored_route_allows_redeployment_on_a_rebuilt_host(apps):
    local = apps.project("demo")
    deploy_app(apps.request(local), repo_root=apps.factory)
    (apps.registry / "demo.json").unlink()
    shutil.rmtree(apps.remote_base / "demo")
    apps.ingress.state(apps={})
    result = deploy_app(apps.request(local), repo_root=apps.factory)
    assert result.repo_name == "demo"
    assert (apps.registry / "demo.json").is_file()
    assert apps.ingress.state()["apps"]["demo-web"]["running"]


def test_down_of_a_missing_app_does_not_reserve_its_name(apps):
    teardown_app(apps.request(repo="test-org/missing"), repo_root=apps.factory)
    assert not (apps.registry / "missing.json").exists()
