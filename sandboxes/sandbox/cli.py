"""CLI argument parsing, validation, and terminal formatting for Modal sandboxes."""

import argparse
from pathlib import Path

import modal

from shared.image import DEFAULT_T3_USAGE_VOLUME
from .config import (
    DEFAULT_METRO_PORT,
    DEFAULT_SNAPSHOT_TIMEOUT,
    DEFAULT_T3_PORT,
    DEFAULT_XFCE_PORT,
)
from .formatting import (
    append_ssh_config,
    display_launch_summary,
    generate_ascii_qr,
    generate_ssh_config_snippet,
    print_access_info,
    print_snapshot_info,
)


class SnapshotTTLAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)
        setattr(namespace, "_snapshot_ttl_specified", True)


class SnapshotTimeoutAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)
        setattr(namespace, "_snapshot_timeout_specified", True)


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch a repository in a Modal Sandbox (Standard Container or Linux VM) with SSH & Cloudflare Ingress"
    )
    # Remote execution flags
    parser.add_argument(
        "--remote",
        action="store_true",
        help="Delegate execution to the hosted Modal control plane function.",
    )
    parser.add_argument(
        "--endpoint-url",
        default=None,
        metavar="URL",
        help="Override endpoint URL for --remote (defaults to MODAL_SANDBOX_ENDPOINT_URL).",
    )

    # Filesystem Snapshot capture flags
    parser.add_argument(
        "--snapshot",
        metavar="SANDBOX_ID",
        default=None,
        help="Capture a root filesystem snapshot of an active sandbox by ID.",
    )
    parser.add_argument(
        "--from-snapshot",
        metavar="IMAGE_ID",
        default=None,
        help="Launch a new sandbox restored from a filesystem snapshot image ID.",
    )
    parser.add_argument(
        "--snapshot-ttl",
        type=int,
        default=30,
        metavar="DAYS",
        action=SnapshotTTLAction,
        help="Snapshot retention time in days (default: 30 days).",
    )
    parser.add_argument(
        "--snapshot-timeout",
        type=int,
        default=DEFAULT_SNAPSHOT_TIMEOUT,
        metavar="SECONDS",
        action=SnapshotTimeoutAction,
        help=f"Snapshot filesystem capture timeout in seconds (default: {DEFAULT_SNAPSHOT_TIMEOUT}s).",
    )
    parser.add_argument(
        "--terminate",
        action="store_true",
        help="Terminate the target sandbox immediately after snapshot capture.",
    )

    # Standard sandbox launcher options
    parser.add_argument(
        "-n",
        "--name",
        dest="name",
        default=None,
        help="Instance name for standalone launches without a repository (e.g. standalone-my-box).",
    )
    parser.add_argument(
        "-b",
        "--github-branch",
        default="main",
        help="Git branch to checkout. Only branches are supported (not tags or commits). Default: main",
    )
    parser.add_argument(
        "--full-clone",
        action="store_true",
        help="Clone complete Git commit history instead of default shallow clone (--depth 50).",
    )
    parser.add_argument(
        "-r",
        "--repo",
        dest="repo",
        default=None,
        help="Target GitHub repository name (e.g. owner/repo or shorthand repo). When omitted, launches a Standalone Sandbox without repository fetch.",
    )

    parser.add_argument(
        "--testing",
        "--test",
        dest="testing",
        action="store_true",
        help="Use testing mode. The default organization's software-factory baseline keeps its repository name; other targets get a test- prefix.",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Also pre-bake a headless Google Chrome shared by the Playwright and Chrome DevTools MCP servers. Implied by --t3.",
    )
    parser.add_argument(
        "--t3",
        "--t3code",
        action="store_true",
        dest="t3",
        help="Also run a T3 Code server in the sandbox and expose its WebUI over public HTTPS URL.",
    )
    parser.add_argument(
        "--t3-port",
        type=int,
        default=DEFAULT_T3_PORT,
        help=f"Port for the T3 Code server, only used with --t3 (default: {DEFAULT_T3_PORT})",
    )
    parser.add_argument(
        "--t3-ssh-host",
        default=None,
        help="SSH host alias to use in T3 Code for 'Open in VS Code' links (defaults to sandbox instance name).",
    )
    parser.add_argument(
        "--t3-usage-volume",
        default=DEFAULT_T3_USAGE_VOLUME,
        help=f"Modal Volume name used to persist T3 Code usage and transcripts (default: {DEFAULT_T3_USAGE_VOLUME}).",
    )
    parser.add_argument(
        "--no-t3-persist",
        action="store_true",
        help="Disable persistent T3 Code usage and transcript volume synchronization across sandboxes.",
    )
    parser.add_argument(
        "--react-native",
        action="store_true",
        help="Also configure Android SDK, NDK, OpenJDK 17, Gradle cache volumes, and Metro bundler port forwarding for React Native.",
    )
    parser.add_argument(
        "--modal",
        action="store_true",
        help="Also configure Python 3, virtual environment, Modal SDK, and decrypt Modal client credentials.",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Modal workspace profile to launch the sandbox in and set as active in the sandbox.",
    )
    parser.add_argument(
        "--metro-port",
        type=int,
        default=DEFAULT_METRO_PORT,
        help=f"Port for the React Native Metro bundler, only used with --react-native (default: {DEFAULT_METRO_PORT})",
    )
    parser.add_argument(
        "--vm",
        action="store_true",
        help="Launch as a full Linux VM Sandbox (virtualization, Docker daemon, custom kernel privileges, swapfile allocation).",
    )
    parser.add_argument(
        "--memory",
        type=int,
        default=None,
        metavar="GB",
        help="(Deprecated) Formerly set static VM RAM; VM sandboxes now use burstable RAM (128, 16384) MiB. If provided with --vm, sizes swapfile to 2 * N GB.",
    )
    parser.add_argument(
        "--no-cloudflare",
        action="store_true",
        help="Disable the default Cloudflare Tunnel for this sandbox.",
    )
    parser.add_argument(
        "--no-ssh-config",
        action="store_true",
        help="Do not automatically append SSH connection details to ~/.ssh/config.",
    )
    parser.add_argument(
        "--sops",
        action="store_true",
        help="Retain SOPS age private key and credentials in ~/.config/sops for interactive debugging.",
    )
    parser.add_argument(
        "--xfce",
        action="store_true",
        help="Also run an XFCE 4 desktop with TigerVNC, noVNC, and Google Chrome exposed over Cloudflare Tunnel (implies --vm).",
    )
    parser.add_argument(
        "--xfce-port",
        type=int,
        default=DEFAULT_XFCE_PORT,
        help=f"Port for the noVNC web server, only used with --xfce (default: {DEFAULT_XFCE_PORT})",
    )
    parser.add_argument(
        "--xfce-password",
        default=None,
        help="Optional password for VNC / noVNC authentication (defaults to passwordless with auto-connect).",
    )
    return parser


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.endpoint_url and not args.remote:
        parser.error("--endpoint-url can only be used with --remote.")

    if args.snapshot:
        if args.from_snapshot:
            parser.error("--snapshot and --from-snapshot cannot be used together.")
        if args.repo:
            parser.error("--snapshot cannot be used with -r/--repo.")
        if args.name:
            parser.error("--snapshot cannot be used with --name.")
        if args.testing:
            parser.error("--snapshot cannot be used with --testing.")
        if args.vm:
            parser.error("--snapshot cannot be used with --vm.")
        if args.memory is not None:
            parser.error("--snapshot cannot be used with --memory.")
        if args.no_cloudflare:
            parser.error("--snapshot cannot be used with --no-cloudflare.")
        if args.github_branch != "main":
            parser.error("--snapshot cannot be used with --github-branch.")
        if args.snapshot_ttl <= 0:
            parser.error("--snapshot-ttl must be a positive integer.")
        if getattr(args, "snapshot_timeout", DEFAULT_SNAPSHOT_TIMEOUT) <= 0:
            parser.error("--snapshot-timeout must be a positive integer.")
        if (
            args.react_native
            or args.modal
            or getattr(args, "profile", None)
            or args.sops
            or args.browser
            or args.t3
            or args.t3_ssh_host
            or getattr(args, "no_t3_persist", False)
            or getattr(args, "t3_usage_volume", DEFAULT_T3_USAGE_VOLUME) != DEFAULT_T3_USAGE_VOLUME
            or getattr(args, "xfce", False)
            or args.full_clone
            or getattr(args, "no_ssh_config", False)
        ):
            parser.error("--snapshot cannot be used with launch configuration arguments.")
    else:
        if args.terminate:
            parser.error("--terminate can only be used with --snapshot.")
        if getattr(args, "_snapshot_ttl_specified", False):
            parser.error("--snapshot-ttl can only be used with --snapshot.")
        if getattr(args, "_snapshot_timeout_specified", False):
            parser.error("--snapshot-timeout can only be used with --snapshot.")
        if args.repo and args.name:
            parser.error(
                "--name cannot be used with -r/--repo: --name is strictly for standalone launches without -r/--repo."
            )
        if args.from_snapshot and not args.repo and not args.name:
            parser.error("--name is required when launching from a snapshot without -r/--repo.")
        if not args.repo and not args.name:
            parser.error("--name is required when launching without -r/--repo.")
        if not args.repo and args.github_branch != "main":
            parser.error("--github-branch cannot be used without -r/--repo.")
        if not args.repo and args.testing:
            parser.error("--testing cannot be used without -r/--repo.")
        if args.from_snapshot and args.full_clone:
            parser.error("--full-clone cannot be used with --from-snapshot.")
        if not args.repo and args.full_clone:
            parser.error("--full-clone cannot be used without -r/--repo.")
        if args.t3_ssh_host and not args.t3:
            parser.error("--t3-ssh-host can only be used with --t3.")
        if getattr(args, "no_t3_persist", False) and not args.t3:
            parser.error("--no-t3-persist can only be used with --t3.")
        if getattr(args, "t3_usage_volume", DEFAULT_T3_USAGE_VOLUME) != DEFAULT_T3_USAGE_VOLUME and not args.t3:
            parser.error("--t3-usage-volume can only be used with --t3.")
        if getattr(args, "no_t3_persist", False) and getattr(args, "t3_usage_volume", DEFAULT_T3_USAGE_VOLUME) != DEFAULT_T3_USAGE_VOLUME:
            parser.error("--no-t3-persist and --t3-usage-volume cannot be used together.")


def capture_snapshot(
    sandbox_id: str,
    ttl_days: int = 30,
    terminate: bool = False,
    timeout: int = DEFAULT_SNAPSHOT_TIMEOUT,
) -> str:
    from sandbox.snapshots import capture_sandbox_snapshot

    result = capture_sandbox_snapshot(
        sandbox_id=sandbox_id,
        ttl_days=ttl_days,
        terminate=terminate,
        timeout=timeout,
        echo=True,
    )
    return result.image_id
