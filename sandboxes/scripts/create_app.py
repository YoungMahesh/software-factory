#!/usr/bin/env python3
"""CLI entrypoint for scaffolding applications from the Software Factory App Template."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Ensure sandboxes package root is on sys.path when invoked directly as script
_SANDBOXES_ROOT = Path(__file__).resolve().parent.parent
if _SANDBOXES_ROOT.is_dir():
    _root_str = str(_SANDBOXES_ROOT)
    if sys.path[:1] != [_root_str]:
        sys.path.insert(0, _root_str)
elif Path("/opt/sandboxes").is_dir() and "/opt/sandboxes" not in sys.path:
    sys.path.append("/opt/sandboxes")

from sandbox.app_scaffolder import (
    AppScaffoldRequest,
    CloudWiringOptions,
    scaffold_app,
)


def create_parser() -> argparse.ArgumentParser:
    """Builds the argument parser for create-app."""
    parser = argparse.ArgumentParser(
        prog="create-app",
        description="Scaffold a new Next.js + optional Expo app from the Software Factory App Template.",
    )
    parser.add_argument("dir", nargs="?", default=None, help="Target directory or project name (default: my-base-app).")
    parser.add_argument("--mobile-app", dest="mobile_app", action=argparse.BooleanOptionalAction, default=None, help="Include React Native / Expo mobile client.")
    parser.add_argument("--db", dest="db", action=argparse.BooleanOptionalAction, default=None, help="Include Drizzle ORM (PostgreSQL) scaffolding (default: enabled).")
    parser.add_argument("--auth", dest="auth", action=argparse.BooleanOptionalAction, default=None, help="Include Better Auth scaffolding (default: enabled).")
    parser.add_argument("--skills", dest="skills", action=argparse.BooleanOptionalAction, default=None, help="Include allowlisted agent skills and docs (default: enabled).")
    parser.add_argument("--install", dest="install", action=argparse.BooleanOptionalAction, default=None, help="Run pnpm install after scaffolding (default: enabled).")
    parser.add_argument("--git", dest="git", action=argparse.BooleanOptionalAction, default=None, help="Initialize Git repository with initial commit (default: enabled).")
    parser.add_argument("--force", action="store_true", help="Allow scaffolding into a non-empty directory.")
    parser.add_argument("-y", "--default", action="store_true", help="Use default template options without prompting.")

    # Factory cloud automation flags
    parser.add_argument("--cloud", action="store_true", help="Enable --github, --provision-db (when --db), --push-vault, and --launch.")
    parser.add_argument("--github", action="store_true", help="Create GitHub repository in GH_ORG_NAME and push initial commit.")
    parser.add_argument("--public", action="store_true", help="Create public GitHub repository (used with --github; default: private).")
    parser.add_argument("--repo-name", default=None, help="Override GitHub/config env repository name (<repo> or <owner>/<repo>).")
    parser.add_argument("--provision-db", action="store_true", help="Provision Resource Plane PostgreSQL database and inject DATABASE_URL.")
    parser.add_argument("--db-name", default=None, help="Explicit Resource Plane PostgreSQL database name.")
    parser.add_argument("--provision-s3", action="store_true", help="Provision Resource Plane S3 bucket and inject AWS SDK variables.")
    parser.add_argument("--bucket-name", default=None, help="Explicit Resource Plane S3 bucket name.")
    parser.add_argument("--push-vault", action="store_true", help="Encrypt and push .env to Central Config Store (config/env/<repo>/).")
    parser.add_argument("--launch", action="store_true", help="Launch a Modal Sandbox with T3 Code after scaffolding.")
    parser.add_argument("--vm", action="store_true", help="Launch sandbox as a full Linux VM (used with --launch).")
    parser.add_argument("--no-t3", action="store_true", help="Disable T3 Code when launching sandbox with --launch.")
    parser.add_argument("--profile", default=None, help="Modal workspace profile to use with --launch.")
    parser.add_argument("--deploy", action="store_true", help="Deploy the scaffolded app live to the Resource Plane VPS (/root/<repo-name>) with wildcard HTTPS.")
    parser.add_argument("--subdomain", default=None, help="Override subdomain label when used with --deploy.")
    parser.add_argument("--base-domain", default=None, help="Override APPS_BASE_DOMAIN when used with --deploy.")
    parser.add_argument("--skip-migrate", action="store_true", help="Skip automatic database migration when used with --deploy.")
    return parser


def _prompt_text(prompt: str, default: str) -> str:
    answer = input(f"? {prompt} ({default}): ").strip()
    return answer or default


def _prompt_bool(prompt: str, default: bool) -> bool:
    hint = "Y/n" if default else "y/N"
    answer = input(f"? {prompt} ({hint}): ").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def _resolve_options(args: argparse.Namespace, argv: list[str]) -> tuple[AppScaffoldRequest, CloudWiringOptions]:
    has_explicit_flags = any(arg.startswith("-") for arg in argv)
    is_interactive = bool(sys.stdin.isatty() and not args.default and not has_explicit_flags)

    target_dir_raw = args.dir
    mobile_app = args.mobile_app
    db = args.db
    auth = args.auth
    skills = args.skills
    install = args.install
    git = args.git

    if is_interactive:
        if not target_dir_raw:
            target_dir_raw = _prompt_text("What will your project be called?", "my-base-app")
        if mobile_app is None:
            mobile_app = _prompt_bool("Include React Native / Expo mobile app?", False)
        if db is None:
            db = _prompt_bool("Include Drizzle ORM (PostgreSQL)?", True)
        if auth is None:
            auth = _prompt_bool("Include Better Auth?", True)
        if skills is None:
            skills = _prompt_bool("Include allowlisted Agent Skills Suite?", True)
        if install is None:
            install = _prompt_bool("Run pnpm install?", True)
        if git is None:
            git = _prompt_bool("Initialize a new Git repository?", True)
    else:
        target_dir_raw = target_dir_raw or "my-base-app"
        mobile_app = bool(mobile_app) if mobile_app is not None else False
        db = True if db is None else bool(db)
        auth = True if auth is None else bool(auth)
        skills = True if skills is None else bool(skills)
        install = True if install is None else bool(install)
        git = True if git is None else bool(git)

    raw_path = Path(target_dir_raw)
    project_dir = raw_path if raw_path.is_absolute() else (Path.cwd() / raw_path)
    project_dir = project_dir.resolve()
    project_name = project_dir.name

    scaffold_req = AppScaffoldRequest(
        project_name=project_name,
        project_dir=project_dir,
        mobile_app=mobile_app,
        db=db,
        auth=auth,
        skills=skills,
        install=install,
        git=git,
        force=args.force,
    )

    github = bool(args.github or args.cloud)
    provision_db = bool(args.provision_db or (args.cloud and db))
    provision_s3 = bool(args.provision_s3)
    push_vault = bool(args.push_vault or args.cloud)
    launch = bool(args.launch or args.cloud)

    cloud_opts = CloudWiringOptions(
        github=github,
        public_repo=args.public,
        repo_name=args.repo_name,
        provision_db=provision_db,
        db_name=args.db_name,
        provision_s3=provision_s3,
        bucket_name=args.bucket_name,
        push_vault=push_vault,
        launch=launch,
        vm=args.vm,
        t3=not args.no_t3,
        profile=args.profile,
        mobile_app=mobile_app,
        deploy=bool(args.deploy),
        subdomain=args.subdomain,
        base_domain=args.base_domain,
        skip_migrate=bool(args.skip_migrate),
    )
    return scaffold_req, cloud_opts


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for create-app."""
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = create_parser()
    args = parser.parse_args(raw_argv)

    try:
        scaffold_req, cloud_opts = _resolve_options(args, raw_argv)
        if cloud_opts.launch and not cloud_opts.github and not cloud_opts.repo_name:
            parser.error("--launch requires --github (or --repo-name referencing an existing GitHub repo).")

        print(f"Creating app '{scaffold_req.project_name}' at {scaffold_req.project_dir}...")
        res = scaffold_app(scaffold_req)
        print(f"✓ Scaffolded App Template ({'web + mobile' if res.mobile_app else 'web'})")

        has_cloud = any([
            cloud_opts.github,
            cloud_opts.provision_db,
            cloud_opts.provision_s3,
            cloud_opts.push_vault,
            cloud_opts.launch,
            cloud_opts.deploy,
        ])
        if has_cloud:
            from sandbox.app_scaffolder import wire_cloud_resources

            cloud_res = wire_cloud_resources(res.project_name, res.project_dir, cloud_opts)
            if cloud_res.github_repo:
                print(f"✓ Pushed GitHub repository: https://github.com/{cloud_res.github_repo}")
            if cloud_res.database_info:
                print(f"✓ Provisioned PostgreSQL DB: {cloud_res.database_info.name}")
            if cloud_res.s3_info:
                print(f"✓ Provisioned S3 bucket: {cloud_res.s3_info.bucket_name}")
            if cloud_res.vault_pushed:
                print("✓ Pushed .env secrets to Central Config Store (config)")
            if cloud_res.launch_response is not None:
                from sandbox.formatting import display_launch_summary

                display_launch_summary(cloud_res.launch_response)
            if cloud_res.deploy_result is not None:
                print(f"✓ Deployed Hosted App: {cloud_res.deploy_result.url} ({cloud_res.deploy_result.remote_dir})")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("\nNext steps:")
    print(f"  cd {res.project_dir}")
    if not res.installed_deps:
        print("  pnpm install")
    print("  pnpm dev")
    if res.mobile_app:
        print("  pnpm mobile")
    return 0


if __name__ == "__main__":
    sys.exit(main())
