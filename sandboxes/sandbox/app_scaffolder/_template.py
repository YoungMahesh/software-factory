"""Template materialization, skill filtering, and workspace setup for App Scaffolder."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
from typing import Any

from sandbox.config import resolve_factory_root

DEFAULT_SANDBOX_TEMPLATE_DIR = Path("/opt/app-template")
_STANDALONE_ALLOWED_ENTRIES = {".git", ".gitignore"}


@dataclass
class CloudWiringOptions:
    """Opt-in cloud automation options executed after local template scaffolding."""

    github: bool = False
    public_repo: bool = False
    repo_name: str | None = None
    org_name: str | None = None
    provision_db: bool = False
    db_name: str | None = None
    provision_s3: bool = False
    bucket_name: str | None = None
    push_vault: bool = False
    launch: bool = False
    vm: bool = False
    t3: bool = True
    profile: str | None = None
    mobile_app: bool = False
    deploy: bool = False
    subdomain: str | None = None
    base_domain: str | None = None
    skip_migrate: bool = False


@dataclass
class AppScaffoldRequest:
    """Configuration options controlling App Template materialization."""

    project_name: str
    project_dir: Path
    mobile_app: bool = False
    db: bool = True
    auth: bool = True
    skills: bool = True
    install: bool = True
    git: bool = True
    force: bool = False
    template_dir: Path | None = None
    skills_source_dir: Path | None = None


@dataclass
class AppScaffoldResult:
    """Result summary emitted after materializing an application workspace."""

    project_name: str
    project_dir: Path
    mobile_app: bool
    db: bool
    auth: bool
    skills: bool
    installed_deps: bool
    git_initialized: bool
    git_committed: bool
    reused_existing_git: bool


def sanitize_identifiers(project_name: str) -> tuple[str, str, str]:
    """Derives Expo slug, URL scheme, and reverse-DNS mobile package ID from project_name."""
    raw = project_name.strip().lower()
    slug = re.sub(r"[^a-z0-9-]+", "-", raw).strip("-") or "base-app"
    alnum = re.sub(r"[^a-z0-9]+", "", slug)
    if not alnum or alnum[0].isdigit():
        alnum = f"app{alnum}"
    return slug, alnum, f"com.app.{alnum}"


def resolve_app_template_dir(explicit_dir: Path | None = None) -> Path:
    """Locates the App Template directory from explicit arg, env, repo root, or sandbox image."""
    candidates: list[Path] = []
    if explicit_dir is not None:
        candidates.append(explicit_dir)
    env_dir = os.environ.get("APP_TEMPLATE_DIR")
    if env_dir:
        candidates.append(Path(env_dir).expanduser())
    factory_root = resolve_factory_root()
    candidates.append(factory_root / "app-template")
    candidates.append(DEFAULT_SANDBOX_TEMPLATE_DIR)

    for candidate in candidates:
        if (candidate / "base").is_dir():
            return candidate
    raise FileNotFoundError(
        "App Template directory not found. Expected 'app-template/base' under factory root, "
        "APP_TEMPLATE_DIR, or /opt/app-template."
    )


def resolve_skills_source_dir(
    template_dir: Path,
    explicit_dir: Path | None = None,
) -> Path:
    """Locates the canonical skills and agent-docs source tree for --skills scaffolding."""
    candidates: list[Path] = []
    if explicit_dir is not None:
        candidates.append(explicit_dir)
    candidates.append(template_dir / "_skills_source")
    candidates.append(resolve_factory_root())
    candidates.append(template_dir.parent)

    for candidate in candidates:
        if (candidate / ".agents" / "skills").is_dir() and (candidate / "skills-lock.json").is_file():
            return candidate
    raise FileNotFoundError(
        "Canonical skills source not found. Expected '.agents/skills' and 'skills-lock.json' "
        "in factory root or staged '_skills_source'."
    )


def load_skills_manifest(template_dir: Path) -> dict[str, Any]:
    """Loads and validates the App Template skills allowlist manifest (skills.json)."""
    manifest_path = template_dir / "skills.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Skills manifest not found: {manifest_path}")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data.get("skills"), list) or not data["skills"]:
        raise ValueError(f"Invalid skills manifest '{manifest_path}': 'skills' must be a non-empty list.")
    return data


def _validate_target_dir(project_dir: Path, force: bool) -> bool:
    """Checks directory safety and returns True if an existing .git directory should be reused."""
    if not project_dir.exists():
        return False
    if not project_dir.is_dir():
        raise ValueError(f"Target path exists and is not a directory: {project_dir}")

    entries = {p.name for p in project_dir.iterdir()}
    has_git = ".git" in entries
    if not entries or entries <= _STANDALONE_ALLOWED_ENTRIES:
        return has_git
    if not force:
        raise ValueError(
            f"Target directory '{project_dir}' already contains files. Pass --force to overwrite."
        )
    return has_git


def _copy_tree(src: Path, dest: Path, *, merge_gitignore: bool = False) -> None:
    """Recursively copies template files while optionally merging existing .gitignore entries."""
    if not src.exists():
        return
    if src.is_dir():
        dest.mkdir(parents=True, exist_ok=True)
        for entry in sorted(src.iterdir(), key=lambda p: p.name):
            _copy_tree(entry, dest / entry.name, merge_gitignore=merge_gitignore)
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    if merge_gitignore and src.name == ".gitignore" and dest.is_file():
        existing_lines = dest.read_text(encoding="utf-8").splitlines()
        template_lines = src.read_text(encoding="utf-8").splitlines()
        merged = list(template_lines)
        template_entries = {line.strip() for line in template_lines if line.strip() and not line.strip().startswith("#")}
        sandbox_only = [
            line
            for line in existing_lines
            if line.strip() and not line.strip().startswith("#") and line.strip() not in template_entries
        ]
        if sandbox_only:
            merged.extend(["", "# Preserved workspace ignores", *sandbox_only])
        dest.write_text("\n".join(merged) + "\n", encoding="utf-8")
        return
    shutil.copy2(src, dest)


def _apply_root_package_tokens(project_dir: Path, project_name: str, mobile_app: bool, skills: bool) -> None:
    """Replaces root package.json template placeholders for scripts and package name."""
    root_pkg_path = project_dir / "package.json"
    raw = root_pkg_path.read_text(encoding="utf-8").replace("{{PROJECT_NAME}}", project_name)

    extra_scripts = ""
    if mobile_app:
        extra_scripts += (
            ',\n    "mobile": "pnpm --filter @repo/mobile start"'
            ',\n    "mobile:tunnel": "pnpm --filter @repo/mobile tunnel"'
            ',\n    "mobile:android": "pnpm --filter @repo/mobile android"'
            ',\n    "mobile:build-apk": "pnpm --filter @repo/mobile build:apk"'
            ',\n    "mobile:serve": "pnpm --filter @repo/mobile serve:apk"'
        )
    if skills:
        extra_scripts += ',\n    "skills:update": "npx skills update -y"'

    root_pkg_path.write_text(raw.replace("{{EXTRA_ROOT_SCRIPTS}}", extra_scripts), encoding="utf-8")


def _apply_web_overlays(template_dir: Path, project_dir: Path, db: bool, auth: bool) -> None:
    """Applies modular database and authentication overlays onto apps/web."""
    web_dir = project_dir / "apps" / "web"
    web_pkg_path = web_dir / "package.json"
    web_pkg = json.loads(web_pkg_path.read_text(encoding="utf-8"))

    env_example_path = project_dir / ".env.example"
    env_example = env_example_path.read_text(encoding="utf-8")
    env_runtime = env_example

    if db:
        _copy_tree(template_dir / "apps" / "web" / "overlay-db", web_dir)
        web_pkg["dependencies"]["drizzle-orm"] = "1.0.0-rc.4"
        web_pkg["dependencies"]["pg"] = "^8.23.0"
        web_pkg["devDependencies"]["drizzle-kit"] = "1.0.0-rc.4"
        web_pkg["devDependencies"]["@types/pg"] = "^8.23.1"
        web_pkg["scripts"]["db:generate"] = "drizzle-kit generate"
        web_pkg["scripts"]["db:migrate"] = "drizzle-kit migrate"

        local_db_line = "\n# Database Connection\nDATABASE_URL=postgres://postgres:postgres@localhost:5432/template_db\n"
        env_example += local_db_line
        env_runtime += local_db_line

    if auth:
        _copy_tree(template_dir / "apps" / "web" / "overlay-auth", web_dir)
        web_pkg["dependencies"]["better-auth"] = "^1.7.3"
        auth_secret = secrets.token_urlsafe(32)
        env_example += "\n# Better Auth Secret\nBETTER_AUTH_SECRET=replace-with-32-char-random-secret\n"
        env_runtime += f"\n# Better Auth Secret\nBETTER_AUTH_SECRET={auth_secret}\n"

    web_pkg_path.write_text(json.dumps(web_pkg, indent=2) + "\n", encoding="utf-8")
    env_example_path.write_text(env_example, encoding="utf-8")
    env_path = project_dir / ".env"
    env_path.write_text(env_runtime, encoding="utf-8")
    try:
        env_path.chmod(0o600)
    except OSError:
        pass


def _apply_mobile_app(template_dir: Path, project_dir: Path, project_name: str, auth: bool) -> None:
    """Copies apps/mobile, parameterizes app.json identifiers, and applies optional auth overlay."""
    mobile_dir = project_dir / "apps" / "mobile"
    _copy_tree(template_dir / "apps" / "mobile" / "base", mobile_dir)

    app_json_path = mobile_dir / "app.json"
    if app_json_path.is_file():
        slug, scheme, package_id = sanitize_identifiers(project_name)
        app_json = json.loads(app_json_path.read_text(encoding="utf-8"))
        expo = app_json.setdefault("expo", {})
        expo["name"] = project_name
        expo["slug"] = slug
        expo["scheme"] = scheme
        expo.setdefault("ios", {})["bundleIdentifier"] = package_id
        expo.setdefault("android", {})["package"] = package_id
        app_json_path.write_text(json.dumps(app_json, indent=2) + "\n", encoding="utf-8")

    if auth:
        _copy_tree(template_dir / "apps" / "mobile" / "overlay-auth", mobile_dir)
        mobile_pkg_path = mobile_dir / "package.json"
        mobile_pkg = json.loads(mobile_pkg_path.read_text(encoding="utf-8"))
        mobile_pkg["dependencies"]["expo-secure-store"] = "~58.0.2"
        mobile_pkg_path.write_text(json.dumps(mobile_pkg, indent=2) + "\n", encoding="utf-8")


def _apply_skills_bundle(template_dir: Path, project_dir: Path, skills_source_dir: Path) -> None:
    """Copies allowlisted Matt Pocock skills, filtered skills-lock.json, and agent docs."""
    manifest = load_skills_manifest(template_dir)
    expected_source = manifest.get("source")
    allowlisted: list[str] = manifest["skills"]

    lock_data = json.loads((skills_source_dir / "skills-lock.json").read_text(encoding="utf-8"))
    all_locks = lock_data.get("skills", {})
    filtered_locks: dict[str, Any] = {}

    src_skills_root = skills_source_dir / ".agents" / "skills"
    dest_skills_root = project_dir / ".agents" / "skills"
    for skill_name in allowlisted:
        src_skill = src_skills_root / skill_name
        if not src_skill.is_dir():
            raise FileNotFoundError(f"Allowlisted skill '{skill_name}' missing from {src_skills_root}")
        lock_entry = all_locks.get(skill_name)
        if lock_entry is not None:
            if expected_source and lock_entry.get("source") != expected_source:
                raise ValueError(
                    f"Skill '{skill_name}' has source '{lock_entry.get('source')}', expected '{expected_source}'."
                )
            filtered_locks[skill_name] = lock_entry
        _copy_tree(src_skill, dest_skills_root / skill_name)

    filtered_lock_payload = {"version": lock_data.get("version", 2), "skills": filtered_locks}
    (project_dir / "skills-lock.json").write_text(
        json.dumps(filtered_lock_payload, indent=2) + "\n",
        encoding="utf-8",
    )

    src_docs_dir = skills_source_dir / "docs" / "agents"
    dest_docs_dir = project_dir / "docs" / "agents"
    for doc_name in manifest.get("agentDocs", []):
        doc_path = src_docs_dir / doc_name
        if doc_path.is_file():
            _copy_tree(doc_path, dest_docs_dir / doc_name)

    _copy_tree(template_dir / "skills-starter", project_dir)


def _has_git_identity(project_dir: Path) -> bool:
    """Returns True if git user.name and user.email are available for creating commits."""
    if os.environ.get("GIT_AUTHOR_NAME") and os.environ.get("GIT_AUTHOR_EMAIL"):
        return True
    name_res = subprocess.run(["git", "-C", str(project_dir), "config", "user.name"], capture_output=True, text=True, check=False)
    email_res = subprocess.run(["git", "-C", str(project_dir), "config", "user.email"], capture_output=True, text=True, check=False)
    return bool(name_res.stdout.strip() and email_res.stdout.strip())


def _initialize_git_repo(project_dir: Path, reused_existing_git: bool) -> tuple[bool, bool]:
    """Initializes git (unless already initialized) and commits scaffolded files when identity is configured."""
    if not shutil.which("git"):
        return False, False
    if not reused_existing_git:
        init_res = subprocess.run(["git", "init", "-b", "main", str(project_dir)], capture_output=True, text=True, check=False)
        if init_res.returncode != 0:
            subprocess.run(["git", "init", str(project_dir)], capture_output=True, text=True, check=True)
    subprocess.run(["git", "-C", str(project_dir), "add", "-A"], capture_output=True, text=True, check=True)
    if not _has_git_identity(project_dir):
        return True, False
    status_res = subprocess.run(["git", "-C", str(project_dir), "status", "--porcelain"], capture_output=True, text=True, check=True)
    if not status_res.stdout.strip():
        return True, False
    commit_res = subprocess.run(
        ["git", "-C", str(project_dir), "commit", "-m", "feat: initial commit from create-app"],
        capture_output=True,
        text=True,
        check=False,
    )
    return True, commit_res.returncode == 0


def scaffold_app(req: AppScaffoldRequest) -> AppScaffoldResult:
    """Materializes the App Template into req.project_dir according to selected options."""
    template_dir = resolve_app_template_dir(req.template_dir)
    skills_source_dir = resolve_skills_source_dir(template_dir, req.skills_source_dir) if req.skills else None

    project_dir = req.project_dir.resolve()
    reused_existing_git = _validate_target_dir(project_dir, force=req.force)
    project_dir.mkdir(parents=True, exist_ok=True)

    _copy_tree(template_dir / "base", project_dir, merge_gitignore=reused_existing_git)
    _apply_root_package_tokens(project_dir, req.project_name, req.mobile_app, req.skills)

    _copy_tree(template_dir / "packages" / "theme", project_dir / "packages" / "theme")
    _copy_tree(template_dir / "packages" / "types", project_dir / "packages" / "types")
    _copy_tree(template_dir / "apps" / "web" / "base", project_dir / "apps" / "web")
    _apply_web_overlays(template_dir, project_dir, db=req.db, auth=req.auth)

    if req.mobile_app:
        _apply_mobile_app(template_dir, project_dir, req.project_name, auth=req.auth)

    if req.skills and skills_source_dir is not None:
        _apply_skills_bundle(template_dir, project_dir, skills_source_dir)

    installed_deps = False
    if req.install and shutil.which("pnpm"):
        install_res = subprocess.run(["pnpm", "install"], cwd=str(project_dir), check=False)
        installed_deps = install_res.returncode == 0

    git_initialized = False
    git_committed = False
    if req.git:
        git_initialized, git_committed = _initialize_git_repo(project_dir, reused_existing_git)

    return AppScaffoldResult(
        project_name=req.project_name,
        project_dir=project_dir,
        mobile_app=req.mobile_app,
        db=req.db,
        auth=req.auth,
        skills=req.skills,
        installed_deps=installed_deps,
        git_initialized=git_initialized,
        git_committed=git_committed,
        reused_existing_git=reused_existing_git,
    )
