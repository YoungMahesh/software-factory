"""Unit tests for the deep SandboxLauncher module and RunningSandbox domain model."""

import base64
import json
import os
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from sandbox.core import LaunchRequest, LaunchResponse
from sandbox.launcher import (
    RunningSandbox,
    SandboxLauncher,
    launch_sandbox,
    resolve_host_software_factory_provenance,
)


class TestRunningSandbox(unittest.TestCase):
    def setUp(self):
        self.mock_sandbox = MagicMock()
        self.mock_sandbox.object_id = "sb-12345678"
        self.mock_sandbox.poll.return_value = None
        self.response = LaunchResponse(
            sandbox_id="sb-12345678",
            app_name="test-app",
            sandbox_name="test-app-abcdef",
            ssh_info=("ssh.host", 2222),
            ssh_command="ssh -p 2222 root@ssh.host",
            ssh_config="Host test-app-abcdef\n  HostName ssh.host\n  Port 2222\n  User root\n  IdentityFile ~/.ssh/modal-sandbox\n  StrictHostKeyChecking no\n  UserKnownHostsFile /dev/null\n",
            opencode_url="https://opencode.modal.run",
            metro_url="https://metro.modal.run",
            t3_url="https://t3.modal.run",
            t3_pair_url="https://t3.modal.run/pair#abc",
        )
        self.running = RunningSandbox(sandbox=self.mock_sandbox, response=self.response)

    def test_properties(self):
        self.assertEqual(self.running.sandbox_id, "sb-12345678")
        self.assertEqual(self.running.app_name, "test-app")
        self.assertEqual(self.running.sandbox_name, "test-app-abcdef")
        self.assertEqual(self.running.ssh_info, ("ssh.host", 2222))
        self.assertEqual(self.running.ssh_command, "ssh -p 2222 root@ssh.host")
        self.assertIn("Host test-app-abcdef", self.running.ssh_config)
        self.assertEqual(self.running.opencode_url, "https://opencode.modal.run")
        self.assertEqual(self.running.metro_url, "https://metro.modal.run")
        self.assertEqual(self.running.t3_url, "https://t3.modal.run")
        self.assertEqual(self.running.t3_pair_url, "https://t3.modal.run/pair#abc")

    def test_to_response(self):
        resp = self.running.to_response()
        self.assertIs(resp, self.response)

    def test_unpacking_compatibility(self):
        sb, resp = self.running
        self.assertIs(sb, self.mock_sandbox)
        self.assertIs(resp, self.response)

    def test_delegated_methods(self):
        self.assertIsNone(self.running.poll())
        self.mock_sandbox.poll.assert_called_once()

        self.running.terminate()
        self.mock_sandbox.terminate.assert_called_once()

        self.mock_sandbox.exec.return_value = "exec_result"
        res = self.running.exec("ls", "-la")
        self.assertEqual(res, "exec_result")
        self.mock_sandbox.exec.assert_called_once_with("ls", "-la")

        self.mock_sandbox.tunnels.return_value = {22: MagicMock()}
        tunnels = self.running.tunnels()
        self.assertIn(22, tunnels)


class TestSandboxLauncher(unittest.TestCase):
    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    def test_launcher_dependency_injection(self, mock_lookup, mock_create):
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-launcher-1"
        mock_sandbox.poll.return_value = None
        mock_sandbox.tunnels.return_value = {22: MagicMock(tcp_socket=("10.0.0.1", 2200))}
        mock_create.return_value = mock_sandbox

        custom_pubkey = MagicMock(return_value="ssh-rsa custom_key")
        custom_builder = MagicMock(return_value=MagicMock())
        custom_append = MagicMock(return_value=True)

        launcher = SandboxLauncher(
            build_image_fn=custom_builder,
            load_pubkey_fn=custom_pubkey,
            append_ssh_fn=custom_append,
            repo_root=Path("/fake/root"),
        )

        req = LaunchRequest(name="custom-launch")
        running = launcher.launch(req, register_ssh_config=True)

        custom_pubkey.assert_called_once()
        custom_builder.assert_called_once()
        custom_append.assert_called_once_with(
            instance_name=running.sandbox_name,
            ssh_host="10.0.0.1",
            ssh_port=2200,
        )
        self.assertEqual(running.sandbox_id, "sb-launcher-1")
        self.assertIsNotNone(running.ssh_config)
        self.assertIn(f"Host {running.sandbox_name}", running.ssh_config)
        self.assertEqual(running.response.ssh_config, running.ssh_config)

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    def test_launcher_skips_ssh_config_when_disabled(self, mock_lookup, mock_create):
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-launcher-2"
        mock_sandbox.poll.return_value = None
        mock_sandbox.tunnels.return_value = {22: MagicMock(tcp_socket=("10.0.0.1", 2200))}
        mock_create.return_value = mock_sandbox

        custom_append = MagicMock()
        launcher = SandboxLauncher(
            build_image_fn=MagicMock(),
            load_pubkey_fn=MagicMock(return_value="key"),
            append_ssh_fn=custom_append,
        )

        req = LaunchRequest(name="no-ssh-reg")
        launcher.launch(req, register_ssh_config=False)

        custom_append.assert_not_called()

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    def test_container_exit_raises_runtime_error(self, mock_lookup, mock_create):
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-fail"
        mock_sandbox.poll.return_value = 1
        mock_sandbox.stderr.read.return_value = "Fatal error on startup"
        mock_create.return_value = mock_sandbox

        launcher = SandboxLauncher(
            build_image_fn=MagicMock(),
            load_pubkey_fn=MagicMock(return_value="key"),
        )
        req = LaunchRequest(name="failing-box")

        with self.assertRaises(RuntimeError) as ctx:
            launcher.launch(req)
        self.assertIn("Container terminated with exit code 1", str(ctx.exception))

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    def test_launch_sandbox_convenience_function(self, mock_lookup, mock_create):
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-func-1"
        mock_sandbox.poll.return_value = None
        mock_sandbox.tunnels.return_value = {}
        mock_create.return_value = mock_sandbox

        req = LaunchRequest(name="func-app")
        sb, resp = launch_sandbox(
            req,
            build_image_fn=MagicMock(),
            load_pubkey_fn=MagicMock(return_value="key"),
        )

        self.assertEqual(sb.object_id, "sb-func-1")
        self.assertEqual(resp.sandbox_id, "sb-func-1")

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    def test_launcher_injects_host_git_identity_into_container_env(self, mock_lookup, mock_create):
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-git-id"
        mock_sandbox.poll.return_value = None
        mock_sandbox.tunnels.return_value = {}
        mock_create.return_value = mock_sandbox

        mock_git_id = MagicMock(return_value={
            "GIT_AUTHOR_NAME": "Test Author",
            "GIT_AUTHOR_EMAIL": "author@test.com",
            "GIT_COMMITTER_NAME": "Test Author",
            "GIT_COMMITTER_EMAIL": "author@test.com",
        })

        launcher = SandboxLauncher(
            build_image_fn=MagicMock(),
            load_pubkey_fn=MagicMock(return_value="key"),
            resolve_git_identity_fn=mock_git_id,
        )

        req = LaunchRequest(name="git-env-app")
        launcher.launch(req)

        mock_git_id.assert_called_once()
        call_env = mock_create.call_args.kwargs["env"]
        self.assertEqual(call_env["GIT_AUTHOR_NAME"], "Test Author")
        self.assertEqual(call_env["GIT_AUTHOR_EMAIL"], "author@test.com")
        self.assertEqual(call_env["GIT_COMMITTER_NAME"], "Test Author")
        self.assertEqual(call_env["GIT_COMMITTER_EMAIL"], "author@test.com")

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    def test_launcher_injects_software_factory_provenance_into_container_env_and_tags(self, mock_lookup, mock_create):
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-prov-test"
        mock_sandbox.poll.return_value = None
        mock_sandbox.tunnels.return_value = {}
        mock_create.return_value = mock_sandbox

        mock_prov = MagicMock(return_value={
            "SOFTWARE_FACTORY_COMMIT": "e8a1f89c01234567890abcdef1234567890abcde",
            "SOFTWARE_FACTORY_COMMIT_SHORT": "e8a1f89",
            "SOFTWARE_FACTORY_REF": "main",
            "SOFTWARE_FACTORY_DIRTY": "1",
        })

        launcher = SandboxLauncher(
            build_image_fn=MagicMock(),
            load_pubkey_fn=MagicMock(return_value="key"),
            resolve_provenance_fn=mock_prov,
        )

        req = LaunchRequest(name="prov-app")
        launcher.launch(req)

        mock_prov.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        call_env = call_kwargs["env"]
        call_tags = call_kwargs["tags"]

        self.assertEqual(call_env["SOFTWARE_FACTORY_COMMIT"], "e8a1f89c01234567890abcdef1234567890abcde")
        self.assertEqual(call_env["SOFTWARE_FACTORY_COMMIT_SHORT"], "e8a1f89")
        self.assertEqual(call_env["SOFTWARE_FACTORY_REF"], "main")
        self.assertEqual(call_env["SOFTWARE_FACTORY_DIRTY"], "1")

        self.assertEqual(call_tags["software_factory_commit"], "e8a1f89")
        self.assertEqual(call_tags["software_factory_dirty"], "1")

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    def test_launcher_unqualified_repo_without_gh_org_name_raises_value_error(self, mock_lookup, mock_create):
        launcher = SandboxLauncher(
            build_image_fn=MagicMock(),
            load_pubkey_fn=MagicMock(return_value="key"),
            repo_root=Path("/nonexistent"),
        )
        req = LaunchRequest(repo="bare-repo")

        with patch.dict(os.environ, {"GH_TOKEN": "dummy", "GH_ORG_NAME": ""}, clear=False):
            with patch("sandbox.launcher.DEFAULT_ORG", ""):
                with self.assertRaises(ValueError) as ctx:
                    launcher.launch(req)
                self.assertIn("has no owner prefix and GH_ORG_NAME is not set", str(ctx.exception))

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    def test_launcher_unqualified_repo_with_gh_org_name_resolves_target_repo(self, mock_lookup, mock_create):
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-org-res"
        mock_sandbox.poll.return_value = None
        mock_sandbox.tunnels.return_value = {}
        mock_create.return_value = mock_sandbox

        launcher = SandboxLauncher(
            build_image_fn=MagicMock(),
            load_pubkey_fn=MagicMock(return_value="key"),
            repo_root=Path("/nonexistent"),
        )
        req = LaunchRequest(repo="bare-repo")

        with patch.dict(os.environ, {"GH_TOKEN": "dummy", "GH_ORG_NAME": "custom-org"}, clear=False):
            launcher.launch(req)
            call_env = mock_create.call_args.kwargs["env"]
            self.assertEqual(call_env["GH_REPO"], "custom-org/bare-repo")
            self.assertEqual(call_env["GH_ORG"], "custom-org")

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    def test_launcher_modal_requires_modal_tokens(self, mock_lookup, mock_create):
        launcher = SandboxLauncher(
            build_image_fn=MagicMock(),
            load_pubkey_fn=MagicMock(return_value="key"),
            repo_root=Path("/nonexistent"),
        )
        req = LaunchRequest(name="modal-app", modal=True)

        with patch.dict(os.environ, {"MODAL_TOKENS": ""}, clear=False):
            with self.assertRaises(ValueError) as ctx:
                launcher.launch(req)
            self.assertIn("Modal development tooling (--modal) requires valid MODAL_TOKENS", str(ctx.exception))

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    def test_launcher_modal_with_valid_modal_tokens_injects_and_runs(self, mock_lookup, mock_create):
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-modal-ok"
        mock_sandbox.poll.return_value = None
        mock_sandbox.tunnels.return_value = {}
        mock_create.return_value = mock_sandbox

        launcher = SandboxLauncher(
            build_image_fn=MagicMock(),
            load_pubkey_fn=MagicMock(return_value="key"),
            repo_root=Path("/nonexistent"),
        )
        req = LaunchRequest(name="modal-app", modal=True, profile="work")
        tokens = json.dumps([{"name": "work", "token_id": "ak-123", "token_secret": "as-456"}])

        with patch.dict(os.environ, {"MODAL_TOKENS": tokens}, clear=False):
            launcher.launch(req)
            call_env = mock_create.call_args.kwargs["env"]
            self.assertEqual(call_env["ENABLE_MODAL"], "1")
            self.assertEqual(call_env["MODAL_PROFILE"], "work")

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    def test_launcher_injects_env_store_secrets(self, mock_lookup, mock_create):
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-vault-test"
        mock_sandbox.poll.return_value = None
        mock_sandbox.tunnels.return_value = {}
        mock_create.return_value = mock_sandbox

        mock_vault_fetch = MagicMock(return_value={"API_KEY": "secret_abc", "DATABASE_URL": "postgres://localhost"})

        launcher = SandboxLauncher(
            build_image_fn=MagicMock(),
            load_pubkey_fn=MagicMock(return_value="key"),
            repo_root=Path("/nonexistent"),
            fetch_vault_env_fn=mock_vault_fetch,
        )
        req = LaunchRequest(repo="custom-org/my-target-app")

        with patch.dict(os.environ, {"GH_TOKEN": "dummy", "GH_ORG_NAME": "custom-org"}, clear=False):
            launcher.launch(req)

        mock_vault_fetch.assert_called_once_with("my-target-app", org_name="custom-org")
        call_env = mock_create.call_args.kwargs["env"]
        self.assertIn("VAULT_DOTENV_B64", call_env)
        decoded = base64.b64decode(call_env["VAULT_DOTENV_B64"]).decode("utf-8")
        self.assertIn("API_KEY=secret_abc", decoded)
        self.assertIn("DATABASE_URL=postgres://localhost", decoded)

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    def test_launcher_injects_env_store_secrets_raw_preserving_quotes(self, mock_lookup, mock_create):
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-vault-test-raw"
        mock_sandbox.poll.return_value = None
        mock_sandbox.tunnels.return_value = {}
        mock_create.return_value = mock_sandbox

        raw_env = (
            "# My custom config\n"
            "SSH_AUTHORIZED_KEY='ssh-rsa AAAAB3... user@example'\n"
            "PLAIN_VAR=plain\n"
        )
        mock_raw_fetch = MagicMock(return_value=raw_env)

        launcher = SandboxLauncher(
            build_image_fn=MagicMock(),
            load_pubkey_fn=MagicMock(return_value="key"),
            repo_root=Path("/nonexistent"),
            fetch_vault_env_raw_fn=mock_raw_fetch,
        )
        req = LaunchRequest(repo="custom-org/my-target-app")

        with patch.dict(os.environ, {"GH_TOKEN": "dummy", "GH_ORG_NAME": "custom-org"}, clear=False):
            launcher.launch(req)

        mock_raw_fetch.assert_called_once_with("my-target-app", org_name="custom-org")
        call_env = mock_create.call_args.kwargs["env"]
        self.assertIn("VAULT_DOTENV_B64", call_env)
        decoded = base64.b64decode(call_env["VAULT_DOTENV_B64"]).decode("utf-8")
        self.assertEqual(decoded, raw_env)
        self.assertIn("SSH_AUTHORIZED_KEY='ssh-rsa AAAAB3... user@example'", decoded)


    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    def test_launcher_injects_repo_specific_git_identity_into_container_env(self, mock_lookup, mock_create):
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-vault-git"
        mock_sandbox.poll.return_value = None
        mock_sandbox.tunnels.return_value = {}
        mock_create.return_value = mock_sandbox

        mock_git_fetch = MagicMock(return_value={"GIT_AUTHOR_NAME": "Repo Dev", "GIT_AUTHOR_EMAIL": "repo-dev@example.com"})

        launcher = SandboxLauncher(
            build_image_fn=MagicMock(),
            load_pubkey_fn=MagicMock(return_value="key"),
            repo_root=Path("/nonexistent"),
            fetch_vault_env_fn=MagicMock(return_value=None),
            fetch_vault_env_raw_fn=MagicMock(return_value=None),
            fetch_vault_git_identity_fn=mock_git_fetch,
        )
        req = LaunchRequest(repo="custom-org/my-target-app")

        with patch.dict(os.environ, {"GH_TOKEN": "dummy", "GH_ORG_NAME": "custom-org"}, clear=False):
            launcher.launch(req)

        mock_git_fetch.assert_called_once_with("my-target-app", org_name="custom-org")
        call_env = mock_create.call_args.kwargs["env"]
        self.assertEqual(call_env.get("TARGET_GIT_AUTHOR_NAME"), "Repo Dev")
        self.assertEqual(call_env.get("TARGET_GIT_AUTHOR_EMAIL"), "repo-dev@example.com")


if __name__ == "__main__":
    unittest.main()
