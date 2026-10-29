"""CLI entrypoint for launching and managing Modal sandboxes (local or remote)."""

import argparse
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
    REMOTE_STARTUP_SCRIPT,
    SHARED_SECRET_NAME,
    browser_enabled,
    build_sandbox_image,
    get_gradle_volumes,
    load_ssh_pub_key,
)
from sandbox.config import (
    DEFAULT_METRO_PORT,
    DEFAULT_OPENCODE_PORT,
    DEFAULT_ORG,
    DEFAULT_T3_PORT,
    DEFAULT_WEB_PORT,
    IDLE_TIMEOUT_SECS,
    TIMEOUT_SECS,
)
from sandbox.cli import (
    SnapshotTTLAction,
    capture_snapshot,
    create_parser,
    generate_ascii_qr,
    print_access_info,
    print_snapshot_info,
    validate_args,
)
from sandbox.core import (
    LaunchRequest,
    launch_sandbox,
)


def run_remote_request(endpoint_url: str, path: str, payload: dict) -> dict:
    """Sends a synchronous JSON POST request to the remote Modal control plane."""
    target_url = endpoint_url.rstrip("/") + path
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    auth_token = os.environ.get("MODAL_SANDBOX_AUTH_TOKEN")
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

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

    print(f"📡 Delegating sandbox launch to remote control plane ({endpoint_url})...")
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
        "opencode": args.opencode,
        "opencode_port": args.opencode_port,
        "t3": args.t3,
        "t3_port": args.t3_port,
        "t3_ssh_host": args.t3_ssh_host,
        "react_native": args.react_native,
        "metro_port": args.metro_port,
        "modal": args.modal,
        "sops": args.sops,
        "browser": args.browser,
        "agy": args.agy,
        "herdr": args.herdr,
        "pi": args.pi,
    }
    data = run_remote_request(endpoint_url, "/launch", payload)
    print_fn = getattr(sys.modules.get("sandbox.main"), "print_access_info", print_access_info)
    print_fn(
        app_name=data.get("app_name", ""),
        sandbox_name=data.get("sandbox_name"),
        sandbox_id=data.get("sandbox_id"),
        ssh_info=tuple(data["ssh_info"]) if data.get("ssh_info") else None,
        opencode_url=data.get("opencode_url"),
        opencode_port=data.get("opencode_port"),
        opencode_password=data.get("opencode_password"),
        metro_url=data.get("metro_url"),
        metro_port=data.get("metro_port"),
        t3_url=data.get("t3_url"),
        t3_port=data.get("t3_port"),
        t3_pair_url=data.get("t3_pair_url"),
        t3_qr_code=data.get("t3_qr_code"),
        t3_ssh_host=data.get("t3_ssh_host"),
        memory_gb=data.get("memory_gb"),
        agy_enabled=data.get("agy_enabled", False),
        cloudflare_enabled=data.get("cloudflare_enabled", True),
        sops_enabled=data.get("sops_enabled", False),
        is_vm=data.get("is_vm", False),
    )


def run_sandbox_launch(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser | None = None,
    repo_root: Path | None = None,
) -> None:
    """Validates configuration and launches a sandbox locally or remotely."""
    if getattr(args, "remote", False):
        run_remote_launch(args, parser=parser)
        return

    if parser is None:
        parser = create_parser()

    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent

    clean_repo = args.repo.strip().rstrip("/") if args.repo else None
    orgs_env_file = repo_root / "secrets" / "github-orgs.env"

    if clean_repo and not orgs_env_file.is_file():
        parser.error(
            f"Organization credentials file not found: {orgs_env_file} (expected secrets/github-orgs.env)."
        )

    if args.memory is not None:
        if not args.vm:
            parser.error("--memory can only be used with --vm.")
        if args.memory < 1:
            parser.error("--memory must be a positive integer number of GB.")
        print(
            "⚠️  Warning: --memory is deprecated. VM Sandboxes now use standard burstable RAM (128, 16384) MiB. "
            f"Using value to configure swapfile ({args.memory * 2} GB).",
            file=sys.stderr,
        )

    if args.opencode and args.opencode_port == DEFAULT_WEB_PORT:
        parser.error(
            f"--opencode-port cannot be {DEFAULT_WEB_PORT}: port {DEFAULT_WEB_PORT} is reserved for web servers and Cloudflare Tunnel."
        )

    if args.react_native:
        if args.metro_port == DEFAULT_WEB_PORT:
            parser.error(
                f"--metro-port cannot be {DEFAULT_WEB_PORT}: port {DEFAULT_WEB_PORT} is reserved for web servers and Cloudflare Tunnel."
            )
        if args.opencode and args.metro_port == args.opencode_port:
            parser.error(
                "--metro-port and --opencode-port must differ: a port can only be exposed once."
            )

    if args.t3 and args.t3_port == DEFAULT_WEB_PORT:
        parser.error(
            f"--t3-port cannot be {DEFAULT_WEB_PORT}: port {DEFAULT_WEB_PORT} is reserved for web servers and Cloudflare Tunnel."
        )

    if args.t3 and args.opencode and args.t3_port == args.opencode_port:
        parser.error(
            "--t3-port and --opencode-port must differ: a port can only be exposed once."
        )

    if args.t3 and args.react_native and args.t3_port == args.metro_port:
        parser.error(
            "--t3-port and --metro-port must differ: a port can only be exposed once."
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
        opencode=args.opencode,
        opencode_port=args.opencode_port,
        t3=args.t3,
        t3_port=args.t3_port,
        t3_ssh_host=getattr(args, "t3_ssh_host", None),
        react_native=args.react_native,
        metro_port=args.metro_port,
        modal=args.modal,
        sops=args.sops,
        browser=args.browser,
        agy=args.agy,
        herdr=args.herdr,
        pi=args.pi,
    )

    try:
        sandbox, result = launch_sandbox(req, repo_root=repo_root)
    except modal.exception.AlreadyExistsError as exc:
        print(
            f"❌ Sandbox already exists and is running: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    print_fn = getattr(sys.modules.get("sandbox.main"), "print_access_info", print_access_info)
    print_fn(
        sandbox=sandbox,
        app_name=result.app_name,
        sandbox_name=result.sandbox_name,
        ssh_info=result.ssh_info,
        opencode_url=result.opencode_url,
        opencode_port=result.opencode_port,
        opencode_password=result.opencode_password,
        metro_url=result.metro_url,
        metro_port=result.metro_port,
        t3_url=result.t3_url,
        t3_port=result.t3_port,
        t3_pair_url=result.t3_pair_url,
        t3_qr_code=result.t3_qr_code,
        t3_ssh_host=result.t3_ssh_host,
        memory_gb=result.memory_gb,
        agy_enabled=result.agy_enabled,
        cloudflare_enabled=result.cloudflare_enabled,
        sops_enabled=result.sops_enabled,
        is_vm=result.is_vm,
    )


def main():
    parser = create_parser()
    args = parser.parse_args()
    validate_args(parser, args)

    if args.snapshot and not args.remote:
        capture_snapshot(
            sandbox_id=args.snapshot,
            ttl_days=args.snapshot_ttl,
            terminate=args.terminate,
        )
        return

    run_sandbox_launch(args, parser=parser)


if __name__ == "__main__":
    main()
