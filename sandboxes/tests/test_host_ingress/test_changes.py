"""Regression coverage for activation, rollback, retries, merge and prune."""

from concurrent.futures import ThreadPoolExecutor
import shlex

from sandbox.app_deploy._caddy import ensure_app_caddy_route, remove_app_caddy_route, render_app_route
from sandbox.caddy_deploy import render_resource_plane_site, setup_reverse_proxy
from sandbox.caddy_store import restore_caddy_from_store
from sandbox.host_ingress import apply_configuration


def test_route_reload_failure_recovers_and_identical_retry_activates(ingress):
    site = ingress.root / "conf/sites/resource-plane.caddy"
    site.write_text("old.example.com {\n reverse_proxy old:3000\n}\n")
    ingress.state(active={"conf/sites/resource-plane.caddy": site.read_text()}, fail_reloads=1)
    ok, message = setup_reverse_proxy(ingress.vps, domain="new.example.com", caddy_config=ingress.config)
    assert not ok and "rolled back" in message
    assert "old.example.com" in site.read_text()
    assert "old.example.com" in ingress.state()["active"]["conf/sites/resource-plane.caddy"]
    ok, message = setup_reverse_proxy(ingress.vps, domain="new.example.com", caddy_config=ingress.config)
    assert ok, message
    assert site.read_text() == render_resource_plane_site("new.example.com")
    assert ingress.state()["active"]["conf/sites/resource-plane.caddy"] == site.read_text()
    reloads = ingress.state()["reloads"]
    ok, message = setup_reverse_proxy(ingress.vps, domain="new.example.com", caddy_config=ingress.config)
    assert ok and "reload skipped" in message
    assert ingress.state()["reloads"] == reloads


def test_validation_failure_restores_files_and_bind_mount_inodes(ingress):
    caddyfile = ingress.root / "conf/Caddyfile"
    original = caddyfile.read_text()
    inode = caddyfile.stat().st_ino
    result = apply_configuration(
        ingress.vps, {"conf/Caddyfile": "INVALID", "conf/sites/new.caddy": "new"},
        caddy_dir=str(ingress.root),
    )
    assert not result.success and "rolled back" in result.message
    assert caddyfile.read_text() == original
    assert caddyfile.stat().st_ino == inode
    assert not (ingress.root / "conf/sites/new.caddy").exists()


def test_failed_recovery_is_retained_and_completed_before_retry(ingress):
    ingress.state(fail_reloads=2)
    result = apply_configuration(ingress.vps, {"conf/sites/new.caddy": "new"}, caddy_dir=str(ingress.root))
    assert not result.success and "Recovery failed" in result.message
    assert (ingress.root / ".factory-ingress-pending/ready").is_file()
    retry = apply_configuration(ingress.vps, {"conf/sites/new.caddy": "new"}, caddy_dir=str(ingress.root))
    assert retry.success, retry.message
    assert ingress.state()["active"]["conf/sites/new.caddy"] == "new"
    assert not (ingress.root / ".factory-ingress-pending").exists()


def test_hosted_app_removal_rolls_back_failed_reload(ingress):
    (ingress.root / "conf/sites/apps-wildcard.caddy").write_text("*.example.com {}")
    ok, message = ensure_app_caddy_route(
        ingress.vps, "demo", "demo.example.com", "demo-web:3000", caddy_dir=str(ingress.root),
    )
    assert ok, message
    route = ingress.root / "conf/apps/demo.caddy"
    previous = route.read_text()
    ingress.state(fail_reloads=1)
    ok, message = remove_app_caddy_route(ingress.vps, "demo", caddy_dir=str(ingress.root))
    assert not ok and "rolled back" in message
    assert route.read_text() == previous
    assert ingress.state()["active"]["conf/apps/demo.caddy"] == previous
    ok, message = remove_app_caddy_route(ingress.vps, "demo", caddy_dir=str(ingress.root))
    assert ok, message
    assert not route.exists()
    assert "conf/apps/demo.caddy" not in ingress.state()["active"]


def test_store_restore_merges_prunes_and_activates_compose_changes(ingress):
    stored = ingress.tmp_path / "stored"
    (stored / "conf/sites").mkdir(parents=True)
    (stored / "conf/Caddyfile").write_text((ingress.root / "conf/Caddyfile").read_text())
    (stored / "conf/sites/restored.caddy").write_text("restored.example.com {}")
    (ingress.root / "conf/sites/extra.caddy").write_text("extra.example.com {}")
    (stored / "docker-compose.override.yml").write_text(
        "services:\n  caddy:\n    environment:\n      EXTRA: value\n"
    )
    result = restore_caddy_from_store(ingress.vps, from_dir=stored, caddy_dir=str(ingress.root))
    assert result.success, result.message
    assert (ingress.root / "conf/sites/extra.caddy").exists()
    assert ingress.state()["active"]["conf/sites/restored.caddy"] == "restored.example.com {}"
    assert ingress.state()["starts"] == 1
    reloads = ingress.state()["reloads"]
    result = restore_caddy_from_store(ingress.vps, from_dir=stored, caddy_dir=str(ingress.root))
    assert result.success and not result.changed
    assert ingress.state()["reloads"] == reloads
    result = restore_caddy_from_store(ingress.vps, from_dir=stored, prune=True, caddy_dir=str(ingress.root))
    assert result.success and result.files_deleted == ["conf/sites/extra.caddy"]
    assert "conf/sites/extra.caddy" not in ingress.state()["active"]


def test_partial_copy_failure_recovers_entire_store_change(ingress):
    stored = ingress.tmp_path / "stored"
    (stored / "conf/sites").mkdir(parents=True)
    for name in ("first", "second"):
        (stored / f"conf/sites/{name}.caddy").write_text(f"{name}.example.com {{}}")
        (ingress.root / f"conf/sites/{name}.caddy").write_text(f"old-{name}")
    marker = ingress.tmp_path / "fail-copy"
    marker.touch()
    copy = ingress.bin_dir / "cp"
    copy.write_text(
        "#!/bin/bash\n"
        f"if [[ \"$2\" == *stage-*/conf/sites/second.caddy ]] && [ -f {shlex.quote(str(marker))} ]; then\n"
        f"  rm {shlex.quote(str(marker))}; exit 1\nfi\n"
        'exec /usr/bin/cp "$@"\n'
    )
    copy.chmod(0o755)
    result = restore_caddy_from_store(ingress.vps, from_dir=stored, caddy_dir=str(ingress.root))
    assert not result.success and "rolled back" in result.message
    for name in ("first", "second"):
        assert (ingress.root / f"conf/sites/{name}.caddy").read_text() == f"old-{name}"
    retry = restore_caddy_from_store(ingress.vps, from_dir=stored, caddy_dir=str(ingress.root))
    assert retry.success, retry.message


def test_concurrent_changes_serialize_without_losing_routes(ingress):
    def update(name):
        return apply_configuration(
            ingress.vps, {f"conf/sites/{name}.caddy": f"{name}.example.com {{}}"},
            caddy_dir=str(ingress.root),
        )
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(update, ["first", "second"]))
    assert all(result.success for result in results), [result.message for result in results]
    assert "conf/sites/first.caddy" in ingress.state()["active"]
    assert "conf/sites/second.caddy" in ingress.state()["active"]


def test_concurrent_route_claims_cannot_publish_the_same_domain(ingress):
    def update(name):
        path = f"conf/apps/{name}.caddy"
        return apply_configuration(
            ingress.vps, {path: render_app_route(name, "shared.example.com", f"{name}:3000")},
            route=(path, "shared.example.com"), caddy_dir=str(ingress.root),
        )
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(update, ["first", "second"]))
    assert sum(result.success for result in results) == 1
    assert "already assigned" in next(result.message for result in results if not result.success)


def test_unconfirmed_remote_exit_cannot_report_success(ingress, monkeypatch):
    monkeypatch.setattr("sandbox.host_ingress._apply.build_ssh_cmd", lambda *_args: ["bash", "-c", "exit 0"])
    result = apply_configuration(
        ingress.vps, {"conf/sites/new.caddy": "new.example.com {}"}, caddy_dir=str(ingress.root),
    )
    assert not result.success
    assert not (ingress.root / "conf/sites/new.caddy").exists()


def test_unavailable_docker_daemon_cannot_be_treated_as_a_fresh_host(ingress):
    ingress.state(daemon_unavailable=True)
    result = apply_configuration(
        ingress.vps, {"conf/sites/new.caddy": "new.example.com {}"},
        bootstrap=True, caddy_dir=str(ingress.root),
    )
    assert not result.success
    assert not (ingress.root / "conf/sites/new.caddy").exists()


def test_preexisting_disk_match_without_activation_proof_is_reloaded(ingress):
    site = ingress.root / "conf/sites/resource-plane.caddy"
    desired = render_resource_plane_site("new.example.com")
    site.write_text(desired)
    ingress.state(active={"conf/sites/resource-plane.caddy": "old route"})
    ok, message = setup_reverse_proxy(ingress.vps, domain="new.example.com", caddy_config=ingress.config)
    assert ok, message
    assert ingress.state()["active"]["conf/sites/resource-plane.caddy"] == desired
    reloads = ingress.state()["reloads"]
    ok, message = setup_reverse_proxy(ingress.vps, domain="new.example.com", caddy_config=ingress.config)
    assert ok and ingress.state()["reloads"] == reloads
