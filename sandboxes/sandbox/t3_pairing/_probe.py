"""In-sandbox runtime probing, tunnel discovery, and pairing record persistence."""

from __future__ import annotations

import json
import logging
from typing import Any

from sandbox.core import DEFAULT_T3_PORT

logger = logging.getLogger(__name__)

T3_BASE_DIR = "/root/.t3"
T3_PAIRING_FILE = "/tmp/t3-pairing.json"
T3_PAIRING_LINKS_FILE = "/tmp/t3-pairing-links.json"

# Reads T3 server runtime, public URL, file-stored tokens, and statev2.sqlite auth_pairing_links in one exec.
# Reading statev2.sqlite gives authoritative consumed_at/revoked_at/expires_at and catches `t3 pair` CLI tokens,
# since `t3 auth pairing list` omits credentials after creation.
_PROBE_T3_PAIRING_SCRIPT = r"""
import json, os, sqlite3

def read_json(path):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def parse_port(val):
    try:
        p = int(val)
        return p if p > 0 else None
    except Exception:
        return None

runtime = read_json("/root/.t3/userdata/server-runtime.json")
runtime_present = isinstance(runtime, dict)
runtime_port = parse_port(runtime.get("port")) if runtime_present else None
dev_url = runtime.get("devUrl") if runtime_present and isinstance(runtime.get("devUrl"), str) else None
env_t3_port = parse_port(os.environ.get("T3_PORT"))

server_running = None
if runtime_present:
    pid = runtime.get("pid")
    if isinstance(pid, int) and pid > 0:
        server_running = os.path.isdir(f"/proc/{pid}")
    if server_running is False and os.path.isdir("/proc"):
        for name in os.listdir("/proc"):
            if not name.isdigit():
                continue
            try:
                cmd = open(f"/proc/{name}/cmdline", "rb").read().decode("utf-8", "ignore").split("\x00")
            except Exception:
                continue
            if any(os.path.basename(arg) == "t3" for arg in cmd[:2]) and "serve" in cmd:
                server_running = True
                break

public_url = None
if os.path.isfile("/root/.t3/public_url"):
    try:
        raw_pub = open("/root/.t3/public_url", "r", encoding="utf-8").read().strip()
        if raw_pub:
            public_url = raw_pub
    except Exception:
        pass

boot_record = read_json("/tmp/t3-pairing.json")
saved_raw = read_json("/tmp/t3-pairing-links.json")
saved_links = saved_raw if isinstance(saved_raw, list) else []

db_rows = []
db_readable = False
db_path = "/root/.t3/userdata/statev2.sqlite"
if os.path.isfile(db_path):
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT id, credential, label, created_at, expires_at, consumed_at, revoked_at "
            "FROM auth_pairing_links ORDER BY created_at ASC"
        )
        db_rows = [dict(row) for row in cur.fetchall()]
        conn.close()
        db_readable = True
    except Exception:
        pass

print(json.dumps({
    "runtime_present": runtime_present,
    "runtime_port": runtime_port,
    "env_t3_port": env_t3_port,
    "dev_url": dev_url,
    "public_url": public_url,
    "server_running": server_running,
    "boot_record": boot_record if isinstance(boot_record, dict) else None,
    "saved_links": saved_links,
    "db_readable": db_readable,
    "db_rows": db_rows,
}))
""".strip()

_APPEND_PAIRING_LINK_SCRIPT = r"""
import json, os, sys

path = "/tmp/t3-pairing-links.json"
entry = json.loads(sys.argv[1])
existing = []
if os.path.isfile(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            parsed = json.load(f)
        if isinstance(parsed, list):
            existing = [item for item in parsed if isinstance(item, dict)]
    except Exception:
        existing = []

entry_id = entry.get("id")
entry_cred = entry.get("credential")
filtered = [
    item for item in existing
    if not (
        (entry_id and item.get("id") == entry_id)
        or (entry_cred and item.get("credential") == entry_cred)
    )
]
filtered.append(entry)
tmp = f"{path}.tmp.{os.getpid()}"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(filtered, f, indent=2)
    f.write("\n")
os.chmod(tmp, 0o600)
os.replace(tmp, path)
""".strip()


def exec_json(sb: Any, *args: str, timeout: int = 20) -> Any:
    """Executes a sandbox command and parses stdout JSON."""
    proc = sb.exec(*args, timeout=timeout)
    rc = proc.wait()
    stdout = (proc.stdout.read() or "").strip() if getattr(proc, "stdout", None) else ""
    stderr = (proc.stderr.read() or "").strip() if getattr(proc, "stderr", None) else ""
    if rc != 0:
        raise RuntimeError(stderr or stdout or f"Command exited with status {rc}")
    return json.loads(stdout) if stdout else None


def probe_sandbox_t3_state(sb: Any) -> dict[str, Any]:
    """Probes T3 runtime state, SQLite pairing rows, and file-stored pairing records."""
    if not hasattr(sb, "exec"):
        return {}
    try:
        result = exec_json(sb, "python3", "-c", _PROBE_T3_PAIRING_SCRIPT, timeout=15)
        return result if isinstance(result, dict) else {}
    except Exception as exc:
        logger.debug("T3 pairing probe failed for %s: %s", getattr(sb, "object_id", "?"), exc)
        return {}


def probe_active_pairing_ids_cli(sb: Any) -> set[str] | None:
    """Fallback active-token check via `t3 auth pairing list` when SQLite is unavailable."""
    if not hasattr(sb, "exec"):
        return None
    try:
        data = exec_json(
            sb,
            "t3", "auth", "pairing", "list", "--base-dir", T3_BASE_DIR, "--json",
            timeout=15,
        )
    except Exception:
        return None
    if not isinstance(data, list):
        return None
    return {
        str(item["id"])
        for item in data
        if isinstance(item, dict) and item.get("id")
    }


def resolve_t3_origin(sb: Any, probe: dict[str, Any]) -> tuple[str | None, str | None]:
    """Resolves active T3 Code Server public HTTPS tunnel URL, supporting custom --t3-port."""
    if probe.get("runtime_present") and probe.get("server_running") is False:
        return None, "T3 Code Server process is not running inside this sandbox."

    tunnels = {}
    if hasattr(sb, "tunnels"):
        try:
            tunnels = sb.tunnels(timeout=2) or {}
        except Exception as exc:
            logger.debug("Failed resolving tunnels for %s: %s", getattr(sb, "object_id", "?"), exc)

    candidate_ports: list[int] = []
    for raw_port in (probe.get("runtime_port"), probe.get("env_t3_port"), DEFAULT_T3_PORT):
        if isinstance(raw_port, int) and raw_port > 0 and raw_port not in candidate_ports:
            candidate_ports.append(raw_port)

    for port in candidate_ports:
        tunnel = tunnels.get(port)
        raw_url = getattr(tunnel, "url", None) if tunnel is not None else None
        if isinstance(raw_url, str) and raw_url.strip():
            return raw_url.rstrip("/"), None

    if probe.get("server_running") is True or probe.get("runtime_present"):
        for fallback in (probe.get("dev_url"), probe.get("public_url")):
            if isinstance(fallback, str) and fallback.strip():
                return fallback.rstrip("/"), None

    return None, "T3 Code Server is not running or tunnel unavailable on this sandbox."


def persist_pairing_link(sb: Any, sandbox_id: str, record: dict[str, Any]) -> None:
    """Appends a newly generated pairing record to `/tmp/t3-pairing-links.json` inside sb."""
    try:
        proc = sb.exec(
            "python3", "-c", _APPEND_PAIRING_LINK_SCRIPT, json.dumps(record),
            timeout=15,
        )
        rc = proc.wait()
        if rc != 0:
            err_text = (proc.stderr.read() or "").strip() if getattr(proc, "stderr", None) else ""
            logger.warning("Failed persisting pairing link for %s: %s", sandbox_id, err_text)
    except Exception as exc:
        logger.warning("Failed persisting pairing link for %s: %s", sandbox_id, exc)
