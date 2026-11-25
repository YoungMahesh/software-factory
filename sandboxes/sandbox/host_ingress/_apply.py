"""Apply a complete Host Ingress Proxy change under one remote lock."""

from __future__ import annotations

from dataclasses import dataclass, field
import io
from pathlib import PurePosixPath
import shlex
import subprocess
import tarfile
from typing import Sequence

from sandbox.infra_deploy import VpsSshConfig, build_ssh_cmd


@dataclass
class IngressResult:
    success: bool
    changed: bool
    message: str
    files_written: list[str] = field(default_factory=list)
    files_deleted: list[str] = field(default_factory=list)


def _validate_path(path: str) -> None:
    relative = PurePosixPath(path)
    runtime_names = {"Dockerfile", "docker-compose.yml", "docker-compose.override.yml", ".env"}
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or relative.as_posix() != path
        or any(character in path for character in ("\n", "\r", "\0"))
        or not (path.startswith("conf/") or path in runtime_names)
    ):
        raise ValueError(f"Invalid Host Ingress Proxy file path: {path!r}")


def apply_configuration(
    vps_config: VpsSshConfig,
    files: dict[str, str],
    *,
    delete: Sequence[str] = (),
    defaults: Sequence[str] = (),
    prune: bool = False,
    bootstrap: bool = False,
    offline: bool = False,
    require_cloudflare: bool = False,
    require_sites_import: bool = False,
    route: tuple[str, str] | None = None,
    caddy_dir: str = "/opt/caddy",
    container_name: str = "caddy",
    network: str = "dbhost-network",
    timeout: int = 360,
) -> IngressResult:
    """Stage, compare, activate and recover a change before releasing the VPS lock.

    A durable journal lets the next operation recover an interrupted change.
    Configuration-only changes reload Caddy. Runtime changes also converge Compose.
    """
    for path in [*files, *delete, *defaults]:
        _validate_path(path)
    if set(files) & set(delete):
        raise ValueError("A Host Ingress Proxy file cannot be written and deleted together.")
    if not set(defaults) <= files.keys():
        raise ValueError("Default files must be included in the change.")
    if route is not None and (route[0] not in files or not route[0].startswith("conf/apps/")):
        raise ValueError("A Hosted App route claim must identify a route file in the change.")

    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        for path, content in sorted(files.items()):
            data = content.encode("utf-8")
            entry = tarfile.TarInfo(path)
            entry.size = len(data)
            entry.mode = 0o600 if path == ".env" else 0o644
            archive.addfile(entry, io.BytesIO(data))

    values = {
        "caddy_dir": caddy_dir,
        "container": container_name,
        "network": network,
        "bootstrap": str(int(bootstrap)),
        "offline": str(int(offline)),
        "prune": str(int(prune)),
        "require_cloudflare": str(int(require_cloudflare)),
        "require_sites_import": str(int(require_sites_import)),
        "route_path": route[0] if route else "",
        "route_host": route[1] if route else "",
    }
    header = "\n".join(f"{key}={shlex.quote(value)}" for key, value in values.items())
    for name, paths in (("wanted", sorted(files)), ("removed", delete), ("defaults", defaults)):
        header += f"\n{name}=({' '.join(shlex.quote(path) for path in paths)})"
    script = header + "\n" + _REMOTE_SCRIPT
    command = build_ssh_cmd(vps_config, f"bash -c {shlex.quote(script)}")
    try:
        result = subprocess.run(
            command, input=payload.getvalue(), timeout=timeout, capture_output=True, check=False,
        )
    except subprocess.TimeoutExpired:
        return IngressResult(
            False, False,
            "Host Ingress Proxy update timed out. The next operation will recover any pending change.",
        )
    except OSError as exc:
        return IngressResult(False, False, f"Host Ingress Proxy update could not run: {exc}")

    output = result.stdout.decode("utf-8", errors="replace")
    if result.returncode:
        error = result.stderr.decode("utf-8", errors="replace").strip()
        return IngressResult(False, False, f"Host Ingress Proxy update failed: {error or output.strip()}")
    if not {"FACTORY_CHANGED", "FACTORY_NOOP"}.intersection(output.splitlines()):
        return IngressResult(False, False, "Host Ingress Proxy update finished without confirming activation.")
    written = sorted(line.removeprefix("FACTORY_WRITTEN=") for line in output.splitlines() if line.startswith("FACTORY_WRITTEN="))
    deleted = sorted(line.removeprefix("FACTORY_DELETED=") for line in output.splitlines() if line.startswith("FACTORY_DELETED="))
    changed = "FACTORY_CHANGED" in output.splitlines()
    message = "Host Ingress Proxy updated and activated."
    if not changed:
        message = "Host Ingress Proxy is already up to date (reload skipped)."
    return IngressResult(True, changed, message, written, deleted)


_REMOTE_SCRIPT = r'''
set -Eeuo pipefail
umask 077
mkdir -p "$caddy_dir"
exec 9>"$caddy_dir/.factory-ingress.lock"
flock -w 30 9
pending="$caddy_dir/.factory-ingress-pending"
stage=""
active_stamp="$caddy_dir/.factory-ingress-active"

is_running() {
    [ "$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null)" = true ]
}

activate() {
    docker exec "$container" caddy validate --config /etc/caddy/Caddyfile &&
    docker exec -w /etc/caddy "$container" caddy reload --config /etc/caddy/Caddyfile
}

fingerprint() {
    (
        cd "$caddy_dir"
        {
            if [ -d conf ]; then
                find conf -type f ! -name '*.bak' ! -name '*.tmp' ! -name '*.swp' \
                    ! -name '*~' ! -name .gitkeep ! -name .DS_Store -print0
            fi
            printf '%s\0' Dockerfile docker-compose.yml docker-compose.override.yml .env
        } | sort -zu | while IFS= read -r -d '' path; do
            if [ -f "$path" ]; then sha256sum "$path"; else printf 'missing %s\n' "$path"; fi
        done
        docker inspect -f '{{.Id}} {{.State.StartedAt}}' "$container"
    ) | sha256sum | cut -d ' ' -f 1
}

mark_active() {
    fingerprint > "$active_stamp.tmp" && mv "$active_stamp.tmp" "$active_stamp"
}

recover() {
    local path failed=0
    while IFS= read -r path; do
        if [ -f "$pending/before/$path" ]; then
            mkdir -p "$(dirname "$caddy_dir/$path")" &&
                cp -p "$pending/before/$path" "$caddy_dir/$path" || failed=1
        else
            rm -f "$caddy_dir/$path" || failed=1
        fi
    done < "$pending/paths"
    [ "$failed" = 0 ] || return 1
    if [ -f "$pending/was-running" ]; then
        if [ -f "$pending/compose" ]; then
            if [ -s "$pending/image" ]; then
                printf 'services:\n  caddy:\n    image: %s\n' "$(cat "$pending/image")" > "$pending/recovery.yml"
                local compose=(docker compose -f "$caddy_dir/docker-compose.yml")
                if [ -f "$caddy_dir/docker-compose.override.yml" ]; then
                    compose+=(-f "$caddy_dir/docker-compose.override.yml")
                fi
                "${compose[@]}" -f "$pending/recovery.yml" up -d --no-build || return 1
            else
                (cd "$caddy_dir" && docker compose up -d) || return 1
            fi
        fi
        activate && mark_active || return 1
    elif is_running; then
        docker stop "$container" >/dev/null || return 1
    fi
}

cleanup() {
    local status=$?
    trap - EXIT HUP INT TERM
    if [ "$status" != 0 ] && [ -f "$pending/ready" ]; then
        if recover; then
            rm -rf "$pending"
            echo "Change failed and was rolled back." >&2
        else
            echo "Recovery failed. Previous files are retained at $pending; the next operation will retry recovery." >&2
        fi
    fi
    if [ -n "$stage" ]; then rm -rf "$stage"; fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

docker info >/dev/null

# Recover interrupted changes before equality checks.
if [ -f "$pending/ready" ]; then
    if recover; then
        rm -rf "$pending"
    else
        echo "Pending ingress change could not be recovered at $pending." >&2
        exit 1
    fi
fi
rm -rf "$pending"
stage=$(mktemp -d "$caddy_dir/.factory-ingress-stage-XXXXXXXX")
tar -xzf - -C "$stage"
for path in "${defaults[@]}"; do
    if [ -f "$caddy_dir/$path" ]; then rm -f "$stage/$path"; fi
done

running=0
if is_running; then running=1; fi
if [ "$running" = 0 ] && [ "$bootstrap" = 0 ] && [ "$offline" = 0 ]; then
    echo "Caddy is not running. Re-run with --bootstrap." >&2
    exit 1
fi
if [ "$running" = 0 ] && [ "$bootstrap" = 1 ]; then
    busy=$(docker ps --format '{{.Names}} {{.Ports}}' | grep -E ':(80|443)->' || true)
    if command -v ss >/dev/null 2>&1; then
        busy+=$(ss -H -lnt '( sport = :80 or sport = :443 )')
    fi
    if [ -n "$busy" ]; then
        echo "Ports 80/443 are already in use on the VPS." >&2
        exit 1
    fi
fi
if [ "$require_cloudflare" = 1 ]; then
    env_path="$caddy_dir/.env"
    if [ -f "$stage/.env" ]; then env_path="$stage/.env"; fi
    if ! grep -qE '^CLOUDFLARE_DNS_API_TOKEN=.+$' "$env_path" 2>/dev/null; then
        echo "Missing CLOUDFLARE_DNS_API_TOKEN for wildcard ingress." >&2
        exit 1
    fi
fi
if [ "$require_sites_import" = 1 ]; then
    config_path="$caddy_dir/conf/Caddyfile"
    if [ -f "$stage/conf/Caddyfile" ]; then config_path="$stage/conf/Caddyfile"; fi
    if ! grep -Eq '^[[:space:]]*import[[:space:]]+(/etc/caddy/)?sites/\*\.caddy([[:space:]]*(#.*)?)?$' "$config_path"; then
        echo "Caddyfile must contain 'import /etc/caddy/sites/*.caddy'." >&2
        exit 1
    fi
fi

written=()
deleted=()
if [ -n "$route_host" ]; then
    for path in "$caddy_dir"/conf/apps/*.caddy; do
        if [ ! -f "$path" ] || [ "$path" = "$caddy_dir/$route_path" ]; then continue; fi
        if awk -v host="$route_host" '
            $1 ~ /^@/ && $2 == "host" {
                for (field = 3; field <= NF; field++) {
                    if (tolower($field) == tolower(host)) found = 1
                }
            }
            END { exit !found }
        ' "$path"; then
            echo "Domain '$route_host' is already assigned by $path." >&2
            exit 1
        fi
    done
fi
for path in "${wanted[@]}"; do
    if [ -f "$stage/$path" ] && ! cmp -s "$stage/$path" "$caddy_dir/$path"; then written+=("$path"); fi
done
for path in "${removed[@]}"; do
    if [ -f "$caddy_dir/$path" ]; then deleted+=("$path"); fi
done
if [ "$prune" = 1 ]; then
    while IFS= read -r path; do
        if [ ! -f "$stage/$path" ]; then deleted+=("$path"); fi
    done < <(
        cd "$caddy_dir"
        if [ -d conf ]; then
            find conf -type f ! -path conf/Caddyfile ! -name '*.bak' ! -name '*.tmp' \
                ! -name '*.swp' ! -name '*~' ! -name .gitkeep ! -name .DS_Store | sort
        fi
    )
fi
build=0
compose=0
for path in "${written[@]}" "${deleted[@]}"; do
    case "$path" in
        Dockerfile) build=1; compose=1 ;;
        docker-compose.yml|docker-compose.override.yml|.env) compose=1 ;;
    esac
done
if [ "$require_cloudflare" = 1 ]; then
    modules=$(docker exec "$container" caddy list-modules 2>/dev/null || true)
    if ! grep -Fxq dns.providers.cloudflare <<< "$modules"; then
        build=1
        compose=1
    fi
fi
if [ "$running" = 0 ] && [ "$bootstrap" = 1 ]; then
    compose=1
    if [ -f "$stage/Dockerfile" ] || [ -f "$caddy_dir/Dockerfile" ]; then build=1; fi
fi
if [ "$running" = 1 ]; then
    docker network inspect "$network" >/dev/null 2>&1 || docker network create "$network" >/dev/null
    if ! docker inspect -f '{{json .NetworkSettings.Networks}}' "$container" | grep -Fq "\"$network\""; then
        docker network connect "$network" "$container"
    fi
fi
if [ -f "$caddy_dir/.env" ]; then chmod 600 "$caddy_dir/.env"; fi
if [ "${#written[@]}" = 0 ] && [ "${#deleted[@]}" = 0 ] && [ "$compose" = 0 ]; then
    if [ "$running" = 1 ] && { [ ! -f "$active_stamp" ] || [ "$(cat "$active_stamp")" != "$(fingerprint)" ]; }; then
        # Older deployments and out-of-band file edits have no activation proof.
        # No files have changed here, so a failed activation leaves no journal.
        activate
        mark_active
        echo FACTORY_CHANGED
        exit 0
    fi
    echo FACTORY_NOOP
    exit 0
fi

# Preserve directory and existing file inodes because Caddy bind-mounts them.
mkdir -p "$pending/before"
printf '%s\n' "${written[@]}" "${deleted[@]}" | sed '/^$/d' | sort -u > "$pending/paths"
while IFS= read -r path; do
    if [ -L "$caddy_dir/$path" ]; then
        echo "Managed ingress file is a symlink: $path" >&2
        exit 1
    fi
    if [ -f "$caddy_dir/$path" ]; then
        mkdir -p "$(dirname "$pending/before/$path")"
        cp -p "$caddy_dir/$path" "$pending/before/$path"
    fi
done < "$pending/paths"
if [ "$running" = 1 ]; then
    touch "$pending/was-running"
    docker inspect -f '{{.Image}}' "$container" > "$pending/image"
fi
if [ "$compose" = 1 ]; then touch "$pending/compose"; fi
touch "$pending/ready"
for path in "${written[@]}"; do
    mkdir -p "$(dirname "$caddy_dir/$path")"
    cp -p "$stage/$path" "$caddy_dir/$path"
done
for path in "${deleted[@]}"; do rm -f "$caddy_dir/$path"; done
if [ -f "$caddy_dir/.env" ]; then chmod 600 "$caddy_dir/.env"; fi
if [ "$running" = 1 ] || [ "$bootstrap" = 1 ]; then
    mkdir -p "$caddy_dir/conf/sites" "$caddy_dir/conf/apps"
    docker network inspect "$network" >/dev/null 2>&1 || docker network create "$network" >/dev/null
    if [ "$compose" = 1 ]; then
        flags=()
        if [ "$build" = 1 ]; then flags+=(--build); fi
        (cd "$caddy_dir" && docker compose up -d "${flags[@]}")
    fi
    if ! docker inspect -f '{{json .NetworkSettings.Networks}}' "$container" | grep -Fq "\"$network\""; then
        docker network connect "$network" "$container"
    fi
    activate
    mark_active
fi
rm -rf "$pending"
for path in "${written[@]}"; do printf 'FACTORY_WRITTEN=%s\n' "$path"; done
for path in "${deleted[@]}"; do printf 'FACTORY_DELETED=%s\n' "$path"; done
echo FACTORY_CHANGED
'''
