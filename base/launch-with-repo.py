import argparse
from pathlib import Path
import uuid
import modal

LOCAL_STARTUP_SCRIPT = Path(__file__).parent / "startup.sh"
REMOTE_STARTUP_SCRIPT = "/root/startup.sh"

# Static base image: built once and cached by Modal
base_image = (
    modal.Image.from_registry("node:24-bookworm-slim")
    .apt_install("curl", "git", "gh")
    .run_commands(
        "corepack enable pnpm",
        "corepack prepare pnpm@10.31.0 --activate",
    )
)

# Bundle startup script into the image
base_image = base_image.add_local_file(
    LOCAL_STARTUP_SCRIPT, REMOTE_STARTUP_SCRIPT, copy=True
)


def parse_timeout(timeout_str: str) -> int:
    """Parses human-friendly timeout (e.g. '2h', '90m', '12') into seconds."""
    if timeout_str.endswith("h"):
        minutes = int(timeout_str[:-1]) * 60
    elif timeout_str.endswith("m"):
        minutes = int(timeout_str[:-1])
    else:
        minutes = int(timeout_str) * 60

    if not (1 <= minutes <= 24 * 60):
        raise argparse.ArgumentTypeError("Timeout must be between 1 minute and 24 hours.")
    return minutes * 60


def print_access_info(sandbox: modal.Sandbox, secret_collection: str, app_name: str):
    tunnel = sandbox.tunnels()[3000]
    print("\n" + "=" * 50)
    print("🏝️  Sandbox Ready!")
    print(f"  • App:     {app_name}")
    print(f"  • WebUI:   {tunnel.url}")
    print(f"  • Shell:   modal shell {sandbox.object_id}")
    print("=" * 50 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Launch a repository in a Modal Sandbox")
    parser.add_argument(
        "--timeout",
        default="12",
        help="Timeout (e.g., 2h, 90m, or raw hours). Default: 12h",
    )
    parser.add_argument(
        "--github-ref",
        default="main",
        help="Git ref to checkout (branch, tag, commit). Default: main",
    )
    parser.add_argument(
        "-s", "--secret", "--secret-collection",
        dest="secret_collection",
        required=True,
        help="Modal Secret collection name.",
    )
    args = parser.parse_args()

    random_id = uuid.uuid4().hex[:8]
    app_name = f"{args.secret_collection}-{random_id}"

    app = modal.App.lookup(app_name, create_if_missing=True)
    secret = modal.Secret.from_name(args.secret_collection)

    print(f"🏝️  Launching Modal Sandbox (App: {app_name})...")
    with modal.enable_output():
        sandbox = modal.Sandbox.create(
            "bash",
            REMOTE_STARTUP_SCRIPT,
            args.github_ref,
            secrets=[secret],
            timeout=parse_timeout(args.timeout),
            image=base_image,
            app=app,
        )

    print_access_info(sandbox, args.secret_collection, app_name)


if __name__ == "__main__":
    main()
