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
    print("🚀 Starting Phase 2: Live Ephemeral Modal Sandbox Pre-flight Verification")

    secret_name = "test2"
    feature_slug = "queues-page"
    secret_dir = root_dir / "secrets_org" / "software-factory-09-test"
    token_file = secret_dir / "token"

    if not token_file.is_file():
        raise FileNotFoundError(f"Missing {token_file}")

    app_name = "test-preflight-verifier"
    app = modal.App.lookup(app_name, create_if_missing=True)

    pubkey = load_ssh_pub_key()

    # Build image with secrets_org/software-factory-09-test and sandbox/factory staged
    image = build_sandbox_image()
    image = image.add_local_dir(secret_dir, "/root/secrets/org", copy=True)
    image = image.add_local_dir(root_dir / "sandbox" / "factory", "/root/factory", copy=True)

    env = {
        "SSH_AUTHORIZED_KEY": pubkey,
        "PORT": "3000",
        "HOSTNAME": "0.0.0.0",
        "APP_NAME": app_name,
        "ENABLE_CLOUDFLARE": "0",
        "GH_REPO": f"software-factory-09-test/{secret_name}",
    }

    sandbox_secrets = [modal.Secret.from_name(SHARED_SECRET_NAME)]

    print(f"📦 Creating ephemeral Modal Sandbox for {secret_name}...")
    sandbox = modal.Sandbox.create(
        "bash",
        REMOTE_STARTUP_SCRIPT,
        "main",
        image=image,
        app=app,
        secrets=sandbox_secrets,
        timeout=300,
        idle_timeout=120,
        unencrypted_ports=[22],
        cpu=(0.125, 2.0),
        memory=(128, 4096),
        env=env,
    )

    try:
        print(f"🏝️  Sandbox {sandbox.object_id} launched. Waiting for repository checkout...")

        # Wait for /root/test2 to be cloned and startup.sh to finish repo setup
        ready = False
        for attempt in range(45):
            proc = sandbox.exec("bash", "-c", "test -d /root/test2/.scratch && echo READY || echo WAITING")
            out = proc.stdout.read().strip()
            if "READY" in out:
                ready = True
                print("✅ Target repository /root/test2 is cloned and ready inside sandbox!")
                break
            time.sleep(2)

        if not ready:
            raise TimeoutError("Timed out waiting for repository checkout in sandbox")

        print("🔍 Executing preflight validation and ticket discovery inside sandbox...")

        js_code = """
import * as fs from 'node:fs';
import { validatePreflight, parseTickets, getNextFrontierTicket } from '/root/factory/preflight.ts';

// 1. Positive validation on cloned real test2 repository (queues-page)
const result = validatePreflight('/root/test2', 'queues-page');
console.log('TEST2_PREFLIGHT_VALID=' + result.valid);
if (!result.valid) {
  console.error('TEST2_PREFLIGHT_ERRORS=' + JSON.stringify(result.errors));
  process.exit(1);
}

const tickets = parseTickets('/root/test2', 'queues-page');
console.log('TEST2_TICKETS_COUNT=' + tickets.length);

const next = getNextFrontierTicket(tickets);
if (!next) {
  console.error('NO_FRONTIER_TICKET');
  process.exit(2);
}
console.log('NEXT_TICKET_ID=' + next.id);
console.log('NEXT_TICKET_TITLE=' + next.title);
console.log('NEXT_TICKET_STATUS=' + next.status);

// 2. Negative validation on unconfigured repository
fs.mkdirSync('/tmp/empty-repo', { recursive: true });
const negResult = validatePreflight('/tmp/empty-repo', 'feature-x');
console.log('EMPTY_REPO_PREFLIGHT_VALID=' + negResult.valid);
console.log('EMPTY_REPO_ERRORS_COUNT=' + negResult.errors.length);
if (negResult.valid !== false || negResult.errors.length !== 3) {
  console.error('Expected negative validation to fail with 3 errors');
  process.exit(3);
}
"""

        verify_proc = sandbox.exec(
            "node",
            "--experimental-strip-types",
            "--input-type=module",
            "-e",
            js_code,
        )
        stdout = verify_proc.stdout.read()
        stderr = verify_proc.stderr.read()
        returncode = verify_proc.wait()

        print("\n--- Sandbox In-Container Output ---")
        print(stdout)
        if stderr:
            print("STDERR:", stderr)

        if returncode != 0:
            raise RuntimeError(f"Verification failed inside sandbox with code {returncode}")

        print("🧪 Also running full preflight unit test suite inside the container...")
        test_proc = sandbox.exec(
            "node",
            "--test",
            "--experimental-strip-types",
            "/root/factory/preflight.test.ts",
        )
        unit_test_out = test_proc.stdout.read()
        unit_returncode = test_proc.wait()
        print(unit_test_out)

        if unit_returncode != 0:
            raise RuntimeError(f"Unit tests failed inside sandbox with code {unit_returncode}")

        print("🎉 Both in-container preflight validation and unit tests passed successfully!")

    finally:
        print(f"🧹 Terminating ephemeral sandbox {sandbox.object_id}...")
        sandbox.terminate()
        print("🏁 Sandbox terminated.")


if __name__ == "__main__":
    main()
