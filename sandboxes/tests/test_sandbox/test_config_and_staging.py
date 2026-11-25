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

    def test_startup_script_has_no_synthetic_or_hardcoded_identities(self):
        startup_content = self.startup_sh_path.read_text()
        self.assertNotIn("Modal Sandbox User", startup_content)
        self.assertNotIn("sandbox@modal.local", startup_content)
        self.assertNotIn("maheshghamand@gmail.com", startup_content)

    def test_startup_script_configures_git_identities_dynamically(self):
        startup_content = self.startup_sh_path.read_text()
        self.assertIn('git config --global user.name "$GLOBAL_GIT_NAME"', startup_content)
        self.assertIn('git config --global user.email "$GLOBAL_GIT_EMAIL"', startup_content)
        self.assertIn('git -C "$TARGET_DIR" config --local user.name "$TARGET_GIT_AUTHOR_NAME"', startup_content)
        self.assertIn('git -C "$TARGET_DIR" config --local user.email "$TARGET_GIT_AUTHOR_EMAIL"', startup_content)

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
            LOCAL_CREATE_DB,
            REMOTE_CREATE_DB,
            LOCAL_CREATE_S3,
            REMOTE_CREATE_S3,
            LOCAL_CREATE_APP,
            REMOTE_CREATE_APP,
            LOCAL_T3_USAGE_SYNC,
            REMOTE_T3_USAGE_SYNC,
            LOCAL_POST_CHECKOUT_HOOK,
            REMOTE_POST_CHECKOUT_HOOK,
            LOCAL_DESKTOP_SERVICE,
            REMOTE_DESKTOP_SERVICE,
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
            (LOCAL_CREATE_DB, REMOTE_CREATE_DB),
            (LOCAL_CREATE_S3, REMOTE_CREATE_S3),
            (LOCAL_CREATE_APP, REMOTE_CREATE_APP),
            (LOCAL_T3_USAGE_SYNC, REMOTE_T3_USAGE_SYNC),
            (LOCAL_POST_CHECKOUT_HOOK, REMOTE_POST_CHECKOUT_HOOK),
            (LOCAL_DESKTOP_SERVICE, REMOTE_DESKTOP_SERVICE),
        ]
        self.assertEqual(BASE_IMAGE_FILES, expected)
        self.assertEqual(REMOTE_SETUP_SCRIPT, "/root/.scripts/setup.sh")
        self.assertEqual(REMOTE_T3_USAGE_SYNC, "/usr/local/bin/t3-usage-sync")
        self.assertEqual(REMOTE_POST_CHECKOUT_HOOK, "/root/.git-hooks/post-checkout")

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
            LOCAL_CREATE_DB,
            REMOTE_CREATE_DB,
            LOCAL_CREATE_S3,
            REMOTE_CREATE_S3,
            LOCAL_CREATE_APP,
            REMOTE_CREATE_APP,
            LOCAL_T3_USAGE_SYNC,
            REMOTE_T3_USAGE_SYNC,
            LOCAL_POST_CHECKOUT_HOOK,
            REMOTE_POST_CHECKOUT_HOOK,
        )

        self.assertEqual(REMOTE_AGYQ, "/usr/local/bin/agyq")
        self.assertEqual(REMOTE_GHLS, "/usr/local/bin/ghls")
        self.assertEqual(REMOTE_GHPR, "/usr/local/bin/ghpr")
        self.assertEqual(REMOTE_GHCLONE, "/usr/local/bin/ghclone")
        self.assertEqual(REMOTE_AGYPROFILE, "/usr/local/bin/agyprofile")
        self.assertEqual(REMOTE_PUSH_REPO_ENV, "/usr/local/bin/push-repo-env")
        self.assertEqual(REMOTE_PULL_REPO_ENV, "/usr/local/bin/pull-repo-env")
        self.assertEqual(REMOTE_T3_USAGE_SYNC, "/usr/local/bin/t3-usage-sync")
        self.assertEqual(REMOTE_POST_CHECKOUT_HOOK, "/root/.git-hooks/post-checkout")

        self.assertTrue(LOCAL_AGYQ.exists(), "scripts/agyq must exist")
        self.assertTrue(LOCAL_GHLS.exists(), "scripts/ghls must exist")
        self.assertTrue(LOCAL_GHPR.exists(), "scripts/ghpr must exist")
        self.assertTrue(LOCAL_GHCLONE.exists(), "scripts/ghclone must exist")
        self.assertTrue(LOCAL_AGYPROFILE.exists(), "scripts/agyprofile must exist")
        self.assertTrue(LOCAL_PUSH_REPO_ENV.exists(), "scripts/push_repo_env.py must exist")
        self.assertTrue(LOCAL_PULL_REPO_ENV.exists(), "scripts/pull_repo_env.py must exist")
        self.assertTrue(LOCAL_CREATE_DB.exists(), "scripts/create_db.py must exist")
        self.assertTrue(LOCAL_CREATE_S3.exists(), "scripts/create_s3.py must exist")
        self.assertTrue(LOCAL_CREATE_APP.exists(), "scripts/create_app.py must exist")
        self.assertEqual(REMOTE_CREATE_APP, "/usr/local/bin/create-app")
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
            LOCAL_T3_KEYBINDINGS,
            REMOTE_T3_KEYBINDINGS,
            LOCAL_T3_WRAPPER,
            REMOTE_T3_WRAPPER,
        )

        mock_image = MagicMock()
        mock_image.run_commands.return_value = mock_image
        mock_image.env.return_value = mock_image
        mock_add_files.side_effect = lambda img, *args, **kwargs: img

        with patch("shared.image.base_image", mock_image):
            # Test T3
            build_sandbox_image(t3=True)
            mock_add_files.assert_any_call(
                mock_image,
                [
                    (LOCAL_T3_KEYBINDINGS, REMOTE_T3_KEYBINDINGS),
                    (LOCAL_T3_WRAPPER, REMOTE_T3_WRAPPER),
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

            # Test t3 launch
            build_sandbox_image(t3=True)
            mock_base.run_commands.assert_called_with(
                "curl -fsSL https://opencode.ai/v2/install | bash"
            )


class TestConfigModule(unittest.TestCase):
    def test_parse_env_file_text(self):
        from sandbox.config import parse_env_file

        raw = '''
        # Comment line
        FOO=bar
        export BAZ="qux"
        SPACED='hello world'
        EMPTY=
        '''
        env = parse_env_file(raw)
        self.assertEqual(env["FOO"], "bar")
        self.assertEqual(env["BAZ"], "qux")
        self.assertEqual(env["SPACED"], "hello world")
        self.assertEqual(env["EMPTY"], "")

    def test_resolve_factory_credentials(self):
        from sandbox.config import resolve_factory_credentials

        test_env = {
            "GH_TOKEN": "ghp_test123",
            "GH_ORG_NAME": "org_test",
            "AGE_PRIVATE_KEY": "AGE-SECRET-KEY-1",
            "MODAL_TOKENS": '[{"name": "p1"}]',
        }
        creds = resolve_factory_credentials(env=test_env, mutate_environ=False)
        self.assertEqual(creds.gh_token, "ghp_test123")
        self.assertEqual(creds.gh_org_name, "org_test")
        self.assertEqual(creds.age_private_key, "AGE-SECRET-KEY-1")
        self.assertEqual(creds.modal_tokens, '[{"name": "p1"}]')

    def test_resolve_timezone_defaults_and_overrides(self):
        from sandbox.config import resolve_timezone

        # 1. Default fallback is Asia/Kolkata
        self.assertEqual(resolve_timezone(env={}), "Asia/Kolkata")

        # 2. DEFAULT_TIMEZONE takes precedence
        self.assertEqual(resolve_timezone(env={"DEFAULT_TIMEZONE": "America/New_York"}), "America/New_York")

        # 3. TZ fallback
        self.assertEqual(resolve_timezone(env={"TZ": "Europe/London"}), "Europe/London")

        # 4. DEFAULT_TIMEZONE wins over TZ
        self.assertEqual(
            resolve_timezone(env={"DEFAULT_TIMEZONE": "Asia/Tokyo", "TZ": "UTC"}),
            "Asia/Tokyo",
        )

    def test_resolve_factory_credentials_includes_timezone(self):
        from sandbox.config import resolve_factory_credentials

        creds = resolve_factory_credentials(env={"DEFAULT_TIMEZONE": "Asia/Kolkata"}, mutate_environ=False)
        self.assertEqual(creds.default_timezone, "Asia/Kolkata")

    def test_resolve_factory_configuration_full(self):
        from sandbox.config import resolve_factory_configuration

        test_env = {
            "GH_TOKEN": "ghp_full123",
            "GH_ORG_NAME": "org_full",
            "AGE_PRIVATE_KEY": "AGE-SECRET-KEY-FULL",
            "MODAL_TOKENS": '[{"name": "p_full"}]',
            "CLOUDFLARE_TUNNEL_TOKEN": "cf-tok-123",
            "WEB_UI_USERNAME": "superadmin",
            "WEB_UI_PASSWORD": "supersecretpassword",
            "CODEX_STATUS_SECRET": "status_sec_abc",
        }
        cfg = resolve_factory_configuration(env=test_env, mutate_environ=False)
        self.assertEqual(cfg.gh_token, "ghp_full123")
        self.assertEqual(cfg.gh_org_name, "org_full")
        self.assertEqual(cfg.age_private_key, "AGE-SECRET-KEY-FULL")
        self.assertEqual(cfg.modal_tokens, '[{"name": "p_full"}]')
        self.assertEqual(cfg.cloudflare_tunnel_token, "cf-tok-123")
        self.assertEqual(cfg.web_ui_username, "superadmin")
        self.assertEqual(cfg.web_ui_password, "supersecretpassword")
        self.assertEqual(cfg.codex_status_secret, "status_sec_abc")

    def test_compile_control_plane_secrets(self):
        from sandbox.config import compile_control_plane_secrets
        import modal

        secrets = compile_control_plane_secrets(extra_secrets={"TEST_CP_SECRET": "1"})
        self.assertIsInstance(secrets, list)
        self.assertEqual(len(secrets), 1)
        self.assertIsInstance(secrets[0], modal.Secret)

