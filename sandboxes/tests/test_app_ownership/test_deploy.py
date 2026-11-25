"""Deploy and down share identity checks and preserve ownership through retries."""

from concurrent.futures import ThreadPoolExecutor
import json

import pytest

from sandbox.app_deploy import deploy_app, teardown_app


def test_deploy_redeploy_and_purge_share_the_same_claim(apps):
    local = apps.project("demo")
    (local / "apps/web/drizzle").mkdir(parents=True)
    (local / "apps/web/drizzle/0000.sql").write_text("CREATE TABLE example (id int);")
    first = deploy_app(apps.request(local), repo_root=apps.factory)
    assert first.migrated
    assert apps.ingress.state()["migrations"] == 1
    assert first.url == "https://demo.apps.example.com"
    remote = apps.remote_base / "demo"
    assert "NODE_ENV=production" in (remote / ".env").read_text()
    assert "NODE_ENV=development" in (local / ".env").read_text()
    assert (apps.registry / "demo.json").is_file()
    second = deploy_app(apps.request(local, skip_migrate=True), repo_root=apps.factory)
    assert first.remote_dir == second.remote_dir
    assert not second.migrated
    result = teardown_app(apps.request(local), purge=True, repo_root=apps.factory)
    assert result.purged
    assert not remote.exists()
    assert not (apps.registry / "demo.json").exists()
    assert "demo-web" not in apps.ingress.state()["apps"]
    assert not (apps.ingress.root / "conf/apps/demo.caddy").exists()


@pytest.mark.parametrize("operation", ["deploy", "down"])
def test_names_that_normalize_alike_cannot_claim_existing_runtime(apps, operation):
    first = apps.project("notes_api")
    second = apps.project("notes-api")
    deploy_app(apps.request(first), repo_root=apps.factory)
    original = (apps.remote_base / "notes_api/.env").read_text()
    action = deploy_app if operation == "deploy" else teardown_app
    with pytest.raises(ValueError, match="already owned"):
        action(apps.request(second, subdomain="different"), repo_root=apps.factory)
    assert (apps.remote_base / "notes_api/.env").read_text() == original
    assert not (apps.remote_base / "notes-api").exists()
    assert apps.ingress.state()["apps"]["notes-api-web"]["running"]


def test_two_owners_cannot_claim_the_same_repository_name(apps):
    local = apps.project("demo")
    deploy_app(apps.request(local, repo="first-owner/demo"), repo_root=apps.factory)
    with pytest.raises(ValueError, match="already owned"):
        deploy_app(apps.request(local, repo="other-owner/demo"), repo_root=apps.factory)
    record = json.loads((apps.registry / "demo.json").read_text())
    assert record["owner"] == "first-owner"


def test_partial_deployment_retains_claim_for_safe_retry(apps):
    first = apps.project("notes_api")
    second = apps.project("notes-api")
    apps.ingress.state(fail_app_builds=1)
    with pytest.raises(RuntimeError, match="Docker build failed"):
        deploy_app(apps.request(first), repo_root=apps.factory)
    assert (apps.registry / "notes-api.json").is_file()
    with pytest.raises(ValueError, match="already owned"):
        deploy_app(apps.request(second), repo_root=apps.factory)
    result = deploy_app(apps.request(first), repo_root=apps.factory)
    assert result.repo_name == "notes_api"


def test_failed_down_cannot_purge_files_or_release_ownership(apps):
    local = apps.project("demo")
    deploy_app(apps.request(local), repo_root=apps.factory)
    apps.ingress.state(fail_app_stops=1)
    with pytest.raises(RuntimeError, match="Failed stopping"):
        teardown_app(apps.request(local), purge=True, repo_root=apps.factory)
    assert (apps.remote_base / "demo/docker-compose.yml").is_file()
    assert (apps.registry / "demo.json").is_file()
    assert (apps.ingress.root / "conf/apps/demo.caddy").is_file()
    teardown_app(apps.request(local), purge=True, repo_root=apps.factory)
    assert not (apps.registry / "demo.json").exists()


def test_failed_route_removal_keeps_files_and_claim_for_retry(apps):
    local = apps.project("demo")
    deploy_app(apps.request(local), repo_root=apps.factory)
    apps.ingress.state(fail_reloads=1)
    with pytest.raises(RuntimeError, match="rolled back"):
        teardown_app(apps.request(local), purge=True, repo_root=apps.factory)
    assert (apps.remote_base / "demo/docker-compose.yml").is_file()
    assert (apps.registry / "demo.json").is_file()
    teardown_app(apps.request(local), purge=True, repo_root=apps.factory)
    assert not (apps.remote_base / "demo").exists()


def test_concurrent_colliding_deployments_allow_one_owner(apps):
    projects = [apps.project("notes_api"), apps.project("notes-api")]

    def deploy(project):
        try:
            return deploy_app(apps.request(project), repo_root=apps.factory)
        except ValueError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(deploy, projects))
    assert sum(isinstance(result, ValueError) for result in results) == 1
    record = json.loads((apps.registry / "notes-api.json").read_text())
    assert record["remote_dir"] == apps.ingress.state()["apps"]["notes-api-web"]["labels"]["com.docker.compose.project.working_dir"]


def test_github_case_alias_uses_the_existing_directory(apps):
    original = apps.project("Demo")
    alias = apps.project("demo")
    deploy_app(apps.request(original, repo="test-org/Demo"), repo_root=apps.factory)
    result = deploy_app(apps.request(alias, repo="TEST-ORG/demo"), repo_root=apps.factory)
    assert result.remote_dir == str(apps.remote_base / "Demo")
    assert not (apps.remote_base / "demo").exists()
