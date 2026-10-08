import sys
import time
from pathlib import Path
import modal

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from shared.image import (
    REMOTE_REPO_SECRETS_DIR,
    REMOTE_STARTUP_SCRIPT,
    SHARED_SECRET_NAME,
    build_sandbox_image,
    load_ssh_pub_key,
)


def main():
    print("================================================================")
    print("🚀 Starting Phase 2: Live Ephemeral Modal Sandbox Assembly Line Verification")
    print("================================================================\n")

    secret_name = "test3"
    secret_dir = root_dir / "secrets_testing" / secret_name
    secret_file = secret_dir / "fetch.env"

    if not secret_file.is_file():
        raise FileNotFoundError(f"Missing {secret_file}")

    app_name = "test-factory-assembly-line"
    app = modal.App.lookup(app_name, create_if_missing=True)

    pubkey = load_ssh_pub_key()

    print("📦 Building sandbox image with OpenCode support, test3 secrets, and factory harness...")
    image = build_sandbox_image(opencode=True)
    image = image.add_local_dir(secret_dir, REMOTE_REPO_SECRETS_DIR, copy=True)
    image = (
        image.add_local_dir(root_dir / "sandbox" / "factory", "/root/factory", copy=True)
        .run_commands("cd /root/factory && pnpm install --force --shamefully-hoist")
    )

    env = {
        "SSH_AUTHORIZED_KEY": pubkey,
        "PORT": "3000",
        "HOSTNAME": "0.0.0.0",
        "APP_NAME": app_name,
        "ENABLE_CLOUDFLARE": "0",
        "ENABLE_OPENCODE": "1",
    }

    sandbox_secrets = [modal.Secret.from_name(SHARED_SECRET_NAME)]

    print(f"📦 Provisioning ephemeral Modal Sandbox for {secret_name}...")
    sandbox = modal.Sandbox.create(
        "bash",
        REMOTE_STARTUP_SCRIPT,
        "main",
        image=image,
        app=app,
        secrets=sandbox_secrets,
        timeout=600,
        idle_timeout=180,
        unencrypted_ports=[22],
        cpu=(0.5, 2.0),
        memory=(512, 4096),
        env=env,
    )

    try:
        print(f"🏝️  Sandbox {sandbox.object_id} launched. Waiting for repository checkout & OpenCode setup...")

        # Wait for /root/test3 to be cloned and startup.sh to finish repo setup
        ready = False
        for attempt in range(60):
            proc = sandbox.exec("bash", "-c", "test -d /root/test3/.scratch && test -f /root/.config/opencode/opencode.env && echo READY || echo WAITING")
            out = proc.stdout.read().strip()
            if "READY" in out:
                ready = True
                print("✅ Target repository /root/test3 and OpenCode credentials are ready inside sandbox!")
                break
            time.sleep(2)

        if not ready:
            raise TimeoutError("Timed out waiting for repository checkout and credentials in sandbox")

        print("🔍 Executing in-container assembly line verification (/root/factory/in-container-test.ts)...")

        test_proc = sandbox.exec(
            "node",
            "--experimental-strip-types",
            "/root/factory/in-container-test.ts",
            workdir="/root/factory",
        )

        for line in test_proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()

        stderr = test_proc.stderr.read()
        if stderr:
            sys.stderr.write(stderr)
            sys.stderr.flush()

        returncode = test_proc.wait()
        if returncode != 0:
            raise RuntimeError(f"In-container assembly line test failed with exit code {returncode}")

        print("\n🎉 Phase 2 Modal Cloud Sandbox Assembly Line Verification PASSED!")

    finally:
        print(f"🧹 Terminating ephemeral sandbox {sandbox.object_id}...")
        sandbox.terminate()
        print("🏁 Ephemeral sandbox terminated cleanly.")


if __name__ == "__main__":
    main()
