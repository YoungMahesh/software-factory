"""In-sandbox execution, GitHub cloning, host-side secret injection, and workspace setup helpers."""

from __future__ import annotations

import inspect
import json
import shlex
from typing import Any, Callable

from sandbox.env_store import resolve_sandbox_bundle

_CLONE_REPO_SCRIPT = """
import json, os, shutil, stat, subprocess, sys, tempfile

cfg = json.load(sys.stdin)
repo = cfg["repo"]
branch = (cfg.get("branch") or "").strip()
app_dir = cfg["app_dir"]
token = (cfg.get("gh_token") or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
force = bool(cfg.get("force"))
full_clone = bool(cfg.get("full_clone"))

if os.path.exists(app_dir):
    if force:
        shutil.rmtree(app_dir)
    else:
        sys.stderr.write(f"Target directory already exists: {app_dir}\\n")
        raise SystemExit(1)

os.makedirs(os.path.dirname(app_dir), exist_ok=True)
env = os.environ.copy()
env["GIT_TERMINAL_PROMPT"] = "0"
askpass_path = None
try:
    if token:
        askpass_dir = "/dev/shm" if os.path.isdir("/dev/shm") else tempfile.gettempdir()
        fd, askpass_path = tempfile.mkstemp(prefix="git-askpass-", dir=askpass_dir)
        os.close(fd)
        with open(askpass_path, "w", encoding="utf-8") as f:
            f.write("#!/usr/bin/env python3\\nimport os, sys\\n")
            f.write("prompt = (sys.argv[1] if len(sys.argv) > 1 else '').lower()\\n")
            f.write("print('x-access-token' if 'username' in prompt else os.environ.get('SF_GIT_TOKEN', ''))\\n")
        os.chmod(askpass_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        env["GIT_ASKPASS"] = askpass_path
        env["SF_GIT_TOKEN"] = token

    cmd = ["git", "clone", "--quiet"]
    if not full_clone:
        cmd.extend(["--depth", "50"])
    if branch:
        cmd.extend(["--branch", branch, "--single-branch"])
    cmd.extend([f"https://github.com/{repo}.git", app_dir])

    res = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        sys.stderr.write(res.stderr or res.stdout or "git clone failed\\n")
        raise SystemExit(res.returncode or 1)

    subprocess.run(
        ["git", "-C", app_dir, "config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*"],
        check=False,
    )
    head_res = subprocess.run(["git", "-C", app_dir, "symbolic-ref", "-q", "HEAD"], capture_output=True, text=True)
    if head_res.returncode != 0:
        sys.stderr.write(f"Branch '{branch or 'HEAD'}' resolved to a detached ref; only Git branches are supported.\\n")
        raise SystemExit(1)

    if shutil.which("gh") and token:
        gh_env = os.environ.copy()
        gh_env["GH_TOKEN"] = token
        subprocess.run(["gh", "auth", "setup-git"], env=gh_env, capture_output=True, check=False)
finally:
    if askpass_path and os.path.exists(askpass_path):
        try:
            os.unlink(askpass_path)
        except OSError:
            pass
"""

_VAULT_UNPACK_SCRIPT = """
import base64, json, os, subprocess, sys

payload = json.load(sys.stdin)
app_dir = payload["app_dir"]
encoded_bundle = payload.get("encoded_bundle")
dotenv_b64 = payload.get("dotenv_b64")
git_name = payload.get("git_author_name")
git_email = payload.get("git_author_email")

git_dir = os.path.join(app_dir, ".git")
vault_dir = os.path.join(git_dir, "env-vault") if os.path.isdir(git_dir) else None

if encoded_bundle:
    data = json.loads(base64.b64decode(encoded_bundle).decode("utf-8"))
    files = data.get("files", {})
    env_map_content = data.get("env_map_content", "")
    mappings = data.get("mappings", [])
    if vault_dir:
        os.makedirs(vault_dir, mode=0o700, exist_ok=True)
        os.chmod(vault_dir, 0o700)
        if env_map_content:
            mp = os.path.join(vault_dir, "env.map")
            with open(mp, "w", encoding="utf-8") as f:
                f.write(env_map_content)
            os.chmod(mp, 0o600)
        for src_name, content in files.items():
            vf = os.path.join(vault_dir, src_name)
            os.makedirs(os.path.dirname(vf), exist_ok=True)
            with open(vf, "w", encoding="utf-8") as f:
                f.write(content)
            os.chmod(vf, 0o600)
    for src, dest in mappings:
        if src in files:
            dest_path = os.path.join(app_dir, dest)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            with open(dest_path, "w", encoding="utf-8") as f:
                f.write(files[src])
            os.chmod(dest_path, 0o600)
elif dotenv_b64:
    raw = base64.b64decode(dotenv_b64).decode("utf-8")
    env_path = os.path.join(app_dir, ".env")
    if not os.path.isfile(env_path):
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(raw)
        os.chmod(env_path, 0o600)
    if vault_dir:
        os.makedirs(vault_dir, mode=0o700, exist_ok=True)
        os.chmod(vault_dir, 0o700)
        df = os.path.join(vault_dir, "default.env")
        with open(df, "w", encoding="utf-8") as f:
            f.write(raw)
        os.chmod(df, 0o600)
        mp = os.path.join(vault_dir, "env.map")
        with open(mp, "w", encoding="utf-8") as f:
            f.write("default.env=.env\\n")
        os.chmod(mp, 0o600)

if git_name and os.path.isdir(git_dir):
    subprocess.run(["git", "-C", app_dir, "config", "--local", "user.name", git_name], check=False)
if git_email and os.path.isdir(git_dir):
    subprocess.run(["git", "-C", app_dir, "config", "--local", "user.email", git_email], check=False)
"""


def _exec_accepts_timeout(exec_fn: Any) -> bool:
    try:
        sig = inspect.signature(exec_fn)
    except (TypeError, ValueError):
        return True
    params = sig.parameters
    return "timeout" in params or any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
    )


def exec_in_sandbox(
    sb: Any,
    *cmd: str,
    stdin_text: str | None = None,
    timeout: int = 300,
) -> tuple[int, str, str]:
    """Executes a command inside a Modal sandbox, streaming stdin cleanly when provided."""
    if _exec_accepts_timeout(sb.exec):
        proc = sb.exec(*cmd, timeout=timeout)
    else:
        proc = sb.exec(*cmd)
    if stdin_text is not None:
        proc.stdin.write(stdin_text)
        proc.stdin.write_eof()
        proc.stdin.drain()
    rc = proc.wait()
    stdout = proc.stdout.read() or ""
    stderr = proc.stderr.read() or ""
    return rc, stdout, stderr


def ensure_blank_git_workspace(sb: Any, app_dir: str) -> None:
    """Initializes a Git-backed empty workspace directory inside the sandbox for blank apps."""
    q_dir = shlex.quote(app_dir)
    script = (
        f"mkdir -p {q_dir} && cd {q_dir} && "
        "if [ ! -d .git ]; then "
        "git init -b main . && "
        "cat << 'EOF' > .gitignore\n"
        ".env\n.env.*\nnode_modules/\ndist/\n.venv/\n__pycache__/\n*.pyc\n"
        "EOF\n"
        "git add .gitignore && "
        "GIT_AUTHOR_NAME=\"${DEFAULT_GIT_NAME:-Factory Operator}\" "
        "GIT_AUTHOR_EMAIL=\"${DEFAULT_GIT_EMAIL:-operator@software-factory.local}\" "
        "GIT_COMMITTER_NAME=\"${DEFAULT_GIT_NAME:-Factory Operator}\" "
        "GIT_COMMITTER_EMAIL=\"${DEFAULT_GIT_EMAIL:-operator@software-factory.local}\" "
        "git commit -m 'initial commit' >/dev/null 2>&1 || true; "
        "fi"
    )
    rc, out, err = exec_in_sandbox(sb, "bash", "-lc", script, timeout=60)
    if rc != 0:
        raise RuntimeError(f"Failed initializing blank Git workspace in {app_dir}: {err or out}")


def configure_nextjs_dev_port(sb: Any, app_dir: str, dev_port: int) -> None:
    """Pins the assigned dev_port in Next.js apps/web/package.json and workspace .env."""
    script = (
        "import json, os, re, subprocess, sys\n"
        "app_dir, dev_port = sys.argv[1], int(sys.argv[2])\n"
        "pkg_path = os.path.join(app_dir, 'apps', 'web', 'package.json')\n"
        "changed_files = []\n"
        "if os.path.isfile(pkg_path):\n"
        "    with open(pkg_path, encoding='utf-8') as f:\n"
        "        pkg = json.load(f)\n"
        "    scripts = pkg.setdefault('scripts', {})\n"
        "    desired = f'next dev -p {dev_port}'\n"
        "    if scripts.get('dev') != desired:\n"
        "        scripts['dev'] = desired\n"
        "        with open(pkg_path, 'w', encoding='utf-8') as f:\n"
        "            json.dump(pkg, f, indent=2)\n"
        "            f.write('\\n')\n"
        "        changed_files.append('apps/web/package.json')\n"
        "env_path = os.path.join(app_dir, '.env')\n"
        "lines = open(env_path, encoding='utf-8').read().splitlines(keepends=True) if os.path.isfile(env_path) else []\n"
        "pattern = re.compile(r'^\\s*(export\\s+)?PORT\\s*=.*$')\n"
        "out, replaced = [], False\n"
        "for line in lines:\n"
        "    if pattern.match(line):\n"
        "        out.append(f'PORT={dev_port}\\n')\n"
        "        replaced = True\n"
        "    else:\n"
        "        out.append(line)\n"
        "if not replaced:\n"
        "    if out and not out[-1].endswith('\\n'):\n"
        "        out[-1] += '\\n'\n"
        "    out.append(f'PORT={dev_port}\\n')\n"
        "os.makedirs(app_dir, exist_ok=True)\n"
        "with open(env_path, 'w', encoding='utf-8') as f:\n"
        "    f.write(''.join(out))\n"
        "try:\n"
        "    os.chmod(env_path, 0o600)\n"
        "except OSError:\n"
        "    pass\n"
        "if changed_files and os.path.isdir(os.path.join(app_dir, '.git')):\n"
        "    has_head = subprocess.run(['git', '-C', app_dir, 'rev-parse', '--verify', 'HEAD'], capture_output=True).returncode == 0\n"
        "    if has_head:\n"
        "        subprocess.run(['git', '-C', app_dir, 'add', *changed_files], check=False)\n"
        "        subprocess.run([\n"
        "            'git', '-C', app_dir,\n"
        "            '-c', 'user.name=Factory Operator', '-c', 'user.email=operator@software-factory.local',\n"
        "            'commit', '--no-verify', '-m', f'chore: bind web dev port {dev_port}',\n"
        "        ], capture_output=True, check=False)\n"
    )
    rc, out, err = exec_in_sandbox(sb, "python3", "-c", script, app_dir, str(dev_port), timeout=30)
    if rc != 0:
        raise RuntimeError(f"Failed configuring dev port {dev_port} in {app_dir}: {err or out}")


def clone_github_repo_in_sandbox(
    sb: Any,
    *,
    repo: str,
    branch: str | None,
    app_dir: str,
    gh_token: str | None = None,
    force: bool = False,
    full_clone: bool = False,
) -> None:
    """Clones a GitHub repository into app_dir inside the sandbox without leaking tokens in argv."""
    payload = json.dumps(
        {
            "repo": repo,
            "branch": branch or "",
            "app_dir": app_dir,
            "gh_token": gh_token or "",
            "force": force,
            "full_clone": full_clone,
        }
    )
    rc, out, err = exec_in_sandbox(
        sb, "python3", "-c", _CLONE_REPO_SCRIPT, stdin_text=payload, timeout=180
    )
    if rc != 0:
        raise RuntimeError(f"Failed cloning {repo} into {app_dir}: {err or out}")


def inject_vault_bundle_in_sandbox(
    sb: Any,
    *,
    repo: str,
    app_dir: str,
    env: dict[str, str],
    resolve_bundle_fn: Callable[..., Any] | None = None,
) -> bool:
    """Resolves Central Config Store (env/) secrets host-side and writes .env/.git/env-vault into app_dir."""
    owner, bare_repo = repo.split("/", 1) if "/" in repo else (env.get("GH_ORG_NAME") or "", repo)
    if not owner or not bare_repo:
        return False
    gh_token = env.get("GH_TOKEN") or env.get("GITHUB_TOKEN")
    age_key = env.get("AGE_PRIVATE_KEY") or env.get("SOPS_AGE_KEY")
    resolver = resolve_bundle_fn or resolve_sandbox_bundle
    try:
        bundle = resolver(bare_repo, org_name=owner, gh_token=gh_token, age_key=age_key)
    except TypeError:
        bundle = resolver(bare_repo, org_name=owner)
    if bundle is None:
        return False
    if not (bundle.encoded_bundle or bundle.dotenv_b64 or bundle.git_author_name or bundle.git_author_email):
        return False

    payload = json.dumps(
        {
            "app_dir": app_dir,
            "encoded_bundle": bundle.encoded_bundle,
            "dotenv_b64": bundle.dotenv_b64,
            "git_author_name": bundle.git_author_name,
            "git_author_email": bundle.git_author_email,
        }
    )
    rc, out, err = exec_in_sandbox(
        sb, "python3", "-c", _VAULT_UNPACK_SCRIPT, stdin_text=payload, timeout=60
    )
    if rc != 0:
        raise RuntimeError(f"Failed materializing Central Config Store secrets in {app_dir}: {err or out}")
    return True


def install_repo_dependencies_in_sandbox(sb: Any, app_dir: str) -> None:
    """Installs Node dependencies inside app_dir when pnpm-lock.yaml or package.json exists."""
    q_dir = shlex.quote(app_dir)
    script = (
        f"cd {q_dir} && "
        "if [ -f pnpm-lock.yaml ]; then pnpm install; "
        "elif [ -f package.json ]; then npm install; fi"
    )
    rc, out, err = exec_in_sandbox(sb, "bash", "-lc", script, timeout=300)
    if rc != 0:
        raise RuntimeError(f"Dependency install failed in {app_dir}: {err or out}")
