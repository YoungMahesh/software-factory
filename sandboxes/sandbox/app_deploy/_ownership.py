"""Hosted App ownership, legacy adoption and serialization on the target VPS."""

from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import PurePosixPath
import select
import shlex
import subprocess
import tempfile

from sandbox.infra_deploy import VpsSshConfig, build_ssh_cmd

from ._caddy import check_app_route_collision
from ._config import DeployTarget, GITHUB_REMOTE_RE

REGISTRY_DIR = "/opt/caddy/.factory-apps"
APPS_DIR = "/opt/caddy/conf/apps"


def _remote(config: VpsSshConfig, command: str, *, content: str | None = None) -> str:
    result = subprocess.run(
        build_ssh_cmd(config, command), input=content, timeout=30,
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise RuntimeError(f"Hosted App ownership check failed: {result.stderr.strip()}")
    return result.stdout


@contextmanager
def _deployment_lock(config: VpsSshConfig):
    """Keep the host lock through the full deployment, including its SSH calls."""
    directory = shlex.quote(REGISTRY_DIR)
    lock_path = shlex.quote(f"{REGISTRY_DIR}/.lock")
    script = (
        f"umask 077; mkdir -p {directory} && exec 9>{lock_path} && "
        "flock -w 30 9 && printf 'FACTORY_LOCKED\\n' && cat >/dev/null"
    )
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            build_ssh_cmd(config, script), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=errors,
        )
        try:
            ready, _, _ = select.select([process.stdout], [], [], 45)
            if not ready or process.stdout.readline() != b"FACTORY_LOCKED\n":
                errors.seek(0)
                detail = errors.read().decode("utf-8", errors="replace").strip()
                raise RuntimeError(f"Could not acquire Hosted App deployment lock. {detail}")
            yield process
            if process.poll() is not None:
                raise RuntimeError("Hosted App deployment lock was lost. Verify the host state before retrying.")
        finally:
            if process.stdin:
                process.stdin.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            if process.stdout:
                process.stdout.close()


def _read_record(config: VpsSshConfig, record_path: str) -> dict | None:
    quoted = shlex.quote(record_path)
    output = _remote(config, f"if [ -e {quoted} ]; then printf 'EXISTS\\n'; cat {quoted}; fi")
    if not output:
        return None
    return _decode_record(output.partition("\n")[2], record_path)


def _decode_record(content: str, location: str) -> dict:
    try:
        record = json.loads(content)
        required = {"version", "repo_name", "owner", "app_slug", "remote_dir", "container_name"}
        if not isinstance(record, dict) or not required <= record.keys() or record["version"] != 1:
            raise ValueError("unsupported ownership metadata")
        for name in required - {"version", "owner"}:
            if not isinstance(record[name], str) or not record[name]:
                raise ValueError(f"invalid {name}")
        if record["owner"] is not None and not isinstance(record["owner"], str):
            raise ValueError("invalid repository owner")
        stored = DeployTarget(
            source_mode="local", bare_repo=record["repo_name"],
            app_slug=record["app_slug"], org_name=record["owner"],
        )
        directory = PurePosixPath(record["remote_dir"])
        stored.remote_directory(str(directory.parent))
        if not directory.is_absolute() or ".." in directory.parts:
            raise ValueError("invalid deployment directory")
        same_name = directory.name == record["repo_name"]
        if record["owner"]:
            same_name = directory.name.lower() == record["repo_name"].lower()
        if not same_name:
            raise ValueError("deployment directory belongs to another app")
        if any(character in record["remote_dir"] for character in ("'", "\n", "\r", "\0")):
            raise ValueError("invalid deployment directory")
        return record
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid Hosted App ownership metadata at {location}: {exc}") from exc


def _inspect_deployment(config: VpsSshConfig, remote_dir: str, container_name: str, app_slug: str) -> dict:
    directory = shlex.quote(remote_dir)
    container = shlex.quote(container_name)
    route = shlex.quote(f"{APPS_DIR}/{app_slug}.caddy")
    script = (
        "set -eu; "
        f"if [ -d {directory} ]; then "
        f"  printf 'DIRECTORY='; (cd {directory} && pwd -P); "
        f"  if [ -n \"$(find {directory} -mindepth 1 -maxdepth 1 -print -quit)\" ]; then echo NONEMPTY; fi; "
        f"  if [ -e {directory}/.git ]; then "
        f"    origin=$(git -C {directory} remote get-url origin) || exit 1; "
        "    printf 'ORIGIN='; printf '%s' \"$origin\" | base64 -w0; printf '\\n'; "
        "  fi; "
        "fi; "
        "containers=$(docker ps -a --format '{{.Names}}') || exit 1; "
        f"if printf '%s\\n' \"$containers\" | grep -Fxq {container}; then "
        f"  printf 'LABELS='; docker inspect -f '{{{{json .Config.Labels}}}}' {container}; "
        "fi; "
        f"if [ -f {route} ]; then echo ROUTE; "
        f"  sed -n 's/^# Hosted App ownership: /RECEIPT=/p' {route}; fi"
    )
    evidence = {
        "nonempty": False, "route": False, "labels": None,
        "origin": "", "directory": "", "receipt": None,
    }
    for line in _remote(config, script).splitlines():
        if line == "NONEMPTY":
            evidence["nonempty"] = True
        elif line == "ROUTE":
            evidence["route"] = True
        elif line.startswith("DIRECTORY="):
            evidence["directory"] = line.removeprefix("DIRECTORY=")
        elif line.startswith("ORIGIN="):
            evidence["origin"] = base64.b64decode(line.removeprefix("ORIGIN=")).decode("utf-8")
        elif line.startswith("LABELS="):
            evidence["labels"] = json.loads(line.removeprefix("LABELS=")) or {}
        elif line.startswith("RECEIPT="):
            evidence["receipt"] = _decode_record(line.removeprefix("RECEIPT="), f"{APPS_DIR}/{app_slug}.caddy")
    return evidence


def _verify_existing(target: DeployTarget, remote_dir: str, evidence: dict, recorded: bool) -> None:
    directory = evidence["directory"]
    if directory and PurePosixPath(directory) != PurePosixPath(remote_dir):
        raise ValueError(f"Hosted App directory resolves to another location: {remote_dir}")
    labels = evidence["labels"]
    if labels is not None:
        working_dir = labels.get("com.docker.compose.project.working_dir", "")
        project = labels.get("com.docker.compose.project", "")
        if project != target.app_slug or PurePosixPath(working_dir) != PurePosixPath(remote_dir):
            raise ValueError(f"Hosted App container '{target.app_slug}-web' is owned by another deployment.")
    origin = evidence["origin"]
    if origin:
        match = GITHUB_REMOTE_RE.search(origin.strip())
        if not match or match.group(2).lower() != target.bare_repo.lower():
            raise ValueError("Existing Hosted App checkout identifies a different repository.")
        if target.org_name and match.group(1).lower() != target.org_name.lower():
            raise ValueError("Existing Hosted App checkout identifies a different repository owner.")
    if recorded:
        return
    existing = evidence["nonempty"] or evidence["route"] or labels is not None
    if existing and labels is None and not origin:
        raise ValueError(
            f"Cannot verify ownership of the existing Hosted App at {remote_dir}. "
            "Its directory and route lack matching container or repository evidence."
        )


def _owned_directory(target: DeployTarget, remote_dir: str, record: dict | None) -> str:
    if record is None:
        return remote_dir
    requested_owner = (target.org_name or "").lower()
    owner = (record["owner"] or "").lower()
    name_matches = record["repo_name"] == target.bare_repo
    if owner and requested_owner:
        name_matches = record["repo_name"].lower() == target.bare_repo.lower()
    if (
        not name_matches
        or owner != requested_owner
        or record["app_slug"] != target.app_slug
        or record["container_name"] != f"{target.app_slug}-web"
        or PurePosixPath(record["remote_dir"]).parent != PurePosixPath(remote_dir).parent
    ):
        raise ValueError(f"Hosted App name '{target.app_slug}' is already owned by another deployment.")
    return record["remote_dir"]


@dataclass
class HostedAppOwnership:
    config: VpsSshConfig
    remote_dir: str
    record_path: str
    lock: subprocess.Popen
    metadata: dict

    def ensure_locked(self) -> None:
        if self.lock.poll() is not None:
            raise RuntimeError("Hosted App deployment lock was lost.")

    def forget(self) -> None:
        """Release an app name only after a completed purge."""
        self.ensure_locked()
        _remote(self.config, f"rm -f {shlex.quote(self.record_path)}")


@contextmanager
def claim_hosted_app(
    config: VpsSshConfig,
    target: DeployTarget,
    remote_dir: str,
    *,
    domain: str | None = None,
    create: bool = True,
):
    """Verify or adopt ownership before allowing any deployment mutations.

    Claims persist across interrupted deployments so retries cannot be mistaken
    for another app. Purge releases the claim after stack and route removal.
    """
    record_path = f"{REGISTRY_DIR}/{target.app_slug}.json"
    with _deployment_lock(config) as lock:
        registered = _read_record(config, record_path)
        previous = registered
        remote_dir = _owned_directory(target, remote_dir, previous)
        evidence = _inspect_deployment(config, remote_dir, f"{target.app_slug}-web", target.app_slug)
        if evidence["receipt"] is not None:
            restored_dir = _owned_directory(target, remote_dir, evidence["receipt"])
            if restored_dir != remote_dir:
                if registered is not None:
                    raise ValueError("Hosted App registry and restored route identify different directories.")
                remote_dir = restored_dir
                evidence = _inspect_deployment(config, remote_dir, f"{target.app_slug}-web", target.app_slug)
            if previous is None:
                previous = evidence["receipt"]
        _verify_existing(target, remote_dir, evidence, previous is not None)
        if domain:
            ok, message = check_app_route_collision(config, target.app_slug, domain, apps_dir=APPS_DIR)
            if not ok:
                raise ValueError(message)
        record = {
            "version": 1, "repo_name": target.bare_repo, "owner": target.org_name,
            "app_slug": target.app_slug, "remote_dir": remote_dir,
            "container_name": f"{target.app_slug}-web",
        }
        ownership = HostedAppOwnership(config, remote_dir, record_path, lock, record)
        ownership.ensure_locked()
        existing = evidence["nonempty"] or evidence["route"] or evidence["labels"] is not None
        if record != registered and (create or previous is not None or existing):
            quoted = shlex.quote(record_path)
            _remote(
                config,
                f"umask 077; cat > {quoted}.tmp && mv {quoted}.tmp {quoted}",
                content=json.dumps(record, sort_keys=True) + "\n",
            )
        yield ownership
