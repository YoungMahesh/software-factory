"""In-sandbox execution, Git workspace initialization, T3 readiness, and DB wiring helpers."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Callable

from sandbox.app_scaffolder._cloud import sanitize_db_name

from ._idle_thread import create_idle_thread_via_ws
from ._models import FactoryAppRecord, build_initial_thread_prompt
from ._prompts import GENERIC_REPO_OPEN_PROMPT
from ._workspace import (
    configure_nextjs_dev_port,
    ensure_blank_git_workspace,
    ensure_shared_repo_checkout,
    exec_in_sandbox,
    inject_vault_bundle_in_sandbox,
    shared_repo_base_dir,
)
from ._worktree_t3 import start_worktree_thread_for_repo

logger = logging.getLogger(__name__)

DEFAULT_T3_READY_TIMEOUT_SECS = 150

_T3_PROBE_SCRIPT = (
    "import glob, json, os, sys\n"
    "checks = [\n"
    "    ('server-runtime.json', '/root/.t3/userdata/server-runtime.json'),\n"
    "    ('environment-id', '/root/.t3/userdata/environment-id'),\n"
    "    ('settings.json', '/root/.t3/userdata/settings.json'),\n"
    "]\n"
    "missing = [name for name, path in checks if not os.path.isfile(path)]\n"
    "if missing:\n"
    "    sys.stderr.write('missing: ' + ', '.join(missing) + '\\n')\n"
    "    raise SystemExit(1)\n"
    "env_id = open('/root/.t3/userdata/environment-id').read().strip()\n"
    "if not env_id:\n"
    "    sys.stderr.write('empty environment-id\\n')\n"
    "    raise SystemExit(1)\n"
    "settings = json.load(open('/root/.t3/userdata/settings.json'))\n"
    "caches = {}\n"
    "for p in glob.glob('/root/.t3/caches/*.json'):\n"
    "    try:\n"
    "        caches[os.path.splitext(os.path.basename(p))[0]] = json.load(open(p))\n"
    "    except Exception:\n"
    "        pass\n"
    "print(json.dumps({'environment_id': env_id, 'settings': settings, 'caches': caches}))\n"
)

_ENV_WRITER_SCRIPT = (
    "import json, os, re, sys\n"
    "data = json.load(sys.stdin)\n"
    "app_dir, conn = data['app_dir'], data['connection_string']\n"
    "env_path = os.path.join(app_dir, '.env')\n"
    "vault_dir = os.path.join(app_dir, '.git', 'env-vault')\n"
    "os.makedirs(vault_dir, mode=0o700, exist_ok=True)\n"
    "os.chmod(vault_dir, 0o700)\n"
    "pattern = re.compile(r'^\\s*(export\\s+)?DATABASE_URL\\s*=.*$')\n"
    "new_line = f'DATABASE_URL=\"{conn}\"\\n'\n"
    "lines = open(env_path, encoding='utf-8').read().splitlines(keepends=True) if os.path.isfile(env_path) else []\n"
    "out = []\n"
    "replaced = False\n"
    "for line in lines:\n"
    "    if pattern.match(line):\n"
    "        out.append(new_line)\n"
    "        replaced = True\n"
    "    else:\n"
    "        out.append(line)\n"
    "if not replaced:\n"
    "    if out and not out[-1].endswith('\\n'):\n"
    "        out[-1] += '\\n'\n"
    "    out.append(new_line)\n"
    "content = ''.join(out)\n"
    "for target in (env_path, os.path.join(vault_dir, 'default.env')):\n"
    "    os.makedirs(os.path.dirname(target), exist_ok=True)\n"
    "    with open(target, 'w', encoding='utf-8') as f:\n"
    "        f.write(content)\n"
    "    os.chmod(target, 0o600)\n"
    "map_path = os.path.join(vault_dir, 'env.map')\n"
    "with open(map_path, 'w', encoding='utf-8') as f:\n"
    "    f.write('default.env=.env\\n')\n"
    "os.chmod(map_path, 0o600)\n"
)


def prepare_app_workspace(
    sb: Any,
    app: FactoryAppRecord,
    app_dir: str,
    *,
    force: bool = False,
    dev_port: int | None = None,
    env: dict[str, str] | None = None,
    resolve_bundle_fn: Callable[..., Any] | None = None,
    log_cb: Callable[[str], None] | None = None,
) -> None:
    """Clones/updates shared GitHub base checkout + secrets, or scaffolds Next.js / blank Git."""
    if app.repo:
        effective_env = env or {}
        gh_token = effective_env.get("GH_TOKEN") or effective_env.get("GITHUB_TOKEN")
        base_dir = app_dir or shared_repo_base_dir(app.repo)
        ensure_shared_repo_checkout(
            sb,
            repo=app.repo,
            branch=app.branch,
            base_dir=base_dir,
            gh_token=gh_token,
            force=force,
            full_clone=app.full_clone,
        )
        try:
            injected = inject_vault_bundle_in_sandbox(
                sb,
                repo=app.repo,
                app_dir=base_dir,
                env=effective_env,
                resolve_bundle_fn=resolve_bundle_fn,
            )
            if injected and log_cb:
                log_cb(f"🔐 Injected Central Config Store secrets for {app.repo}")
        except Exception as exc:
            logger.warning("Central Config Store secret injection skipped for %s: %s", app.repo, exc)
            if log_cb:
                log_cb(f"⚠️ Secret injection from config repo skipped: {exc}")
        return

    if app.template == "nextjs":
        cmd = ["create-app", app_dir, "-y"]
        if app.mobile_app:
            cmd.append("--mobile-app")
        if force:
            cmd.append("--force")
        rc, out, err = exec_in_sandbox(sb, *cmd, timeout=300)
        if rc != 0:
            raise RuntimeError(f"create-app failed in {app_dir}: {err or out}")
        if dev_port is not None:
            configure_nextjs_dev_port(sb, app_dir, dev_port)
    else:
        ensure_blank_git_workspace(sb, app_dir)


def cleanup_app_workspace(
    sb: Any,
    app_dir: str,
    *,
    dev_port: int | None = None,
    repo_base_dir: str | None = None,
    keep_base_repo: bool = False,
) -> None:
    """Stops app-scoped processes, removes worktree or T3 project, and deletes the workspace."""
    if not app_dir.startswith("/root/") or app_dir.rstrip("/") == "/root":
        raise ValueError(f"Refusing to delete unsafe workspace path: {app_dir!r}")

    kill_script = (
        "import os, signal, sys, time\n"
        "app_dir = os.path.realpath(sys.argv[1])\n"
        "port = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else ''\n"
        "self_pid = os.getpid()\n"
        "parent_pid = os.getppid()\n"
        "targets = []\n"
        "for name in os.listdir('/proc'):\n"
        "    if not name.isdigit():\n"
        "        continue\n"
        "    pid = int(name)\n"
        "    if pid in (1, self_pid, parent_pid):\n"
        "        continue\n"
        "    try:\n"
        "        cwd = os.path.realpath(f'/proc/{pid}/cwd')\n"
        "        raw_cmd = open(f'/proc/{pid}/cmdline', 'rb').read().decode('utf-8', 'ignore')\n"
        "        args = [a for a in raw_cmd.split('\\x00') if a]\n"
        "    except Exception:\n"
        "        continue\n"
        "    if any('t3' == os.path.basename(a) for a in args[:2]):\n"
        "        continue\n"
        "    matches_dir = cwd == app_dir or cwd.startswith(app_dir + '/') or any(\n"
        "        a == app_dir or a.startswith(app_dir + '/') for a in args\n"
        "    )\n"
        "    matches_port = bool(port) and (\n"
        "        f'PORT={port}' in args or any(args[i:i+2] == ['-p', port] for i in range(len(args) - 1))\n"
        "    )\n"
        "    if matches_dir or matches_port:\n"
        "        targets.append(pid)\n"
        "for sig in (signal.SIGTERM, signal.SIGKILL):\n"
        "    alive = []\n"
        "    for pid in targets:\n"
        "        try:\n"
        "            os.kill(pid, sig)\n"
        "            alive.append(pid)\n"
        "        except ProcessLookupError:\n"
        "            pass\n"
        "        except Exception:\n"
        "            pass\n"
        "    if not alive or sig == signal.SIGKILL:\n"
        "        break\n"
        "    time.sleep(0.4)\n"
        "    targets = alive\n"
    )
    exec_in_sandbox(sb, "python3", "-c", kill_script, app_dir, str(dev_port or ""), timeout=20)
    if repo_base_dir and app_dir != repo_base_dir:
        exec_in_sandbox(sb, "git", "-C", repo_base_dir, "worktree", "remove", "--force", app_dir, timeout=30)
        exec_in_sandbox(sb, "rm", "-rf", app_dir, timeout=30)
        if not keep_base_repo:
            exec_in_sandbox(sb, "t3", "project", "remove", "--force", repo_base_dir, "--base-dir", "/root/.t3", timeout=30)
            exec_in_sandbox(sb, "rm", "-rf", repo_base_dir, timeout=30)
        return
    if not keep_base_repo:
        exec_in_sandbox(sb, "t3", "project", "remove", "--force", app_dir, "--base-dir", "/root/.t3", timeout=30)
        exec_in_sandbox(sb, "rm", "-rf", app_dir, timeout=30)


def probe_t3_ready(sb: Any, timeout: int = 15) -> dict[str, Any] | None:
    """Performs a single non-blocking probe of T3 Code Server readiness inside the sandbox."""
    try:
        rc, out, _ = exec_in_sandbox(sb, "python3", "-c", _T3_PROBE_SCRIPT, timeout=timeout)
        if rc == 0 and out.strip():
            return json.loads(out)
    except Exception:
        pass
    return None


def wait_for_t3_ready(sb: Any, timeout_secs: int = DEFAULT_T3_READY_TIMEOUT_SECS) -> dict[str, Any]:
    """Polls until T3 Code Server emits server-runtime, environment-id, and settings."""
    deadline = time.monotonic() + timeout_secs
    last_probe_err = ""
    while True:
        rc, out, err = exec_in_sandbox(sb, "python3", "-c", _T3_PROBE_SCRIPT, timeout=15)
        if rc == 0 and out.strip():
            return json.loads(out)
        if err.strip():
            last_probe_err = err.strip()
        if time.monotonic() >= deadline:
            break
        time.sleep(1.0)

    log_tail = ""
    try:
        log_rc, log_out, _ = exec_in_sandbox(sb, "tail", "-n", "15", "/tmp/t3.log", timeout=10)
        if log_rc == 0 and log_out.strip():
            log_tail = log_out.strip()
    except Exception:
        pass

    parts = [f"Timed out after {timeout_secs}s waiting for T3 Code Server readiness inside sandbox."]
    if last_probe_err:
        parts.append(f"Probe state: {last_probe_err}.")
    if log_tail:
        parts.append(f"Recent /tmp/t3.log:\n{log_tail}")
    raise TimeoutError(" ".join(parts))


def resolve_provider_model(
    t3_meta: dict[str, Any],
    requested_provider: str,
    requested_model: str,
    requested_thought_level: str | None,
) -> tuple[str, str, str | None]:
    """Selects an enabled, authenticated T3 provider instance and advertised model slug."""
    settings = t3_meta.get("settings") or {}
    caches = t3_meta.get("caches") or {}
    instances = settings.get("providerInstances") or {}

    if requested_provider == "antigravity":
        preferred = ["antigravity", "antigravity-anv", "antigravity-mgh"]
        candidates = [
            iid for iid in preferred if isinstance(instances.get(iid), dict) and instances[iid].get("enabled", True)
        ]
        for iid, cfg in instances.items():
            if (
                iid not in candidates
                and isinstance(cfg, dict)
                and cfg.get("driver") == "antigravity"
                and cfg.get("enabled", True)
            ):
                candidates.append(iid)

        chosen = next(
            (iid for iid in candidates if (caches.get(iid) or {}).get("auth", {}).get("status") == "authenticated"),
            candidates[0] if candidates else "antigravity",
        )
        cache_models = (caches.get(chosen) or {}).get("models") or []
        slugs = [m.get("slug") for m in cache_models if isinstance(m, dict) and m.get("slug")]
        chosen_model = requested_model
        if slugs and chosen_model not in slugs:
            if "gemini-4-hydrogen" in slugs:
                chosen_model = "gemini-4-hydrogen"
            elif "gemini-3.8-flash" in slugs:
                chosen_model = "gemini-3.8-flash"
            else:
                default_item = next((m for m in cache_models if isinstance(m, dict) and m.get("isDefault")), None)
                chosen_model = (default_item or {}).get("slug") or slugs[0]
        return chosen, chosen_model, requested_thought_level

    if requested_provider in instances and instances[requested_provider].get("enabled", True):
        return requested_provider, requested_model, requested_thought_level
    for iid, cfg in instances.items():
        if isinstance(cfg, dict) and cfg.get("driver") == requested_provider and cfg.get("enabled", True):
            return iid, requested_model, requested_thought_level
    raise RuntimeError(f"Requested provider '{requested_provider}' is not enabled inside this sandbox.")


def provision_optional_database(
    sb: Any,
    app: FactoryAppRecord,
    app_dir: str,
    *,
    env: dict[str, str],
    create_db_fn: Callable[..., Any],
) -> str | None:
    """Provisions a Resource Plane database for scratch Next.js apps when configured."""
    if app.repo or app.template != "nextjs":
        return None
    rp_domain = env.get("RESOURCE_PLANE_DOMAIN") or env.get("DB_HOST_DOMAIN")
    rp_token = env.get("RESOURCE_PLANE_ADMIN_TOKEN") or env.get("DB_HOST_ADMIN_TOKEN")
    if not (rp_domain and rp_token):
        return None

    db_info = create_db_fn(
        database_name=sanitize_db_name(app.slug),
        project_name=app.slug,
        domain=rp_domain,
        token=rp_token,
    )
    rc, _, err = exec_in_sandbox(
        sb,
        "python3",
        "-c",
        _ENV_WRITER_SCRIPT,
        stdin_text=json.dumps({"app_dir": app_dir, "connection_string": db_info.connection_string}),
        timeout=30,
    )
    if rc != 0:
        raise RuntimeError(f"Failed writing DATABASE_URL into sandbox workspace: {err}")
    return str(db_info.name)


def _probe_project_threads(sb: Any, app_dir: str) -> tuple[bool, list[dict[str, Any]]]:
    rc, out, _ = exec_in_sandbox(
        sb, "t3", "thread", "list", "--project", app_dir, "--base-dir", "/root/.t3", "--json", timeout=30
    )
    if rc != 0 or not out.strip():
        return False, []
    parsed = json.loads(out)
    if isinstance(parsed, dict) and isinstance(parsed.get("threads"), list):
        return True, parsed["threads"]
    if isinstance(parsed, list):
        return True, parsed
    return True, []


def list_project_threads(sb: Any, app_dir: str) -> list[dict[str, Any]]:
    """Lists T3 threads registered for app_dir inside the sandbox."""
    _, threads = _probe_project_threads(sb, app_dir)
    return threads


def _parse_added_project_id(output: str) -> str | None:
    match = re.search(r"^(?:Added|Unarchived)\s+project\s+(\S+)", output.strip(), re.MULTILINE)
    return match.group(1) if match else None


def ensure_worktree_or_app_thread(
    sb: Any,
    app: FactoryAppRecord,
    app_dir: str,
    *,
    instance_id: str,
    model: str,
    thought_level: str | None,
    log_cb: Callable[[str], None] | None = None,
) -> tuple[str, str | None, str, str | None]:
    """Registers project, creates a per-conversation T3 worktree for repos, or opens scratch thread."""
    project_title = app.repo.split("/", 1)[-1] if app.repo else app.title
    add_rc, add_out, add_err = exec_in_sandbox(
        sb, "t3", "project", "add", "--base-dir", "/root/.t3", "--title", project_title, app_dir, timeout=30
    )
    added_project_id = _parse_added_project_id(add_out) if add_rc == 0 else None
    list_ok, existing = _probe_project_threads(sb, app_dir)
    if add_rc != 0 and not list_ok:
        raise RuntimeError(f"t3 project add failed: {add_err}")

    if app.repo:
        thread_id, project_id, wt_path, wt_branch = start_worktree_thread_for_repo(
            sb,
            app,
            app_dir,
            added_project_id=added_project_id,
            existing_threads=existing,
            instance_id=instance_id,
            model=model,
            thought_level=thought_level,
            log_cb=log_cb,
        )
        return thread_id, project_id, wt_path, wt_branch

    if existing and existing[0].get("threadId"):
        return str(existing[0]["threadId"]), existing[0].get("projectId") or added_project_id, app_dir, None

    if not app.prompt.strip() and not app.web_app:
        try:
            thread_id, project_id = create_idle_thread_via_ws(
                sb,
                app_dir=app_dir,
                project_id=added_project_id,
                title=app.title,
                instance_id=instance_id,
                model=model,
                thought_level=thought_level,
            )
            return thread_id, project_id, app_dir, None
        except Exception as exc:
            logger.warning("Idle thread RPC failed for %s; falling back to generic prompt: %s", app_dir, exc)

    cmd = [
        "t3", "thread", "start", app_dir, "-",
        "--base-dir", "/root/.t3",
        "--provider", instance_id,
        "--model", model,
    ]
    if thought_level:
        cmd.extend(["--option", f"thought_level={thought_level}"])
    cmd.extend(["--title", app.title, "--json"])
    full_prompt = build_initial_thread_prompt(
        app.prompt,
        template=app.template,
        app_dir=app_dir,
        dev_port=app.dev_port,
        web_app=app.web_app,
        repo=app.repo,
    )
    if not full_prompt:
        full_prompt = GENERIC_REPO_OPEN_PROMPT
    rc, out, err = exec_in_sandbox(sb, *cmd, stdin_text=full_prompt, timeout=60)
    if rc != 0:
        recovered = list_project_threads(sb, app_dir)
        if recovered and recovered[0].get("threadId"):
            return str(recovered[0]["threadId"]), recovered[0].get("projectId") or added_project_id, app_dir, None
        raise RuntimeError(f"t3 thread start failed: {err or out}")

    started = json.loads(out)
    thread_id = started.get("threadId")
    project_id = started.get("projectId") or (started.get("projection") or {}).get("projectId") or added_project_id
    if not thread_id:
        raise RuntimeError("t3 thread start did not return a threadId.")
    return str(thread_id), project_id, app_dir, None


def ensure_project_and_start_thread(
    sb: Any,
    app: FactoryAppRecord,
    app_dir: str,
    *,
    instance_id: str,
    model: str,
    thought_level: str | None,
) -> tuple[str, str | None]:
    """Registers app_dir with T3 and opens an idle thread (empty repo prompt) or starts a turn."""
    thread_id, project_id, _, _ = ensure_worktree_or_app_thread(
        sb,
        app,
        app_dir,
        instance_id=instance_id,
        model=model,
        thought_level=thought_level,
    )
    return thread_id, project_id


def mint_pairing_token(sb: Any) -> str:
    """Creates a 5-minute one-time pairing credential inside the sandbox."""
    rc, out, err = exec_in_sandbox(
        sb,
        "t3", "auth", "pairing", "create",
        "--base-dir", "/root/.t3",
        "--ttl", "5m",
        "--label", "Factory App Handoff",
        "--json",
        timeout=30,
    )
    if rc != 0:
        raise RuntimeError(f"Failed creating T3 pairing token: {err or out}")
    token = (json.loads(out) or {}).get("credential")
    if not token:
        raise RuntimeError("T3 pairing create returned no credential.")
    return str(token)
