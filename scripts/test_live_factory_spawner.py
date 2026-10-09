#!/usr/bin/env python3
"""Live Integration Test for Modal Software Factory Spawner and Container Entrypoint.

Tests the full orchestration path:
1. Provisions an ephemeral Modal Sandbox via `dispatch_job` with `--testing` targeting `test3`.
2. Stages `secrets_org/software-factory-09-test/`, mounts `/root/factory_entrypoint.sh` and `/root/factory`.
3. Inside the container:
   - SOPS Age key bootstrap from `share0`
   - Decrypts OpenCode credentials to `/root/.config/opencode/opencode.env`
   - Decrypts token and clones `software-factory-09-test/test3` to `/root/test3`
   - Checks out `factory/slug-generator`
   - Maps repository environment secrets (`web.env` -> `.env`)
   - Preserves `GH_TOKEN` for pushing
   - Runs `/root/factory/pipeline.ts` for Autonomous Feature Batch
4. Streams live execution logs to stdout.
5. Verifies exit code 0 and verifies the pushed remote branch on GitHub.
"""

from pathlib import Path
import subprocess
import sys

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from factory.orchestrator import dispatch_job


def decrypt_token_and_repo() -> tuple[str, str]:
    token_path = root_dir / "secrets_org" / "software-factory-09-test" / "token"
    cmd = f"SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt sops -d '{token_path}'"
    token = subprocess.check_output(cmd, shell=True, text=True).strip()
    repo = "software-factory-09-test/test3"
    return repo, token


def main() -> None:
    print("================================================================")
    print("🚀 Live Modal Cloud Sandbox Factory Spawner Verification")
    print("   Target: software-factory-09-test/test3")
    print("   Feature: slug-generator")
    print("================================================================\n")

    test3_token = root_dir / "secrets_org" / "software-factory-09-test" / "token"
    if not test3_token.is_file():
        raise FileNotFoundError(f"Missing {test3_token}")

    print("🛰️  Dispatching software factory job to Modal cloud sandbox...")
    start_time = subprocess.check_output(["date", "+%s"], text=True).strip()

    exit_code = dispatch_job(
        project="test3",
        feature="slug-generator",
        testing=True,
        timeout_secs=900,  # 15 minutes upper bound for test run
    )

    print(f"\n🏁 Sandbox execution completed with exit code: {exit_code}")

    if exit_code != 0:
        print(f"❌ Live factory sandbox test FAILED with exit code {exit_code}")
        sys.exit(exit_code)

    # Verify remote branch on GitHub
    print("\n🔍 Verifying pushed feature branch on remote GitHub repository...")
    repo, token = decrypt_token_and_repo()
    url = f"https://x-access-token:{token}@github.com/{repo}.git"
    heads = subprocess.check_output(
        ["git", "ls-remote", "--heads", url, "factory/slug-generator"],
        text=True,
        env={"GIT_TERMINAL_PROMPT": "0"},
    )
    print("Remote ref:\n" + heads.strip())

    if "refs/heads/factory/slug-generator" not in heads:
        print("❌ Error: factory/slug-generator was NOT found on remote origin!")
        sys.exit(1)

    print("✅ Remote branch refs/heads/factory/slug-generator verified on GitHub origin!")
    print("\n🎉 LIVE MODAL FACTORY SANDBOX SPAWNER VERIFICATION PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
