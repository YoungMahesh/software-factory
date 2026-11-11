"""Launch orchestration and SSH access tests for T3 Code integration."""

import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from shared.image import T3_STORAGE_MOUNT_PATH, DEFAULT_T3_USAGE_VOLUME


class TestT3CodeLaunchSSH(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]

    def test_generate_ascii_qr(self):
        from sandbox.main import generate_ascii_qr

        qr_text = generate_ascii_qr("https://test-t3.modal.run/pair#token=ABCD")
        self.assertIsNotNone(qr_text)
        self.assertTrue(any(c in qr_text for c in ["█", "▀", "▄"]))

    def test_print_access_info_with_1click_pair_url_and_qr(self):
        from sandbox.main import print_access_info

        mock_sb = MagicMock()
        mock_sb.object_id = "sb-123"

        stdout_buf = io.StringIO()
        with patch("sys.stdout", stdout_buf):
            print_access_info(
                sandbox=mock_sb,
                app_name="my-app",
                t3_url="https://test-t3.modal.run",
                t3_port=3775,
                t3_pair_url="https://test-t3.modal.run/pair#token=ABCD123",
                t3_qr_code="  █▀▀█\n  ▀▀▀▀",
                t3_persist=True,
                t3_usage_volume="t3code-usage-v1",
                cloudflare_enabled=False,
            )

        output = stdout_buf.getvalue()
        self.assertIn("• T3 Code:  https://test-t3.modal.run/pair#token=ABCD123", output)
        self.assertIn("• T3 Storage: Persistent volume (t3code-usage-v1)", output)
        self.assertIn("Scan with T3 Code Mobile App (iOS / Android):", output)
        self.assertIn("█▀▀█", output)

    def test_print_access_info_cloudflare_custom_domain(self):
        from sandbox.main import print_access_info
        mock_sb = MagicMock()
        mock_sb.object_id = "sb-cf-custom"

        stdout_buf = io.StringIO()
        with patch.dict(os.environ, {"MODAL_SANDBOX_TUNNEL_DOMAIN": "preview.example.com"}):
            with patch("sys.stdout", stdout_buf):
                print_access_info(sandbox=mock_sb, app_name="my-app", cloudflare_enabled=True)

        output = stdout_buf.getvalue()
        self.assertIn("• Cloudflare: https://preview.example.com (port 3000)", output)

    def test_print_access_info_cloudflare_unset_domain_fallback(self):
        from sandbox.main import print_access_info
        mock_sb = MagicMock()
        mock_sb.object_id = "sb-cf-fallback"

        stdout_buf = io.StringIO()
        with patch.dict(os.environ, {"MODAL_SANDBOX_TUNNEL_DOMAIN": "", "CLOUDFLARE_TUNNEL_DOMAIN": ""}):
            with patch("sys.stdout", stdout_buf):
                print_access_info(sandbox=mock_sb, app_name="my-app", cloudflare_enabled=True)

        output = stdout_buf.getvalue()
        self.assertIn("• Cloudflare: Active on port 3000 (set MODAL_SANDBOX_TUNNEL_DOMAIN to display custom URL)", output)

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    @patch("sandbox.main.build_sandbox_image")
    @patch("sandbox.main.load_ssh_pub_key", return_value="ssh-rsa dummy")
    def test_run_sandbox_launch_passes_t3_configuration(
        self,
        mock_load_pubkey,
        mock_build_image,
        mock_app_lookup,
        mock_sandbox_create,
    ):
        from sandbox.main import create_parser, run_sandbox_launch

        mock_image = MagicMock()
        mock_build_image.return_value = mock_image
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-t3-123"
        mock_tunnel = MagicMock()
        mock_tunnel.url = "https://test-t3.modal.run"
        mock_sandbox.tunnels.return_value = {3775: mock_tunnel}
        mock_sandbox_create.return_value = mock_sandbox

        with tempfile.TemporaryDirectory() as tmpdir:
            dotenv_file = Path(tmpdir) / ".env"
            dotenv_file.write_text("GH_TOKEN=dummy\nGH_ORG_NAME=sFactory0\n")

            parser = create_parser()
            args = parser.parse_args(["-r", "my-repo", "--t3"])
            run_sandbox_launch(args, repo_root=Path(tmpdir))

        mock_app_lookup.assert_called_once_with("my-repo", create_if_missing=True)
        mock_build_image.assert_called_once_with(
            opencode=False,
            agy=False,
            browser=True,
            modal_tooling=False,
            react_native=False,
            t3=True,
            herdr=False,
            pi=False,
        )
        call_kwargs = mock_sandbox_create.call_args.kwargs
        self.assertIn(3775, call_kwargs["encrypted_ports"])
        self.assertEqual(call_kwargs["env"]["ENABLE_T3"], "1")
        self.assertEqual(call_kwargs["env"]["T3_PORT"], "3775")
        self.assertEqual(call_kwargs["env"]["FLAGS_enforce_kernel_ipv6_support"], "false")
        self.assertEqual(call_kwargs["env"]["ENABLE_T3_PERSISTENCE"], "1")
        self.assertEqual(call_kwargs["env"]["T3_USAGE_VOLUME"], DEFAULT_T3_USAGE_VOLUME)
        self.assertEqual(call_kwargs["env"]["ANTIGRAVITY_DATA_DIR"], f"{T3_STORAGE_MOUNT_PATH}/conversations")
        self.assertIn(T3_STORAGE_MOUNT_PATH, call_kwargs["volumes"])

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    @patch("sandbox.main.build_sandbox_image")
    @patch("sandbox.main.load_ssh_pub_key", return_value="ssh-rsa dummy")
    def test_run_sandbox_launch_no_t3_persist(
        self,
        mock_load_pubkey,
        mock_build_image,
        mock_app_lookup,
        mock_sandbox_create,
    ):
        from sandbox.main import create_parser, run_sandbox_launch

        mock_image = MagicMock()
        mock_build_image.return_value = mock_image
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-t3-no-persist"
        mock_tunnel = MagicMock()
        mock_tunnel.url = "https://test-t3.modal.run"
        mock_sandbox.tunnels.return_value = {3775: mock_tunnel}
        mock_sandbox_create.return_value = mock_sandbox

        with tempfile.TemporaryDirectory() as tmpdir:
            dotenv_file = Path(tmpdir) / ".env"
            dotenv_file.write_text("GH_TOKEN=dummy\nGH_ORG_NAME=sFactory0\n")

            parser = create_parser()
            args = parser.parse_args(["-r", "my-repo", "--t3", "--no-t3-persist"])
            run_sandbox_launch(args, repo_root=Path(tmpdir))

        call_kwargs = mock_sandbox_create.call_args.kwargs
        self.assertEqual(call_kwargs["env"]["ENABLE_T3"], "1")
        self.assertNotIn("ENABLE_T3_PERSISTENCE", call_kwargs["env"])
        self.assertNotIn(T3_STORAGE_MOUNT_PATH, call_kwargs["volumes"])

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    @patch("sandbox.main.build_sandbox_image")
    @patch("sandbox.main.load_ssh_pub_key", return_value="ssh-rsa dummy")
    def test_run_sandbox_launch_custom_t3_usage_volume(
        self,
        mock_load_pubkey,
        mock_build_image,
        mock_app_lookup,
        mock_sandbox_create,
    ):
        from sandbox.main import create_parser, run_sandbox_launch

        mock_image = MagicMock()
        mock_build_image.return_value = mock_image
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-t3-custom-vol"
        mock_tunnel = MagicMock()
        mock_tunnel.url = "https://test-t3.modal.run"
        mock_sandbox.tunnels.return_value = {3775: mock_tunnel}
        mock_sandbox_create.return_value = mock_sandbox

        with tempfile.TemporaryDirectory() as tmpdir:
            dotenv_file = Path(tmpdir) / ".env"
            dotenv_file.write_text("GH_TOKEN=dummy\nGH_ORG_NAME=sFactory0\n")

            parser = create_parser()
            args = parser.parse_args(["-r", "my-repo", "--t3", "--t3-usage-volume", "custom-usage-volume"])
            run_sandbox_launch(args, repo_root=Path(tmpdir))

        call_kwargs = mock_sandbox_create.call_args.kwargs
        self.assertEqual(call_kwargs["env"]["ENABLE_T3_PERSISTENCE"], "1")
        self.assertEqual(call_kwargs["env"]["T3_USAGE_VOLUME"], "custom-usage-volume")
        self.assertIn(T3_STORAGE_MOUNT_PATH, call_kwargs["volumes"])

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    @patch("sandbox.main.build_sandbox_image")
    @patch("sandbox.main.load_ssh_pub_key", return_value="ssh-rsa dummy")
    @patch("sandbox.main.print_access_info")
    def test_run_sandbox_launch_resolves_pair_url_from_container(
        self,
        mock_print_access,
        mock_load_pubkey,
        mock_build_image,
        mock_app_lookup,
        mock_sandbox_create,
    ):
        from sandbox.main import create_parser, run_sandbox_launch

        mock_image = MagicMock()
        mock_build_image.return_value = mock_image
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-t3-456"
        mock_tunnel = MagicMock()
        mock_tunnel.url = "https://t3.modal.run"
        mock_sandbox.tunnels.return_value = {3775: mock_tunnel}

        # Mock sandbox.exec("cat", "/tmp/t3-pairing.json")
        mock_exec_proc = MagicMock()
        mock_exec_proc.wait.return_value = 0
        mock_exec_proc.stdout.read.return_value = '{"credential": "SECRET_TOKEN_XYZ"}'
        mock_sandbox.exec.return_value = mock_exec_proc

        mock_sandbox_create.return_value = mock_sandbox

        with tempfile.TemporaryDirectory() as tmpdir:
            dotenv_file = Path(tmpdir) / ".env"
            dotenv_file.write_text("GH_TOKEN=dummy\nGH_ORG_NAME=sFactory0\n")

            parser = create_parser()
            args = parser.parse_args(["-r", "my-repo", "--t3"])
            run_sandbox_launch(args, repo_root=Path(tmpdir))

        mock_sandbox.exec.assert_called_with("t3", "auth", "pairing", "create", "--ttl", "24h", "--json")
        exec_calls = mock_sandbox.exec.call_args_list
        self.assertEqual(len(exec_calls), 2)
        self.assertEqual(exec_calls[0].args[0], "python3")
        self.assertEqual(exec_calls[0].args[1], "-c")
        self.assertIn("T3_PUBLIC_URL", exec_calls[0].args[2])
        self.assertIn("https://t3.modal.run", exec_calls[0].args[2])
        self.assertIn("devUrl", exec_calls[0].args[2])
        call_kwargs = mock_print_access.call_args.kwargs
        self.assertEqual(call_kwargs["t3_pair_url"], "https://t3.modal.run/pair#token=SECRET_TOKEN_XYZ")
        self.assertIsNotNone(call_kwargs["t3_qr_code"])

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    @patch("sandbox.main.build_sandbox_image")
    @patch("sandbox.main.load_ssh_pub_key", return_value="ssh-rsa dummy")
    @patch("sandbox.main.print_access_info")
    def test_run_sandbox_launch_sets_t3_ssh_host_env_and_cfg(
        self,
        mock_print_access,
        mock_load_pubkey,
        mock_build_image,
        mock_app_lookup,
        mock_sandbox_create,
    ):
        from sandbox.main import create_parser, run_sandbox_launch

        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-t3-ssh-1"
        mock_tunnel = MagicMock()
        mock_tunnel.url = "https://t3.modal.run"
        mock_sandbox.tunnels.return_value = {3775: mock_tunnel}

        mock_exec_proc = MagicMock()
        mock_exec_proc.wait.return_value = 0
        mock_exec_proc.stdout.read.return_value = '{"credential": "TOKEN"}'
        mock_sandbox.exec.return_value = mock_exec_proc
        mock_sandbox_create.return_value = mock_sandbox

        with tempfile.TemporaryDirectory() as tmpdir:
            dotenv_file = Path(tmpdir) / ".env"
            dotenv_file.write_text("GH_TOKEN=dummy\nGH_ORG_NAME=sFactory0\n")

            parser = create_parser()
            args = parser.parse_args(["-r", "my-repo", "--t3"])
            run_sandbox_launch(args, repo_root=Path(tmpdir))

        create_kwargs = mock_sandbox_create.call_args.kwargs
        env = create_kwargs["env"]
        self.assertIn("T3_SSH_HOST", env)
        self.assertTrue(env["T3_SSH_HOST"].startswith("my-repo-"))

        exec_calls = mock_sandbox.exec.call_args_list
        cfg_exec = exec_calls[0]
        self.assertEqual(cfg_exec.args[0], "python3")
        self.assertIn("T3_SSH_HOST=", cfg_exec.args[2])
        self.assertIn("PRETTY_HOSTNAME", cfg_exec.args[2])

    @patch("modal.Sandbox.create")
    @patch("modal.App.lookup")
    @patch("sandbox.main.build_sandbox_image")
    @patch("sandbox.main.load_ssh_pub_key", return_value="ssh-rsa dummy")
    @patch("sandbox.main.print_access_info")
    def test_run_sandbox_launch_custom_t3_ssh_host(
        self,
        mock_print_access,
        mock_load_pubkey,
        mock_build_image,
        mock_app_lookup,
        mock_sandbox_create,
    ):
        from sandbox.main import create_parser, run_sandbox_launch

        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-t3-ssh-2"
        mock_tunnel = MagicMock()
        mock_tunnel.url = "https://t3.modal.run"
        mock_sandbox.tunnels.return_value = {3775: mock_tunnel}

        mock_exec_proc = MagicMock()
        mock_exec_proc.wait.return_value = 0
        mock_exec_proc.stdout.read.return_value = '{"credential": "TOKEN"}'
        mock_sandbox.exec.return_value = mock_exec_proc
        mock_sandbox_create.return_value = mock_sandbox

        with tempfile.TemporaryDirectory() as tmpdir:
            dotenv_file = Path(tmpdir) / ".env"
            dotenv_file.write_text("GH_TOKEN=dummy\nGH_ORG_NAME=sFactory0\n")

            parser = create_parser()
            args = parser.parse_args(["-r", "my-repo", "--t3", "--t3-ssh-host", "my-custom-box"])
            run_sandbox_launch(args, repo_root=Path(tmpdir))

        create_kwargs = mock_sandbox_create.call_args.kwargs
        env = create_kwargs["env"]
        self.assertEqual(env["T3_SSH_HOST"], "my-custom-box")

        call_kwargs = mock_print_access.call_args.kwargs
        self.assertEqual(call_kwargs["t3_ssh_host"], "my-custom-box")
