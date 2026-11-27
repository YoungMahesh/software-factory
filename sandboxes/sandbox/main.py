"""CLI entrypoint for launching and managing Modal sandboxes (local or remote)."""

import argparse
import base64
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

import modal

# Ensure repository root is on sys.path for shared imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.image import (
    DEFAULT_T3_USAGE_VOLUME,
    REMOTE_STARTUP_SCRIPT,
    browser_enabled,
    build_sandbox_image,
    get_gradle_volumes,
    load_ssh_pub_key,
)
from sandbox.config import (
    DEFAULT_METRO_PORT,
    DEFAULT_ORG,
    DEFAULT_SNAPSHOT_TIMEOUT,
    DEFAULT_T3_PORT,
    DEFAULT_WEB_PORT,
    DEFAULT_XFCE_PORT,
    IDLE_TIMEOUT_SECS,
    TIMEOUT_SECS,
    parse_env_file,
    resolve_factory_root,
    resolve_web_ui_credentials,
)
from sandbox.cli import (
    SnapshotTTLAction,
    append_ssh_config,
    capture_snapshot,
    create_parser,
    display_launch_summary,
    generate_ascii_qr,
    generate_ssh_config_snippet,
    print_access_info,
    print_snapshot_info,
    validate_args,
)
from sandbox.core import (
    LaunchRequest,
)
from sandbox.launcher import launch_sandbox


def run_remote_request(endpoint_url: str, path: str, payload: dict) -> dict:
    """Sends a synchronous JSON POST request to the remote Modal control plane."""
    target_url = endpoint_url.rstrip("/") + path
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    creds_dict = resolve_web_ui_credentials(repo_root=resolve_factory_root(), enforce=False)
    user = creds_dict.get("WEB_UI_USERNAME")
    passwd = creds_dict.get("WEB_UI_PASSWORD")
    if not user or not passwd:
        raise ValueError(
            "Remote control plane invocation requires WEB_UI_USERNAME and WEB_UI_PASSWORD to be set in environment or .env."
        )

    creds = base64.b64encode(f"{user}:{passwd}".encode("utf-8")).decode("utf-8")
    headers["Authorization"] = f"Basic {creds}"

    req = urllib.request.Request(target_url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            resp_body = resp.read().decode("utf-8")
            return json.loads(resp_body)
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8")
        try:
            detail = json.loads(err_body).get("detail", err_body)
        except Exception:
            detail = err_body
        raise RuntimeError(f"Remote control plane error ({exc.code}): {detail}") from exc
    except Exception as exc:
        raise RuntimeError(f"Failed to communicate with remote control plane: {exc}") from exc


def run_remote_launch(args: argparse.Namespace, parser: argparse.ArgumentParser | None = None) -> None:
    """Delegates sandbox launch or snapshot capture to the hosted Modal control plane."""
    endpoint_url = args.endpoint_url or os.environ.get("MODAL_SANDBOX_ENDPOINT_URL")
    if not endpoint_url:
        endpoint_url = parse_env_file(resolve_factory_root() / ".env").get("MODAL_SANDBOX_ENDPOINT_URL")
    if not endpoint_url:
        msg = "--remote requires --endpoint-url or the MODAL_SANDBOX_ENDPOINT_URL environment variable."
        if parser:
            parser.error(msg)
        raise ValueError(msg)

    if args.snapshot:
        print(f"📡 Delegating snapshot capture for {args.snapshot} to {endpoint_url}...")
        payload = {
            "sandbox_id": args.snapshot,
            "ttl_days": args.snapshot_ttl,
            "terminate": args.terminate,
            "timeout": getattr(args, "snapshot_timeout", DEFAULT_SNAPSHOT_TIMEOUT),
        }
        res = run_remote_request(endpoint_url, "/snapshot", payload)
        print_snapshot_info(
            sandbox_id=res["sandbox_id"],
            image_id=res["image_id"],
            ttl_days=res["ttl_days"],
            ttl_seconds=res.get("ttl_seconds"),
            terminate=res.get("terminated", False),
        )
        return

    print(f"📡 Delegating sandbox launch to {endpoint_url}...")
    payload = {
        "repo": args.repo,
        "testing": args.testing,
        "github_branch": args.github_branch,
        "full_clone": args.full_clone,
        "name": args.name,
        "from_snapshot": args.from_snapshot,
        "vm": args.vm,
        "memory": args.memory,
        "no_cloudflare": args.no_cloudflare,
        "t3": args.t3,
        "t3_port": args.t3_port,
        "t3_ssh_host": args.t3_ssh_host,
        "t3_usage_volume": getattr(args, "t3_usage_volume", DEFAULT_T3_USAGE_VOLUME),
        "no_t3_persist": getattr(args, "no_t3_persist", False),
        "react_native": args.react_native,
        "metro_port": args.metro_port,
        "modal": args.modal,
        "profile": getattr(args, "profile", None),
        "sops": args.sops,
        "browser": args.browser,
        "xfce": getattr(args, "xfce", False),
        "xfce_port": getattr(args, "xfce_port", DEFAULT_XFCE_PORT),
        "xfce_password": getattr(args, "xfce_password", None),
    }
    data = run_remote_request(endpoint_url, "/launch", payload)
    display_launch_summary(data, register_ssh=not getattr(args, "no_ssh_config", False))


def run_sandbox_launch(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser | None = None,
    repo_root: Path | None = None,
) -> None:
    """Launches a sandbox locally using the Modal client SDK."""
    if args.remote:
        run_remote_launch(args, parser=parser)
        return

    if parser is None:
        parser = create_parser()

    if args.memory is not None:
        print(
            "⚠️  Warning: --memory is deprecated. VM Sandboxes now use standard burstable RAM (128, 16384) MiB. "
            f"Using value to configure swapfile ({args.memory * 2} GB).",
            file=sys.stderr,
        )

    req = LaunchRequest(
        repo=args.repo,
        testing=args.testing,
        github_branch=args.github_branch,
        full_clone=args.full_clone,
        name=args.name,
        from_snapshot=args.from_snapshot,
        vm=args.vm,
        memory=args.memory,
        no_cloudflare=args.no_cloudflare,
        t3=args.t3,
        t3_port=args.t3_port,
        t3_ssh_host=getattr(args, "t3_ssh_host", None),
        t3_usage_volume=getattr(args, "t3_usage_volume", DEFAULT_T3_USAGE_VOLUME),
        no_t3_persist=getattr(args, "no_t3_persist", False),
        react_native=args.react_native,
        metro_port=args.metro_port,
        modal=args.modal,
        profile=getattr(args, "profile", None),
        sops=args.sops,
        browser=args.browser,
        xfce=getattr(args, "xfce", False),
        xfce_port=getattr(args, "xfce_port", DEFAULT_XFCE_PORT),
        xfce_password=getattr(args, "xfce_password", None),
    )

    try:
        sandbox, result = launch_sandbox(
            req,
            repo_root=repo_root,
            build_image_fn=build_sandbox_image,
            load_pubkey_fn=load_ssh_pub_key,
        )
    except (ValueError, FileNotFoundError) as exc:
        parser.error(str(exc))
    except modal.exception.AlreadyExistsError as exc:
        print(
            f"❌ Sandbox already exists and is running: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    display_launch_summary(
        result,
        sandbox=sandbox,
        register_ssh=not getattr(args, "no_ssh_config", False),
    )


def _build_infra_help_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="modal-sandbox infra",
        description="Manage Resource Plane, Sandbox Web Dashboard, and Host Ingress Proxy on the VPS.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", metavar="<subcommand>")
    subparsers.add_parser("deploy", help="Deploy Resource Plane (PostgreSQL & S3) to the VPS via SSH.")
    subparsers.add_parser("dashboard", help="Deploy the Next.js Sandbox Web Dashboard and configure Caddy routing.")
    subparsers.add_parser("caddy", help="Configure Host Ingress Proxy (/opt/caddy) and backup/restore config.")
    return parser


def run_infra_cli(argv: list[str]) -> int:
    """Dispatches `modal-sandbox infra <deploy|dashboard|caddy>` without implicit deploy."""
    if argv and argv[0] == "deploy":
        from sandbox.infra_deploy import main as infra_main
        return infra_main(argv[1:])
    if argv and argv[0] == "dashboard":
        from sandbox.dashboard_deploy import main as dashboard_main
        return dashboard_main(argv[1:])
    if argv and argv[0] == "caddy":
        from sandbox.caddy_deploy import main as caddy_main
        return caddy_main(argv[1:])

    parser = _build_infra_help_parser()
    if not argv:
        parser.print_help(sys.stderr)
        return 2
    if argv[0] in ("-h", "--help"):
        parser.print_help()
        return 0
    parser.error(f"Unknown infra subcommand '{argv[0]}'. Choose from: deploy, dashboard, caddy.")
    return 2


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "create-app":
        from scripts.create_app import main as create_app_main
        sys.exit(create_app_main(sys.argv[2:]))

    if len(sys.argv) > 1 and sys.argv[1] == "deploy-app":
        from scripts.deploy_app import main as deploy_app_main
        sys.exit(deploy_app_main(sys.argv[2:]))

    if len(sys.argv) > 1 and sys.argv[1] == "infra":
        sys.exit(run_infra_cli(sys.argv[2:]))

    parser = create_parser()
    args = parser.parse_args()
    validate_args(parser, args)

    if args.snapshot and not args.remote:
        capture_snapshot(
            sandbox_id=args.snapshot,
            ttl_days=args.snapshot_ttl,
            terminate=args.terminate,
            timeout=getattr(args, "snapshot_timeout", DEFAULT_SNAPSHOT_TIMEOUT),
        )
        return

    run_sandbox_launch(args, parser=parser)


if __name__ == "__main__":
    main()
