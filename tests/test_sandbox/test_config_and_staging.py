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
        )

        self.assertEqual(LOCAL_GITCONFIG, self.gitconfig_path)
        self.assertEqual(REMOTE_GITCONFIG, "/root/.gitconfig")

        self.assertIn((LOCAL_GITCONFIG, REMOTE_GITCONFIG), BASE_IMAGE_FILES)
        self.assertTrue(LOCAL_GITCONFIG.exists())
        self.assertFalse(self.gitconfig_mahesh_path.exists())

    def test_base_gitconfig_declares_github_credential_helpers(self):
        content = self.gitconfig_path.read_text()
        self.assertIn('[credential "https://github.com"]', content)
        self.assertIn('helper = !/usr/bin/gh auth git-credential', content)
        self.assertIn('[credential "https://gist.github.com"]', content)
        self.assertIn("defaultBranch = main", content)

    def test_base_gitconfig_has_no_hardcoded_identities_or_conditional_profiles(self):
        content = self.gitconfig_path.read_text()
        self.assertNotIn("name = Mahesh", content)
        self.assertNotIn("maheshghamand@gmail.com", content)
        self.assertNotIn("includeIf", content)
        self.assertNotIn("gitconfig-mahesh471978", content)

    def test_startup_script_uses_generic_author_defaults(self):
        startup_content = self.startup_sh_path.read_text()
        self.assertIn('GIT_AUTHOR_NAME="${GIT_AUTHOR_NAME:-Modal Sandbox User}"', startup_content)
        self.assertIn('GIT_AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL:-sandbox@modal.local}"', startup_content)
        self.assertNotIn("maheshghamand@gmail.com", startup_content)

    def test_startup_script_does_not_mutate_git_config_inline(self):
        startup_content = self.startup_sh_path.read_text()
        self.assertNotIn("git config --global user.email", startup_content)
        self.assertNotIn("git config --global user.name", startup_content)

    def test_host_git_identity_resolution(self):
        from sandbox.launcher import resolve_host_git_identity
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"GIT_AUTHOR_NAME": "Alice", "GIT_AUTHOR_EMAIL": "alice@example.com"}):
            ident = resolve_host_git_identity()
            self.assertEqual(ident.get("GIT_AUTHOR_NAME"), "Alice")
            self.assertEqual(ident.get("GIT_COMMITTER_NAME"), "Alice")
            self.assertEqual(ident.get("GIT_AUTHOR_EMAIL"), "alice@example.com")
            self.assertEqual(ident.get("GIT_COMMITTER_EMAIL"), "alice@example.com")



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
            LOCAL_SETUP_SCRIPT,
            REMOTE_SETUP_SCRIPT,
            LOCAL_AGYQ,
            REMOTE_AGYQ,
            LOCAL_GHLS,
            REMOTE_GHLS,
            LOCAL_GHPR,
            REMOTE_GHPR,
            LOCAL_GHCLONE,
            REMOTE_GHCLONE,
            LOCAL_AGYPROFILE,
            REMOTE_AGYPROFILE,
            LOCAL_PUSH_REPO_ENV,
            REMOTE_PUSH_REPO_ENV,
            LOCAL_PULL_REPO_ENV,
            REMOTE_PULL_REPO_ENV,
            LOCAL_T3_USAGE_SYNC,
            REMOTE_T3_USAGE_SYNC,
        )

        expected = [
            (LOCAL_STARTUP_SCRIPT, REMOTE_STARTUP_SCRIPT),
            (LOCAL_ALIASES_BASH, REMOTE_ALIASES_BASH),
            (LOCAL_GITCONFIG, REMOTE_GITCONFIG),
            (LOCAL_SETUP_SCRIPT, REMOTE_SETUP_SCRIPT),
            (LOCAL_AGYQ, REMOTE_AGYQ),
            (LOCAL_GHLS, REMOTE_GHLS),
            (LOCAL_GHPR, REMOTE_GHPR),
            (LOCAL_GHCLONE, REMOTE_GHCLONE),
            (LOCAL_AGYPROFILE, REMOTE_AGYPROFILE),
            (LOCAL_PUSH_REPO_ENV, REMOTE_PUSH_REPO_ENV),
            (LOCAL_PULL_REPO_ENV, REMOTE_PULL_REPO_ENV),
            (LOCAL_T3_USAGE_SYNC, REMOTE_T3_USAGE_SYNC),
        ]
        self.assertEqual(BASE_IMAGE_FILES, expected)
        self.assertEqual(REMOTE_SETUP_SCRIPT, "/root/.scripts/setup.sh")
        self.assertEqual(REMOTE_T3_USAGE_SYNC, "/usr/local/bin/t3-usage-sync")

    def test_developer_commands_staged_and_symlinked_system_wide(self):
        repo_root = Path(__file__).resolve().parents[2]
        from shared.image import (
            LOCAL_AGYQ,
            REMOTE_AGYQ,
            LOCAL_GHLS,
            REMOTE_GHLS,
            LOCAL_GHPR,
            REMOTE_GHPR,
            LOCAL_GHCLONE,
            REMOTE_GHCLONE,
            LOCAL_AGYPROFILE,
            REMOTE_AGYPROFILE,
            LOCAL_PUSH_REPO_ENV,
            REMOTE_PUSH_REPO_ENV,
            LOCAL_PULL_REPO_ENV,
            REMOTE_PULL_REPO_ENV,
            LOCAL_T3_USAGE_SYNC,
            REMOTE_T3_USAGE_SYNC,
        )

        self.assertEqual(REMOTE_AGYQ, "/usr/local/bin/agyq")
        self.assertEqual(REMOTE_GHLS, "/usr/local/bin/ghls")
        self.assertEqual(REMOTE_GHPR, "/usr/local/bin/ghpr")
        self.assertEqual(REMOTE_GHCLONE, "/usr/local/bin/ghclone")
        self.assertEqual(REMOTE_AGYPROFILE, "/usr/local/bin/agyprofile")
        self.assertEqual(REMOTE_PUSH_REPO_ENV, "/usr/local/bin/push-repo-env")
        self.assertEqual(REMOTE_PULL_REPO_ENV, "/usr/local/bin/pull-repo-env")
        self.assertEqual(REMOTE_T3_USAGE_SYNC, "/usr/local/bin/t3-usage-sync")

        self.assertTrue(LOCAL_AGYQ.exists(), "scripts/agyq must exist")
        self.assertTrue(LOCAL_GHLS.exists(), "scripts/ghls must exist")
        self.assertTrue(LOCAL_GHPR.exists(), "scripts/ghpr must exist")
        self.assertTrue(LOCAL_GHCLONE.exists(), "scripts/ghclone must exist")
        self.assertTrue(LOCAL_AGYPROFILE.exists(), "scripts/agyprofile must exist")
        self.assertTrue(LOCAL_PUSH_REPO_ENV.exists(), "scripts/push_repo_env.py must exist")
        self.assertTrue(LOCAL_PULL_REPO_ENV.exists(), "scripts/pull_repo_env.py must exist")
        self.assertTrue(LOCAL_T3_USAGE_SYNC.exists(), "shared/t3_usage_sync.py must exist")

        startup_content = (repo_root / "shared" / "startup.sh").read_text()
        self.assertIn("chmod +x /usr/local/bin/agyq /usr/local/bin/ghls /usr/local/bin/ghpr /usr/local/bin/ghclone /usr/local/bin/agyprofile", startup_content)
        self.assertIn("ln -sf /usr/local/bin/agyprofile /usr/local/bin/switch-agy-profile", startup_content)
        self.assertIn("ln -sf /usr/local/bin/agyprofile /usr/local/bin/switch-agy-profile.sh", startup_content)
        self.assertIn("export PATH=\"/usr/local/bin:$PATH\"", startup_content)

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
            LOCAL_ANTIGRAVITY_SETTINGS,
            REMOTE_ANTIGRAVITY_SETTINGS,
            LOCAL_ANTIGRAVITY_KEYBINDINGS,
            REMOTE_ANTIGRAVITY_KEYBINDINGS,
            LOCAL_ANTIGRAVITY_ONBOARDING,
            REMOTE_ANTIGRAVITY_ONBOARDING,
            LOCAL_T3_KEYBINDINGS,
            REMOTE_T3_KEYBINDINGS,
            LOCAL_T3_WRAPPER,
            REMOTE_T3_WRAPPER,
            LOCAL_PI_SETTINGS,
            REMOTE_PI_SETTINGS,
            LOCAL_PI_MODELS,
            REMOTE_PI_MODELS,
        )

        mock_image = MagicMock()
        mock_image.run_commands.return_value = mock_image
        mock_image.env.return_value = mock_image
        mock_add_files.side_effect = lambda img, *args, **kwargs: img

        with patch("shared.image.base_image", mock_image):
            # Test OpenCode
            build_sandbox_image(opencode=True)
            mock_add_files.assert_any_call(
                mock_image,
                [
                    (LOCAL_OPENCODE_CONFIG, REMOTE_OPENCODE_CONFIG),
                ],
            )

            # Test Antigravity
            build_sandbox_image(agy=True)
            mock_add_files.assert_any_call(
                mock_image,
                [
                    (LOCAL_ANTIGRAVITY_SETTINGS, REMOTE_ANTIGRAVITY_SETTINGS),
                    (LOCAL_ANTIGRAVITY_KEYBINDINGS, REMOTE_ANTIGRAVITY_KEYBINDINGS),
                    (LOCAL_ANTIGRAVITY_ONBOARDING, REMOTE_ANTIGRAVITY_ONBOARDING),
                ],
            )

            # Test T3
            build_sandbox_image(t3=True)
            mock_add_files.assert_any_call(
                mock_image,
                [
                    (LOCAL_T3_KEYBINDINGS, REMOTE_T3_KEYBINDINGS),
                    (LOCAL_T3_WRAPPER, REMOTE_T3_WRAPPER),
                ],
            )

            # Test Pi
            build_sandbox_image(pi=True)
            mock_add_files.assert_any_call(
                mock_image,
                [
                    (LOCAL_PI_SETTINGS, REMOTE_PI_SETTINGS),
                    (LOCAL_PI_MODELS, REMOTE_PI_MODELS),
                ],
            )

    @patch("shared.image.base_image")
    def test_build_sandbox_image_layers_correct_tools(self, mock_base):
        from shared.image import build_sandbox_image

        mock_image = MagicMock()
        mock_base.run_commands.return_value = mock_image
        mock_image.run_commands.return_value = mock_image
        mock_image.env.return_value = mock_image

        with patch("shared.image.add_local_files_if_present", side_effect=lambda img, *args, **kwargs: img):
            # Test vanilla launch
            img = build_sandbox_image()
            self.assertEqual(img, mock_base)

            # Test OpenCode
            build_sandbox_image(opencode=True)
            mock_base.run_commands.assert_called_with(
                "curl -fsSL https://opencode.ai/v2/install | bash"
            )

            # Test Antigravity
            build_sandbox_image(agy=True)
            mock_base.run_commands.assert_called_with(
                "curl -fsSL https://antigravity.google/cli/install.sh | bash",
                "mkdir -p /root/.gemini/antigravity-cli /root/.gemini/antigravity-cli/cache",
            )

            # Test Herdr
            build_sandbox_image(herdr=True)
            mock_base.run_commands.assert_called_with(
                "curl -fsSL https://herdr.dev/install.sh | env HERDR_INSTALL_DIR=/usr/local/bin sh"
            )

            # Test Pi
            build_sandbox_image(pi=True)
            mock_base.run_commands.assert_called_with(
                "npm install -g --ignore-scripts @earendil-works/pi-coding-agent"
            )
