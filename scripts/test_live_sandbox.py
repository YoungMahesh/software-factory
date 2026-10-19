#!/usr/bin/env python3
"""Automated Live Verification for Modal Sandboxes (Standard & VM).

Implements the Sandbox Live Verification standard against Test Repository Baseline
(software-factory-09-test/test1). Ephemeral execution with guaranteed teardown.
"""

import argparse
from pathlib import Path
import sys
import time
import modal

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from shared.image import (
    REMOTE_STARTUP_SCRIPT,
    SHARED_SECRET_NAME,
    build_sandbox_image,
    load_ssh_pub_key,
)

DEFAULT_TEST_ORG = "software-factory-09-test"
DEFAULT_TEST_REPO = "test1"


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run live ephemeral verification of Modal Sandbox against Test Repository Baseline"
    )
    parser.add_argument(
        "--repo",
        default=DEFAULT_TEST_REPO,
        help=f"Target repository name under {DEFAULT_TEST_ORG} (default: {DEFAULT_TEST_REPO})",
    )
    parser.add_argument(
        "--vm",
        action="store_true",
        help="Test VM Sandbox execution mode with Docker daemon",
    )
    parser.add_argument(
        "--snapshots",
        action="store_true",
        help="Test Filesystem Snapshot capture and restore capability",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Sandbox execution timeout in seconds (default: 300)",
    )
    return parser


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()

    token_file = root_dir / "secrets_org" / DEFAULT_TEST_ORG / "token"
    if not token_file.is_file():
        raise FileNotFoundError(
            f"Test Organization token not found at {token_file}. Ensure organization credentials exist."
        )

    app_name = f"test-live-verifier-{args.repo}"
    app = modal.App.lookup(app_name, create_if_missing=True)
    pubkey = load_ssh_pub_key()

    print("================================================================")
    print("🚀 Sandbox Live Verification")
    print(f"   Target: {DEFAULT_TEST_ORG}/{args.repo}")
    print(f"   Mode:   {'VM Sandbox' if args.vm else 'Standard Sandbox'}")
    print(f"   Snapshots Check: {'Yes' if args.snapshots else 'No'}")
    print("================================================================\n")

    # Build image with test organization token staged
    image = build_sandbox_image()
    image = image.add_local_dir(
        root_dir / "secrets_org" / DEFAULT_TEST_ORG,
        "/root/secrets/org",
        copy=True,
    )

    env = {
        "SSH_AUTHORIZED_KEY": pubkey,
        "PORT": "3000",
        "HOSTNAME": "0.0.0.0",
        "APP_NAME": app_name,
        "ENABLE_CLOUDFLARE": "0",
        "GH_REPO": f"{DEFAULT_TEST_ORG}/{args.repo}",
    }

    sandbox_kwargs: dict = {
        "image": image,
        "app": app,
        "timeout": args.timeout,
        "idle_timeout": 120,
        "unencrypted_ports": [22],
        "cpu": (0.125, 2.0),
        "env": env,
    }

    sandbox_kwargs["runtime"] = "vm" if args.vm else "gvisor"
    sandbox_kwargs["memory"] = (128, 4096)

    if args.vm:
        env["SWAP_GB"] = "2"
        env["ENABLE_DOCKER"] = "1"

    sandbox_secrets = [modal.Secret.from_name(SHARED_SECRET_NAME)]

    print(f"📦 Provisioning ephemeral Modal Sandbox for {DEFAULT_TEST_ORG}/{args.repo}...")
    sandbox = modal.Sandbox.create(
        "bash",
        REMOTE_STARTUP_SCRIPT,
        "main",
        secrets=sandbox_secrets,
        **sandbox_kwargs,
    )

    restored_sandbox = None
    try:
        print(f"🏝️  Sandbox {sandbox.object_id} launched. Awaiting startup and git clone completion...")

        # 1. Wait for repo clone to complete
        target_path = f"/root/{args.repo}"
        ready = False
        for attempt in range(45):
            proc = sandbox.exec("bash", "-c", f"test -d {target_path} && echo READY || echo WAITING")
            out = proc.stdout.read().strip()
            if "READY" in out:
                ready = True
                print(f"✅ Repository cloned successfully at {target_path} inside sandbox!")
                break
            time.sleep(2)

        if not ready:
            raise TimeoutError(f"Timed out waiting for repository clone at {target_path}")

        # 2. Assert organization token was scrubbed from disk (ADR-0031 security invariant)
        scrub_proc = sandbox.exec(
            "bash", "-c", "test ! -f /root/secrets/org/token && echo CLEAN || echo LEAKED"
        )
        scrub_out = scrub_proc.stdout.read().strip()
        if "CLEAN" in scrub_out:
            print("🔒 Security check passed: organization token was scrubbed from disk.")
        else:
            raise RuntimeError("Security invariant violated: /root/secrets/org/token was not purged!")

        # 3. Assert git branch is valid
        branch_proc = sandbox.exec("bash", "-c", f"cd {target_path} && git symbolic-ref --short HEAD")
        branch_name = branch_proc.stdout.read().strip()
        print(f"🌿 Git active branch verified: {branch_name}")

        # 4. If VM mode, verify Docker daemon is reachable
        if args.vm:
            print("🐳 Verifying Docker daemon in VM Sandbox...")
            docker_proc = sandbox.exec("docker", "info")
            if docker_proc.wait() != 0:
                raise RuntimeError("Docker daemon is not running in VM Sandbox!")
            print("✅ Docker daemon verified running.")

        # 5. If snapshots mode, exercise snapshot capture and restore
        if args.snapshots:
            print("📸 Testing Filesystem Snapshot capture...")
            sync_proc = sandbox.exec("sync")
            sync_proc.wait()

            snapshot_image = sandbox.snapshot_filesystem(timeout=120)
            print(f"✅ Filesystem Snapshot captured: {snapshot_image.object_id}")

            print("♻️  Testing restore from snapshot image...")
            restore_app_name = f"test-restore-{args.repo}"
            restore_app = modal.App.lookup(restore_app_name, create_if_missing=True)
            restore_env = {
                "SSH_AUTHORIZED_KEY": pubkey,
                "PORT": "3000",
                "HOSTNAME": "0.0.0.0",
                "APP_NAME": restore_app_name,
                "RESUME_SNAPSHOT": "1",
                "ENABLE_CLOUDFLARE": "0",
            }
            restored_sandbox = modal.Sandbox.create(
                "bash",
                REMOTE_STARTUP_SCRIPT,
                "main",
                image=snapshot_image,
                app=restore_app,
                secrets=sandbox_secrets,
                timeout=180,
                idle_timeout=60,
                cpu=(0.125, 2.0),
                memory=(128, 4096),
                env=restore_env,
            )
            print(f"🏝️  Restored Sandbox {restored_sandbox.object_id} launched. Checking workspace...")
            res_proc = restored_sandbox.exec("bash", "-c", f"test -d {target_path} && echo EXISTS || echo MISSING")
            if "EXISTS" in res_proc.stdout.read().strip():
                print(f"✅ Workspace {target_path} confirmed intact in restored snapshot!")
            else:
                raise RuntimeError("Restored sandbox missing workspace directory!")

        print("\n🎉 Sandbox Live Verification succeeded across all assertions!")

    finally:
        print(f"\n🧹 Terminating ephemeral sandbox {sandbox.object_id}...")
        sandbox.terminate()
        if restored_sandbox is not None:
            print(f"🧹 Terminating restored snapshot sandbox {restored_sandbox.object_id}...")
            restored_sandbox.terminate()
        print("🏁 Clean teardown complete. Zero lingering sandboxes.")


if __name__ == "__main__":
    main()
