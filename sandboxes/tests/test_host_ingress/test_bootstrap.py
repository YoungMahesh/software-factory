"""Every bootstrap path stages a complete build context and isolated credentials."""

import shutil

from sandbox.caddy_deploy import bootstrap_caddy
from sandbox.caddy_store import restore_caddy_from_store
from sandbox.caddy_wildcard import ensure_wildcard_caddy


def test_plain_bootstrap_stages_dockerfile_and_is_idempotent(ingress):
    shutil.rmtree(ingress.root)
    ingress.state(running=False, cloudflare=False)
    ok, message = bootstrap_caddy(ingress.vps, caddy_config=ingress.config)
    assert ok, message
    assert (ingress.root / "Dockerfile").read_text() == (ingress.source / "Dockerfile").read_text()
    assert ingress.state()["running"]
    commands = ingress.state()["commands"]
    assert any("--build" in command for command in commands)
    starts = ingress.state()["starts"]
    ok, message = bootstrap_caddy(ingress.vps, caddy_config=ingress.config)
    assert ok and ingress.state()["starts"] == starts


def test_bootstrap_aborts_on_busy_ports_before_staging_runtime(ingress):
    shutil.rmtree(ingress.root)
    ingress.state(running=False, ports_busy=True)
    ok, message = bootstrap_caddy(ingress.vps, caddy_config=ingress.config)
    assert not ok and "already in use" in message
    assert not (ingress.root / "docker-compose.yml").exists()


def test_wildcard_upgrade_preserves_routes_and_keeps_token_outside_conf(ingress):
    ingress.state(cloudflare=False)
    existing = ingress.root / "conf/sites/existing.caddy"
    existing.write_text("existing.example.com {}")
    ok, message = ensure_wildcard_caddy(
        ingress.vps, "apps.example.com", "dns-test-token", caddy_dir=str(ingress.root),
    )
    assert ok, message
    assert ingress.state()["cloudflare"]
    assert existing.read_text() == "existing.example.com {}"
    assert (ingress.root / ".env").stat().st_mode & 0o777 == 0o600
    assert not any("dns-test-token" in path.read_text() for path in (ingress.root / "conf").rglob("*") if path.is_file())
    assert "conf/sites/apps-wildcard.caddy" in ingress.state()["active"]
    starts = ingress.state()["starts"]
    ok, message = ensure_wildcard_caddy(
        ingress.vps, "apps.example.com", "dns-test-token", caddy_dir=str(ingress.root),
    )
    assert ok and ingress.state()["starts"] == starts


def test_store_bootstrap_filters_networks_and_uses_shared_runtime(ingress, monkeypatch):
    stored = ingress.tmp_path / "stored"
    shutil.copytree(ingress.source / "conf", stored / "conf")
    (stored / "conf/sites/apps-wildcard.caddy").write_text("*.example.com {}")
    (stored / "docker-compose.override.yml").write_text(
        "services:\n  caddy:\n    networks:\n      - missing_net\n"
        "networks:\n  missing_net:\n    external: true\n"
    )
    shutil.rmtree(ingress.root)
    ingress.state(running=False, cloudflare=False)
    monkeypatch.setenv("CLOUDFLARE_DNS_API_TOKEN", "dns-test-token")
    result = restore_caddy_from_store(
        ingress.vps, from_dir=stored, bootstrap=True, caddy_dir=str(ingress.root),
    )
    assert result.success, result.message
    assert result.skipped_networks == ["missing_net"]
    assert (ingress.root / "Dockerfile").is_file()
    assert (ingress.root / ".env").stat().st_mode & 0o777 == 0o600
    assert not (ingress.root / "docker-compose.override.yml").exists()


def test_failed_upgrade_recovers_previous_runtime_and_routes(ingress):
    old_compose = (ingress.root / "docker-compose.yml").read_text()
    ingress.state(cloudflare=False, fail_starts=1)
    ok, message = ensure_wildcard_caddy(
        ingress.vps, "apps.example.com", "dns-test-token", caddy_dir=str(ingress.root),
    )
    assert not ok and "rolled back" in message
    assert ingress.state()["running"]
    assert (ingress.root / "docker-compose.yml").read_text() == old_compose
    assert not (ingress.root / "conf/sites/apps-wildcard.caddy").exists()
    assert not (ingress.root / ".env").exists()


def test_wildcard_store_restore_upgrades_a_running_proxy(ingress, monkeypatch):
    stored = ingress.tmp_path / "stored"
    shutil.copytree(ingress.source / "conf", stored / "conf")
    (stored / "conf/sites/apps-wildcard.caddy").write_text("*.example.com {}")
    ingress.state(cloudflare=False)
    monkeypatch.setenv("CLOUDFLARE_DNS_API_TOKEN", "dns-test-token")
    result = restore_caddy_from_store(ingress.vps, from_dir=stored, caddy_dir=str(ingress.root))
    assert result.success, result.message
    assert ingress.state()["cloudflare"]
    assert (ingress.root / ".env").stat().st_mode & 0o777 == 0o600
    assert "conf/sites/apps-wildcard.caddy" in ingress.state()["active"]


def test_unchanged_runtime_hardens_token_permissions_and_connects_network(ingress):
    ok, message = ensure_wildcard_caddy(
        ingress.vps, "apps.example.com", "dns-test-token", caddy_dir=str(ingress.root),
    )
    assert ok, message
    (ingress.root / ".env").chmod(0o644)
    ingress.state(networks=[])
    reloads = ingress.state()["reloads"]
    ok, message = ensure_wildcard_caddy(
        ingress.vps, "apps.example.com", "dns-test-token", caddy_dir=str(ingress.root),
    )
    assert ok, message
    assert (ingress.root / ".env").stat().st_mode & 0o777 == 0o600
    assert "dbhost-network" in ingress.state()["networks"]
    assert ingress.state()["reloads"] == reloads
