"""VPS SSH tar transport, Docker network probing, and local directory I/O for caddy-store."""

from __future__ import annotations

import io
from pathlib import Path
import subprocess
import tarfile

from sandbox.infra_deploy import VpsSshConfig, build_ssh_cmd

from ._github import is_declarative_caddy_relpath

DEFAULT_CADDY_DIR = "/opt/caddy"


def extract_tar_bytes_to_dict(tar_gz_bytes: bytes) -> dict[str, str]:
    """Decodes a gzipped tar archive into {rel_path: utf8_text} for declarative Caddy files."""
    if not tar_gz_bytes:
        return {}
    files: dict[str, str] = {}
    with tarfile.open(fileobj=io.BytesIO(tar_gz_bytes), mode="r:gz") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            rel = member.name.lstrip("./")
            if not is_declarative_caddy_relpath(rel):
                continue
            extracted = tf.extractfile(member)
            if extracted is None:
                continue
            try:
                files[rel] = extracted.read().decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(f"Non-UTF-8 file in /opt/caddy cannot be stored as plaintext: {rel}") from exc
    return dict(sorted(files.items()))


def build_tar_gz_bytes(files: dict[str, str]) -> bytes:
    """Packages {rel_path: utf8_text} into an in-memory gzipped tar archive."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for rel, content in sorted(files.items()):
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=rel)
            info.size = len(data)
            info.mode = 0o644
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def fetch_vps_caddy_files(
    vps_config: VpsSshConfig,
    caddy_dir: str = DEFAULT_CADDY_DIR,
    timeout: int = 30,
) -> dict[str, str]:
    """Fetches declarative /opt/caddy/conf/ files and docker-compose.override.yml from VPS."""
    remote_script = (
        f"if [ ! -d '{caddy_dir}' ]; then exit 0; fi; "
        f"cd '{caddy_dir}' && {{ "
        f"[ -f docker-compose.override.yml ] && printf '%s\\n' 'docker-compose.override.yml'; "
        f"[ -d conf ] && find conf -type f ! -name '*.bak' ! -name '*.tmp' ! -name '*.swp' ! -name '*~' ! -name '.gitkeep' ! -name '.DS_Store' | sort; "
        f"}} | {{ list=$(cat); [ -n \"$list\" ] && printf '%s\\n' \"$list\" | tar -czf - -T -; }}"
    )
    res = subprocess.run(
        build_ssh_cmd(vps_config, remote_script),
        timeout=timeout,
        capture_output=True,
        check=False,
    )
    if res.returncode != 0:
        err = res.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Failed reading {caddy_dir} from VPS: {err}")
    return extract_tar_bytes_to_dict(res.stdout)


def list_remote_docker_networks(vps_config: VpsSshConfig, timeout: int = 20) -> set[str]:
    """Returns the set of Docker network names currently existing on the target VPS."""
    res = subprocess.run(
        build_ssh_cmd(vps_config, "docker network ls --format '{{.Name}}'"),
        timeout=timeout,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(f"Failed listing Docker networks on VPS: {res.stderr.strip()}")
    return {line.strip() for line in res.stdout.splitlines() if line.strip()}


def read_local_caddy_dir(local_dir: Path) -> dict[str, str]:
    """Reads declarative Caddy files from a local directory."""
    if not local_dir.is_dir():
        raise FileNotFoundError(f"Local Caddy directory not found: {local_dir}")
    files: dict[str, str] = {}
    for path in sorted(local_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(local_dir).as_posix()
        if is_declarative_caddy_relpath(rel):
            files[rel] = path.read_text(encoding="utf-8")
    return files


def write_local_caddy_dir(local_dir: Path, files: dict[str, str]) -> None:
    """Mirrors declarative Caddy files into a local directory for inspection."""
    local_dir.mkdir(parents=True, exist_ok=True)
    for rel, content in sorted(files.items()):
        if not is_declarative_caddy_relpath(rel):
            continue
        dest = (local_dir / rel).resolve()
        if local_dir.resolve() not in dest.parents:
            raise ValueError(f"Unsafe relative path: {rel}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")


def apply_files_to_vps(
    vps_config: VpsSshConfig,
    files_to_write: dict[str, str],
    files_to_delete: list[str],
    caddy_dir: str = DEFAULT_CADDY_DIR,
    timeout: int = 45,
) -> None:
    """Streams updated files via tar over SSH and deletes specified relative paths."""
    if files_to_write:
        payload = build_tar_gz_bytes(files_to_write)
        p_ssh = subprocess.run(
            build_ssh_cmd(vps_config, f"mkdir -p '{caddy_dir}' && tar -xzf - -C '{caddy_dir}'"),
            input=payload,
            timeout=timeout,
            capture_output=True,
            check=False,
        )
        if p_ssh.returncode != 0:
            err = p_ssh.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Failed transferring Caddy files to {caddy_dir}: {err}")

    if files_to_delete:
        rm_args = " ".join(f"'{caddy_dir}/{p}'" for p in files_to_delete if is_declarative_caddy_relpath(p))
        if rm_args:
            res = subprocess.run(
                build_ssh_cmd(vps_config, f"rm -f {rm_args}"),
                timeout=timeout,
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode != 0:
                raise RuntimeError(f"Failed removing pruned Caddy files: {res.stderr.strip()}")
