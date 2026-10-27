"""Subsystem tests for Modal Sandbox runner and configuration."""

from pathlib import Path
import subprocess
import unittest
from unittest.mock import ANY, MagicMock, patch


class TestSandboxShellAliases(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]
        self.aliases_path = self.repo_root / "shared" / "aliases.bash"
        self.legacy_git_bash = self.repo_root / "git.bash"
        self.startup_sh_path = self.repo_root / "shared" / "startup.sh"

    def test_legacy_git_bash_removed(self):
        self.assertFalse(self.legacy_git_bash.exists(), "Legacy root git.bash should be removed")

    def test_shared_aliases_file_exists_and_contains_requested_aliases(self):
        self.assertTrue(self.aliases_path.is_file(), "shared/aliases.bash must exist")
        content = self.aliases_path.read_text()

        expected_docker_aliases = [
            "alias dc='docker container'",
            "alias dco='docker compose'",
            "alias di='docker image'",
            "alias din='docker inspect'",
            "alias dl='docker logs'",
            "alias dn='docker network'",
            "alias dv='docker volume'",
        ]
        expected_git_aliases = [
            "alias gs='git status'",
            "alias gd='git diff'",
            "alias gds='git diff --cached'",
            "alias ga='git add .'",
            "alias gl='git log'",
            "alias gc='git commit -m'",
            "alias gp='git push'",
            "alias gP='git pull'",
            "alias gb='git branch'",
        ]

        for alias in expected_docker_aliases:
            self.assertIn(alias, content, f"Missing Docker alias: {alias}")

        for alias in expected_git_aliases:
            self.assertIn(alias, content, f"Missing Git alias: {alias}")

    def test_image_and_startup_script_stage_and_source_bash_aliases(self):
        from shared.image import LOCAL_ALIASES_BASH, REMOTE_ALIASES_BASH

        self.assertEqual(LOCAL_ALIASES_BASH, self.aliases_path)
        self.assertEqual(REMOTE_ALIASES_BASH, "/root/.bash_aliases")

        startup_content = self.startup_sh_path.read_text()
        self.assertIn('if [ -f /root/.bash_aliases ]; then', startup_content)
        self.assertIn('source /root/.bash_aliases', startup_content)
        self.assertNotIn('/root/.git.bash', startup_content)

class TestSandboxGitConfig(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]
        self.gitconfig_path = self.repo_root / "shared" / "gitconfig"
        self.gitconfig_mahesh_path = self.repo_root / "shared" / "gitconfig-mahesh471978"
        self.startup_sh_path = self.repo_root / "shared" / "startup.sh"

    def test_git_configs_registered_in_base_image_manifest(self):
        from shared.image import (
            BASE_IMAGE_FILES,
            LOCAL_GITCONFIG,
            REMOTE_GITCONFIG,
            LOCAL_GITCONFIG_MAHESH471978,
            REMOTE_GITCONFIG_MAHESH471978,
        )

        self.assertEqual(LOCAL_GITCONFIG, self.gitconfig_path)
        self.assertEqual(REMOTE_GITCONFIG, "/root/.gitconfig")
        self.assertEqual(LOCAL_GITCONFIG_MAHESH471978, self.gitconfig_mahesh_path)
        self.assertEqual(REMOTE_GITCONFIG_MAHESH471978, "/root/.gitconfig-mahesh471978")

        self.assertIn((LOCAL_GITCONFIG, REMOTE_GITCONFIG), BASE_IMAGE_FILES)
        self.assertIn(
            (LOCAL_GITCONFIG_MAHESH471978, REMOTE_GITCONFIG_MAHESH471978),
            BASE_IMAGE_FILES,
        )
        self.assertTrue(LOCAL_GITCONFIG.exists())
        self.assertTrue(LOCAL_GITCONFIG_MAHESH471978.exists())

    def test_base_gitconfig_declares_primary_identity_and_conditional_inclusion(self):
        content = self.gitconfig_path.read_text()
        self.assertIn("name = Mahesh", content)
        self.assertIn("email = maheshghamand@gmail.com", content)
        self.assertIn('[includeIf "gitdir:/root/intrifund/"]', content)
        self.assertIn("path = ~/.gitconfig-mahesh471978", content)

    def test_secondary_gitconfig_is_pure_delta_override_without_redundant_name(self):
        secondary_content = self.gitconfig_mahesh_path.read_text()
        self.assertIn("email = mahesh471978@gmail.com", secondary_content)
        self.assertNotIn(
            "name",
            secondary_content,
            "Secondary profile should not redeclare name; it inherits from base gitconfig",
        )

    def test_startup_script_does_not_mutate_git_config_inline(self):
        startup_content = self.startup_sh_path.read_text()
        self.assertNotIn("git config --global user.email", startup_content)
        self.assertNotIn("git config --global user.name", startup_content)

    def test_offline_git_identity_resolution_cascades_name_and_overrides_email(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            # Replicate base and secondary configs, routing the simulated intrifund directory to the override profile
            base_cfg_content = self.gitconfig_path.read_text().replace(
                "/root/intrifund/", str(temp_dir / "intrifund") + "/"
            )
            override_cfg_content = self.gitconfig_mahesh_path.read_text()

            home_dir = temp_dir / "home"
            home_dir.mkdir()
            (home_dir / ".gitconfig").write_text(base_cfg_content)
            (home_dir / ".gitconfig-mahesh471978").write_text(override_cfg_content)

            default_repo = temp_dir / "default_org" / "repo1"
            default_repo.mkdir(parents=True)
            subprocess.run(["git", "init"], cwd=default_repo, check=True, capture_output=True)

            intrifund_repo = temp_dir / "intrifund" / "repo2"
            intrifund_repo.mkdir(parents=True)
            subprocess.run(["git", "init"], cwd=intrifund_repo, check=True, capture_output=True)

            env = os.environ.copy()
            env["HOME"] = str(home_dir)
            env["GIT_CONFIG_GLOBAL"] = str(home_dir / ".gitconfig")
            env["GIT_CONFIG_NOSYSTEM"] = "1"

            # Default repo retains global name and global email
            res_default_name = subprocess.run(
                ["git", "config", "user.name"],
                cwd=default_repo,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            res_default_email = subprocess.run(
                ["git", "config", "user.email"],
                cwd=default_repo,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            self.assertEqual(res_default_name, "Mahesh")
            self.assertEqual(res_default_email, "maheshghamand@gmail.com")

            # Intrifund repo cascades global name and overrides email from secondary profile
            res_intrifund_name = subprocess.run(
                ["git", "config", "user.name"],
                cwd=intrifund_repo,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            res_intrifund_email = subprocess.run(
                ["git", "config", "user.email"],
                cwd=intrifund_repo,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            self.assertEqual(res_intrifund_name, "Mahesh")
            self.assertEqual(res_intrifund_email, "mahesh471978@gmail.com")



class TestSandboxImageStaging(unittest.TestCase):
    def test_base_image_files_manifest_contents(self):
        from shared.image import (
            BASE_IMAGE_FILES,
            LOCAL_STARTUP_SCRIPT,
            REMOTE_STARTUP_SCRIPT,
            LOCAL_ALIASES_BASH,
            REMOTE_ALIASES_BASH,
            LOCAL_GITCONFIG,
            REMOTE_GITCONFIG,
            LOCAL_GITCONFIG_MAHESH471978,
            REMOTE_GITCONFIG_MAHESH471978,
            LOCAL_SETUP_SCRIPT,
            REMOTE_SETUP_SCRIPT,
            LOCAL_CLOUDFLARE_SECRET,
            REMOTE_CLOUDFLARE_SECRET,
        )

        expected = [
            (LOCAL_STARTUP_SCRIPT, REMOTE_STARTUP_SCRIPT),
            (LOCAL_ALIASES_BASH, REMOTE_ALIASES_BASH),
            (LOCAL_GITCONFIG, REMOTE_GITCONFIG),
            (LOCAL_GITCONFIG_MAHESH471978, REMOTE_GITCONFIG_MAHESH471978),
            (LOCAL_SETUP_SCRIPT, REMOTE_SETUP_SCRIPT),
            (LOCAL_CLOUDFLARE_SECRET, REMOTE_CLOUDFLARE_SECRET),
        ]
        self.assertEqual(BASE_IMAGE_FILES, expected)

    def test_add_local_files_if_present_stages_existing_and_skips_missing(self):
        from shared.image import add_local_files_if_present

        mock_image = MagicMock()
        mock_image.add_local_file.return_value = mock_image

        repo_root = Path(__file__).resolve().parents[2]
        existing_file = repo_root / "shared" / "aliases.bash"
        missing_file = repo_root / "shared" / "nonexistent-file-xyz.bash"

        files = [
            (existing_file, "/root/.bash_aliases"),
            (missing_file, "/root/missing"),
        ]

        result = add_local_files_if_present(mock_image, files)
        self.assertIs(result, mock_image)
        mock_image.add_local_file.assert_called_once_with(
            existing_file, "/root/.bash_aliases", copy=True
        )

    @patch("shared.image.add_local_files_if_present")
    def test_build_sandbox_image_uses_add_local_files_if_present_for_features(
        self, mock_add_files
    ):
        from shared.image import (
            build_sandbox_image,
            LOCAL_OPENCODE_CONFIG,
            REMOTE_OPENCODE_CONFIG,
            LOCAL_OPENCODE_SECRET,
            REMOTE_OPENCODE_SECRET,
            LOCAL_ANTIGRAVITY_SETTINGS,
            REMOTE_ANTIGRAVITY_SETTINGS,
            LOCAL_ANTIGRAVITY_KEYBINDINGS,
            REMOTE_ANTIGRAVITY_KEYBINDINGS,
            LOCAL_ANTIGRAVITY_ONBOARDING,
            REMOTE_ANTIGRAVITY_ONBOARDING,
            LOCAL_ANTIGRAVITY_SECRET,
            REMOTE_ANTIGRAVITY_SECRET,
            LOCAL_ANTIGRAVITY_SECRET_MGH,
            REMOTE_ANTIGRAVITY_SECRET_MGH,
            LOCAL_ANTIGRAVITY_SECRET_ANV,
            REMOTE_ANTIGRAVITY_SECRET_ANV,
            LOCAL_MODAL_SECRET,
            REMOTE_MODAL_SECRET,
        )

        mock_add_files.side_effect = lambda img, files: img

        # Test opencode
        mock_add_files.reset_mock()
        build_sandbox_image(opencode=True)
        mock_add_files.assert_called_with(
            ANY,
            [
                (LOCAL_OPENCODE_CONFIG, REMOTE_OPENCODE_CONFIG),
                (LOCAL_OPENCODE_SECRET, REMOTE_OPENCODE_SECRET),
            ],
        )

        # Test agy
        mock_add_files.reset_mock()
        build_sandbox_image(agy=True)
        mock_add_files.assert_called_with(
            ANY,
            [
                (LOCAL_ANTIGRAVITY_SETTINGS, REMOTE_ANTIGRAVITY_SETTINGS),
                (LOCAL_ANTIGRAVITY_KEYBINDINGS, REMOTE_ANTIGRAVITY_KEYBINDINGS),
                (LOCAL_ANTIGRAVITY_ONBOARDING, REMOTE_ANTIGRAVITY_ONBOARDING),
                (LOCAL_ANTIGRAVITY_SECRET, REMOTE_ANTIGRAVITY_SECRET),
                (LOCAL_ANTIGRAVITY_SECRET_MGH, REMOTE_ANTIGRAVITY_SECRET_MGH),
                (LOCAL_ANTIGRAVITY_SECRET_ANV, REMOTE_ANTIGRAVITY_SECRET_ANV),
            ],
        )

        # Test modal_tooling
        mock_add_files.reset_mock()
        build_sandbox_image(modal_tooling=True)
        mock_add_files.assert_called_with(
            ANY,
            [
                (LOCAL_MODAL_SECRET, REMOTE_MODAL_SECRET),
            ],
        )

        # Test t3 also stages opencode config and secrets
        mock_add_files.reset_mock()
        build_sandbox_image(t3=True)
        mock_add_files.assert_any_call(
            ANY,
            [
                (LOCAL_OPENCODE_CONFIG, REMOTE_OPENCODE_CONFIG),
                (LOCAL_OPENCODE_SECRET, REMOTE_OPENCODE_SECRET),
            ],
        )

    def test_build_sandbox_image_layers_react_native(self):
        from shared.image import build_sandbox_image

        with patch("shared.image.base_image") as mock_base:
            mock_apt_img = MagicMock()
            mock_env_img = MagicMock()
            mock_run_img = MagicMock()

            mock_base.apt_install.return_value = mock_apt_img
            mock_apt_img.env.return_value = mock_env_img
            mock_env_img.run_commands.return_value = mock_run_img

            build_sandbox_image(react_native=True)

            mock_base.apt_install.assert_called_once_with(
                "openjdk-17-jdk-headless", "watchman"
            )
            run_cmd_args = mock_env_img.run_commands.call_args[0]
            self.assertIn("npm install --global @expo/ngrok@^4.1.0", run_cmd_args)

    def test_startup_script_react_native_inotify_and_checks(self):
        from shared.image import LOCAL_STARTUP_SCRIPT

        content = LOCAL_STARTUP_SCRIPT.read_text()
        self.assertIn("sysctl -w fs.inotify.max_user_watches=524288", content)
        self.assertIn("/etc/sysctl.d/99-react-native.conf", content)
        self.assertIn("watchman --version", content)
        self.assertIn("npm list -g @expo/ngrok", content)


if __name__ == "__main__":
    unittest.main()

