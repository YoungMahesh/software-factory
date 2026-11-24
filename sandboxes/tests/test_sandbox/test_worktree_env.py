"""Unit tests for Git worktree environment secret propagation hook."""

import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


class TestWorktreeEnvPropagation(unittest.TestCase):
    def setUp(self):
        self.hook_script = Path(__file__).resolve().parents[2] / "shared" / "git-hooks" / "post-checkout"
        self.assertTrue(self.hook_script.is_file(), f"Hook script not found at {self.hook_script}")

    def _init_git_repo(self, repo_dir: Path) -> None:
        """Initializes a valid Git repository with initial commit."""
        subprocess.run(["git", "init", "-b", "main", str(repo_dir)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "Test User"], check=True)
        subprocess.run(["git", "-C", str(repo_dir), "config", "user.email", "test@example.com"], check=True)
        (repo_dir / "README.md").write_text("# Test Repo\n")
        subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", "Initial commit"], check=True, capture_output=True)

    def test_worktree_propagation_with_env_map(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "main-repo"
            repo.mkdir()
            self._init_git_repo(repo)

            # Setup .git/env-vault with env.map and mapped secret files
            vault_dir = repo / ".git" / "env-vault"
            vault_dir.mkdir(parents=True)
            (vault_dir / "env.map").write_text("web.env = apps/web/.env\napi.env = packages/api/.env.local\n")
            (vault_dir / "web.env").write_text("WEB_PORT=3000\n")
            (vault_dir / "api.env").write_text("API_SECRET=supersecret\n")

            # Configure global/local hooksPath pointing to our hook
            hooks_dir = root / "git-hooks"
            hooks_dir.mkdir()
            hook_dest = hooks_dir / "post-checkout"
            hook_dest.write_bytes(self.hook_script.read_bytes())
            hook_dest.chmod(0o755)

            subprocess.run(
                ["git", "-C", str(repo), "config", "core.hooksPath", str(hooks_dir)],
                check=True,
            )

            # Create new worktree
            wt_dir = root / "worktrees" / "wt-1"
            res = subprocess.run(
                ["git", "-C", str(repo), "worktree", "add", "-b", "feature-1", str(wt_dir), "main"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, f"git worktree add failed: {res.stderr}")

            # Verify files were propagated to destination paths
            web_env = wt_dir / "apps" / "web" / ".env"
            api_env = wt_dir / "packages" / "api" / ".env.local"
            self.assertTrue(web_env.is_file(), f"Expected {web_env} to exist")
            self.assertTrue(api_env.is_file(), f"Expected {api_env} to exist")
            self.assertEqual(web_env.read_text(), "WEB_PORT=3000\n")
            self.assertEqual(api_env.read_text(), "API_SECRET=supersecret\n")

            # Verify permissions (0600)
            mode = stat.S_IMODE(web_env.stat().st_mode)
            self.assertEqual(mode, 0o600)

    def test_worktree_propagation_non_destructive(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "main-repo"
            repo.mkdir()
            self._init_git_repo(repo)

            vault_dir = repo / ".git" / "env-vault"
            vault_dir.mkdir(parents=True)
            (vault_dir / "env.map").write_text("default.env = .env\n")
            (vault_dir / "default.env").write_text("VAULT_VAR=original\n")

            hooks_dir = root / "git-hooks"
            hooks_dir.mkdir()
            hook_dest = hooks_dir / "post-checkout"
            hook_dest.write_bytes(self.hook_script.read_bytes())
            hook_dest.chmod(0o755)

            subprocess.run(
                ["git", "-C", str(repo), "config", "core.hooksPath", str(hooks_dir)],
                check=True,
            )

            wt_dir = root / "worktrees" / "wt-1"
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "add", "-b", "feature-1", str(wt_dir), "main"],
                check=True,
                capture_output=True,
            )

            # Pre-existing/modified .env in worktree
            wt_env = wt_dir / ".env"
            self.assertTrue(wt_env.is_file())
            wt_env.write_text("VAULT_VAR=modified_by_agent\n")

            # Checkout another branch or commit in the same worktree
            subprocess.run(
                ["git", "-C", str(wt_dir), "checkout", "-b", "feature-sub"],
                check=True,
                capture_output=True,
            )

            # Must preserve modified_by_agent
            self.assertEqual(wt_env.read_text(), "VAULT_VAR=modified_by_agent\n")

    def test_worktree_propagation_zero_config_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "main-repo"
            repo.mkdir()
            self._init_git_repo(repo)

            # No env.map in .git/env-vault, but main repo has .env and .env.local
            (repo / ".env").write_text("MAIN_KEY=val1\n")
            (repo / ".env.local").write_text("LOCAL_KEY=val2\n")

            hooks_dir = root / "git-hooks"
            hooks_dir.mkdir()
            hook_dest = hooks_dir / "post-checkout"
            hook_dest.write_bytes(self.hook_script.read_bytes())
            hook_dest.chmod(0o755)

            subprocess.run(
                ["git", "-C", str(repo), "config", "core.hooksPath", str(hooks_dir)],
                check=True,
            )

            wt_dir = root / "worktrees" / "wt-fallback"
            res = subprocess.run(
                ["git", "-C", str(repo), "worktree", "add", "-b", "feature-fallback", str(wt_dir), "main"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, f"git worktree add failed: {res.stderr}")

            wt_env = wt_dir / ".env"
            wt_local = wt_dir / ".env.local"
            self.assertTrue(wt_env.is_file(), f"Expected {wt_env} to exist")
            self.assertTrue(wt_local.is_file(), f"Expected {wt_local} to exist")
            self.assertEqual(wt_env.read_text(), "MAIN_KEY=val1\n")
            self.assertEqual(wt_local.read_text(), "LOCAL_KEY=val2\n")

    def test_worktree_propagation_chains_local_hook(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "main-repo"
            repo.mkdir()
            self._init_git_repo(repo)

            # Add a local repo hook in repo/.git/hooks/post-checkout
            local_hook = repo / ".git" / "hooks" / "post-checkout"
            marker_file = root / "local_hook_marker.txt"
            local_hook.write_text(f"#!/bin/sh\necho 'CALLED' > '{marker_file}'\n")
            local_hook.chmod(0o755)

            hooks_dir = root / "git-hooks"
            hooks_dir.mkdir()
            hook_dest = hooks_dir / "post-checkout"
            hook_dest.write_bytes(self.hook_script.read_bytes())
            hook_dest.chmod(0o755)

            subprocess.run(
                ["git", "-C", str(repo), "config", "core.hooksPath", str(hooks_dir)],
                check=True,
            )

            wt_dir = root / "worktrees" / "wt-chain"
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "add", "-b", "feature-chain", str(wt_dir), "main"],
                check=True,
                capture_output=True,
            )

            self.assertTrue(marker_file.is_file(), "Expected local hook marker file to be created")
            self.assertEqual(marker_file.read_text().strip(), "CALLED")


if __name__ == "__main__":
    unittest.main()
