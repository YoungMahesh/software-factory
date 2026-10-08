#!/usr/bin/env python3
"""Live Integration Test for Modal Software Factory Spawner and Container Entrypoint.

Tests the full orchestration path:
1. Provisions an ephemeral Modal Sandbox via `dispatch_job` with `--testing` targeting `test3`.
2. Stages `secrets_testing/test3/`, mounts `/root/factory_entrypoint.sh` and `/root/factory`.
3. Inside the container:
   - SOPS Age key bootstrap from `share0`
   - Decrypts OpenCode credentials to `/root/.config/opencode/opencode.env`
   - Decrypts fetch.env and clones `anveshak71/test3` to `/root/test3`
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
    fetch_path = root_dir / "secrets_testing" / "test3" / "fetch.env"
    cmd = f"SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt sops -d '{fetch_path}'"
    out = subprocess.check_output(cmd, shell=True, text=True)
    repo, token = "", ""
    for line in out.splitlines():
        if line.startswith("GH_REPO="):
            repo = line.split("=", 1)[1].strip().strip("\"'")
        elif line.startswith("GH_TOKEN="):
            token = line.split("=", 1)[1].strip().strip("\"'")
    return repo, token


def main() -> None:
    print("================================================================")
    print("🚀 Live Modal Cloud Sandbox Factory Spawner Verification")
    print("   Target: secrets_testing/test3 (anveshak71/test3)")
    print("   Feature: slug-generator")
    print("================================================================\n")

    test3_fetch = root_dir / "secrets_testing" / "test3" / "fetch.env"
    if not test3_fetch.is_file():
        raise FileNotFoundError(f"Missing {test3_fetch}")

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
