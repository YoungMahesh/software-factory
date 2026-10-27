"""Subsystem tests for Modal Sandbox runner and configuration."""

import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import ANY, MagicMock, patch


class TestT3CodeIntegration(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]
        self.sandbox_main = self.repo_root / "sandbox" / "main.py"
        self.startup_sh = self.repo_root / "shared" / "startup.sh"

    def test_help_contains_t3_flags(self):
        import sys

        res = subprocess.run(
            [sys.executable, str(self.sandbox_main), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("--t3", res.stdout)
        self.assertIn("--t3code", res.stdout)
        self.assertIn("--t3-port", res.stdout)
        self.assertIn("T3 Code server", res.stdout)

    def test_parser_t3_flags(self):
        from sandbox.main import create_parser

        parser = create_parser()
        args = parser.parse_args(["-s", "my-secret", "--t3"])
        self.assertTrue(args.t3)
        self.assertEqual(args.t3_port, 3775)

        args_alias = parser.parse_args(["-s", "my-secret", "--t3code", "--t3-port", "3776"])
        self.assertTrue(args_alias.t3)
        self.assertEqual(args_alias.t3_port, 3776)

    def test_snapshot_cannot_be_used_with_t3(self):
        import sys

        res = subprocess.run(
            [sys.executable, str(self.sandbox_main), "--snapshot", "sb-123", "--t3"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("--snapshot cannot be used with launch configuration arguments", res.stderr)

    def test_t3_port_collision_with_reserved_web_port(self):
        from sandbox.main import create_parser, run_sandbox_launch
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_dir = Path(tmpdir) / "secrets" / "test-repo"
            secrets_dir.mkdir(parents=True)
            (secrets_dir / "fetch.env").write_text("DUMMY=1")

            parser = create_parser()
            args = parser.parse_args(["-s", "test-repo", "--t3", "--t3-port", "3000"])
            with self.assertRaises(SystemExit):
                run_sandbox_launch(args, repo_root=Path(tmpdir))

    def test_t3_port_collision_with_opencode(self):
        from sandbox.main import create_parser, run_sandbox_launch
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_dir = Path(tmpdir) / "secrets" / "test-repo"
            secrets_dir.mkdir(parents=True)
            (secrets_dir / "fetch.env").write_text("DUMMY=1")

            parser = create_parser()
            args = parser.parse_args(["-s", "test-repo", "--t3", "--opencode", "--t3-port", "4096"])
            with self.assertRaises(SystemExit):
                run_sandbox_launch(args, repo_root=Path(tmpdir))

    def test_t3_port_collision_with_metro(self):
        from sandbox.main import create_parser, run_sandbox_launch
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_dir = Path(tmpdir) / "secrets" / "test-repo"
            secrets_dir.mkdir(parents=True)
            (secrets_dir / "fetch.env").write_text("DUMMY=1")

            parser = create_parser()
            args = parser.parse_args(["-s", "test-repo", "--t3", "--react-native", "--t3-port", "8081"])
            with self.assertRaises(SystemExit):
                run_sandbox_launch(args, repo_root=Path(tmpdir))

    def test_startup_script_contains_t3_daemon_and_check_script(self):
        content = self.startup_sh.read_text()
        self.assertIn("ENABLE_T3", content)
        self.assertIn("check-t3", content)
        self.assertIn("t3 serve", content)
        self.assertIn("--auto-bootstrap-project-from-cwd", content)

    def test_startup_and_setup_scripts_contain_antigravity_preauth(self):
        startup_content = self.startup_sh.read_text()
        setup_content = (self.repo_root / "scripts" / "setup.sh").read_text()

        for content in [startup_content, setup_content]:
            self.assertIn("acp_token.json", content)
            self.assertIn("oauth-personal", content)
            self.assertIn("dummy-client-id", content)
            self.assertIn("providerInstances", content)
            self.assertIn("antigravity", content)
            self.assertIn("antigravity-mgh", content)
            self.assertIn("antigravity-anv", content)
            self.assertIn("Antigravity (MGH)", content)
            self.assertIn("Antigravity (ANV)", content)
            self.assertIn("/root/.t3/caches", content)
            self.assertIn("gemini-3.8-flash-high", content)

    def test_switch_agy_profile_offline_with_cached_profiles(self):
        import tempfile

        switch_script = self.repo_root / "scripts" / "switch-agy-profile.sh"
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir) / ".gemini" / "antigravity-cli"
            profiles_dir = target_dir / "profiles"
            profiles_dir.mkdir(parents=True)
            (profiles_dir / "mgh").write_text('{"refresh_token": "token-mgh"}')
            (profiles_dir / "anv").write_text('{"refresh_token": "token-anv"}')
            (profiles_dir / "m47").write_text('{"refresh_token": "token-m47"}')

            env = {"TARGET_DIR": str(target_dir), "PATH": os.environ["PATH"]}
            res = subprocess.run(["bash", str(switch_script), "mgh"], capture_output=True, text=True, env=env)
            self.assertEqual(res.returncode, 0, f"Failed: {res.stderr}")
            self.assertIn("Switched Antigravity CLI profile to: mgh", res.stdout)
            self.assertEqual((target_dir / "antigravity-oauth-token").read_text(), '{"refresh_token": "token-mgh"}')

    def test_build_sandbox_image_stages_multiple_antigravity_accounts(self):
        from shared.image import (
            LOCAL_ANTIGRAVITY_SECRET,
            LOCAL_ANTIGRAVITY_SECRET_MGH,
            LOCAL_ANTIGRAVITY_SECRET_ANV,
            REMOTE_ANTIGRAVITY_SECRET,
            REMOTE_ANTIGRAVITY_SECRET_MGH,
            REMOTE_ANTIGRAVITY_SECRET_ANV,
        )

        self.assertTrue(str(LOCAL_ANTIGRAVITY_SECRET_MGH).endswith("antigravity-oauth-token-mgh.json"))
        self.assertTrue(str(LOCAL_ANTIGRAVITY_SECRET_ANV).endswith("antigravity-oauth-token-anv.json"))
        self.assertEqual(REMOTE_ANTIGRAVITY_SECRET_MGH, "/root/secrets/antigravity-oauth-token-mgh.json")
        self.assertEqual(REMOTE_ANTIGRAVITY_SECRET_ANV, "/root/secrets/antigravity-oauth-token-anv.json")

    def test_startup_and_setup_scripts_contain_opencode_preauth(self):
        startup_content = self.startup_sh.read_text()
        setup_content = (self.repo_root / "scripts" / "setup.sh").read_text()

        for content in [startup_content, setup_content]:
            self.assertIn("OPENCODE_GO_API_KEY", content)
            self.assertIn("providerInstances", content)
            self.assertIn("opencode", content)
            self.assertIn("/root/.opencode/bin/opencode", content)

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
        import tempfile

        mock_image = MagicMock()
        mock_build_image.return_value = mock_image
        mock_sandbox = MagicMock()
        mock_sandbox.object_id = "sb-t3-123"
        mock_tunnel = MagicMock()
        mock_tunnel.url = "https://test-t3.modal.run"
        mock_sandbox.tunnels.return_value = {3775: mock_tunnel}
        mock_sandbox_create.return_value = mock_sandbox

        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_dir = Path(tmpdir) / "secrets" / "my-secret"
            secrets_dir.mkdir(parents=True)
            (secrets_dir / "fetch.env").write_text("DUMMY=1")

            parser = create_parser()
            args = parser.parse_args(["-s", "my-secret", "--t3"])
            run_sandbox_launch(args, repo_root=Path(tmpdir))

        mock_app_lookup.assert_called_once_with("my-secret", create_if_missing=True)
        mock_build_image.assert_called_once_with(
            opencode=False,
            agy=False,
            browser=False,
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

    def test_build_sandbox_image_layers_t3(self):
        from unittest.mock import call
        from shared.image import (
            build_sandbox_image,
            T3_VERSION,
            T3_TAR_URL,
            T3_PATCH_SCRIPT,
            T3_ANTIGRAVITY_URL,
            T3_ANTIGRAVITY_VERSION_DIR,
            T3_ANTIGRAVITY_MANAGED_DIR,
            T3_INSTALL_COMPLETE_JSON,
            T3_ACTIVE_JSON,
            LOCAL_OPENCODE_CONFIG,
            REMOTE_OPENCODE_CONFIG,
            LOCAL_OPENCODE_SECRET,
            REMOTE_OPENCODE_SECRET,
            LOCAL_ANTIGRAVITY_SECRET,
            LOCAL_ANTIGRAVITY_SECRET_MGH,
            LOCAL_ANTIGRAVITY_SECRET_ANV,
            REMOTE_ANTIGRAVITY_SECRET,
            REMOTE_ANTIGRAVITY_SECRET_MGH,
            REMOTE_ANTIGRAVITY_SECRET_ANV,
        )

        with patch("shared.image.base_image") as mock_base, patch(
            "shared.image.add_local_files_if_present"
        ) as mock_add_files:
            mock_img1 = MagicMock()
            mock_img2 = MagicMock()
            mock_img3 = MagicMock()
            mock_base.run_commands.return_value = mock_img1
            mock_add_files.side_effect = lambda img, *args, **kwargs: img
            mock_img1.run_commands.return_value = mock_img2
            mock_img2.env.return_value = mock_img3

            result = build_sandbox_image(t3=True)

            mock_base.run_commands.assert_called_once_with(
                "curl -fsSL https://opencode.ai/v2/install | bash"
            )
            mock_add_files.assert_has_calls(
                [
                    call(
                        mock_img1,
                        [
                            (LOCAL_OPENCODE_CONFIG, REMOTE_OPENCODE_CONFIG),
                            (LOCAL_OPENCODE_SECRET, REMOTE_OPENCODE_SECRET),
                        ],
                    ),
                    call(
                        mock_img2,
                        [
                            (LOCAL_ANTIGRAVITY_SECRET, REMOTE_ANTIGRAVITY_SECRET),
                            (LOCAL_ANTIGRAVITY_SECRET_MGH, REMOTE_ANTIGRAVITY_SECRET_MGH),
                            (LOCAL_ANTIGRAVITY_SECRET_ANV, REMOTE_ANTIGRAVITY_SECRET_ANV),
                        ],
                    ),
                ]
            )
            mock_img1.run_commands.assert_called_once_with(
                "mkdir -p /opt/t3",
                f"curl -fsSL {T3_TAR_URL} | tar -xz -C /opt/t3 --strip-components=1",
                "ln -sf /opt/t3/t3 /usr/local/bin/t3",
                T3_PATCH_SCRIPT,
                f"mkdir -p {T3_ANTIGRAVITY_VERSION_DIR}",
                f"curl -fsSL {T3_ANTIGRAVITY_URL} -o /tmp/agy-acp.zip",
                f"unzip -q /tmp/agy-acp.zip -d {T3_ANTIGRAVITY_VERSION_DIR}",
                "rm -f /tmp/agy-acp.zip",
                (
                    f"chmod 0755 {T3_ANTIGRAVITY_VERSION_DIR}/agy_acp_server.par "
                    f"{T3_ANTIGRAVITY_VERSION_DIR}/localharness_external"
                ),
                f"echo '{T3_INSTALL_COMPLETE_JSON}' > {T3_ANTIGRAVITY_VERSION_DIR}/.install-complete.json",
                f"echo '{T3_ACTIVE_JSON}' > {T3_ANTIGRAVITY_MANAGED_DIR}/active.json",
            )
            mock_img2.env.assert_called_once_with(
                {"PATH": "/root/.opencode/bin:${PATH}"}
            )

    def test_t3_patch_script_validity_and_execution(self):
        import ast
        import tempfile
        import base64
        from shared.image import T3_PATCH_SCRIPT

        self.assertTrue(T3_PATCH_SCRIPT.startswith("python3 -c '") and T3_PATCH_SCRIPT.endswith("'"))
        py_code = T3_PATCH_SCRIPT[len("python3 -c '") : -1]

        try:
            ast.parse(py_code)
        except SyntaxError as e:
            self.fail(f"T3_PATCH_SCRIPT contains invalid Python syntax: {e}")

        with tempfile.TemporaryDirectory() as tmpdir:
            test_bin = Path(tmpdir) / "t3"
            t = base64.b64decode(
                "ZnVuY3Rpb24gYnVpbGRBbnRpZ3Jhdml0eUFjcFNwYXduSW5wdXQoaW5wdXQpIHsKCXJldHVybiB7CgkJY29tbWFuZDogaW5wdXQuaW5zdGFsbGF0aW9uLmV4ZWN1dGFibGVQYXRoLAoJCWFyZ3M6IGlucHV0LnByb2ZpbGUucGxhdGZvcm0gPT09ICJsaW51eCIgPyBbIi0tdWlkPSJdIDogW10sCgkJY3dkOiBpbnB1dC5jd2QsCgkJZW52OiB7CgkJCS4uLmFudGlncmF2aXR5RW52aXJvbm1lbnQoaW5wdXQucHJvZmlsZSwgaW5wdXQuYmFzZUVudiA/PyBwcm9jZXNzLmVudiwgaW5wdXQuYXV0aCA/PyBBTlRJR1JBVklUWV9QRVJTT05BTF9BVVRILCBpbnB1dC5ydW50aW1lVGVtcERpcmVjdG9yeSksCgkJCUFOVElHUkFWSVRZX0hBUk5FU1NfUEFUSDogaW5wdXQuaW5zdGFsbGF0aW9uLmhhcm5lc3NQYXRoCgkJfSwKCQlleHRlbmRFbnY6IGZhbHNlCgl9Owp9"
            )
            r = base64.b64decode(
                "ZnVuY3Rpb24gYnVpbGRBbnRpZ3Jhdml0eUFjcFNwYXduSW5wdXQoaW5wdXQpewpyZXR1cm57CmNvbW1hbmQ6aW5wdXQuaW5zdGFsbGF0aW9uLmV4ZWN1dGFibGVQYXRoLAphcmdzOiBpbnB1dC5wcm9maWxlLnBsYXRmb3JtPT09ImxpbnV4Ij9bIi0tZW5mb3JjZV9rZXJuZWxfaXB2Nl9zdXBwb3J0PWZhbHNlIiwiLS11aWQ9Il06W10sCmN3ZDppbnB1dC5jd2QsCmVudjp7Ci4uLmFudGlncmF2aXR5RW52aXJvbm1lbnQoaW5wdXQucHJvZmlsZSxpbnB1dC5iYXNlRW52Pz9wcm9jZXNzLmVudiwgaW5wdXQuYXV0aD8/QU5USUdSQVZJVFlfUEVSU09OQUxfQVVUSCwgaW5wdXQucnVudGltZVRlbXBEaXJlY3RvcnkpLApBTlRJR1JBVklUWV9IQVJORVNTX1BBVEg6aW5wdXQuaW5zdGFsbGF0aW9uLmhhcm5lc3NQYXRoCn0sCmV4dGVuZEVudjpmYWxzZQp9Owp9"
            )
            self.assertEqual(len(t), 426)
            self.assertEqual(len(r), 426)
            self.assertEqual(len(t), len(r), "Patch must be length-preserving to prevent SEA corruption")

            initial_content = b"PREFIX_" + t + b"_SUFFIX"
            test_bin.write_bytes(initial_content)

            test_cmd = T3_PATCH_SCRIPT.replace("/opt/t3/t3", str(test_bin))
            res = subprocess.run(["bash", "-c", test_cmd], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Patch script failed: {res.stderr}")

            patched_content = test_bin.read_bytes()
            self.assertIn(b"--enforce_kernel_ipv6_support=false", patched_content)
            self.assertNotIn(t, patched_content)
            self.assertEqual(len(patched_content), len(initial_content), "Binary size must not change")

            # Verify idempotency on already-patched binary
            res_idempotent = subprocess.run(["bash", "-c", test_cmd], capture_output=True, text=True)
            self.assertEqual(res_idempotent.returncode, 0, f"Idempotent patch failed: {res_idempotent.stderr}")
            self.assertEqual(test_bin.read_bytes(), patched_content)

    def test_startup_script_mints_pairing_token(self):
        content = self.startup_sh.read_text()
        self.assertIn("t3 auth pairing create --ttl 24h --json > /tmp/t3-pairing.json", content)

    def test_generate_ascii_qr(self):
        from sandbox.main import generate_ascii_qr

        qr_text = generate_ascii_qr("https://test-t3.modal.run/pair#token=ABCD")
        self.assertIsNotNone(qr_text)
        self.assertTrue(any(c in qr_text for c in ["█", "▀", "▄"]))

    def test_print_access_info_with_1click_pair_url_and_qr(self):
        import io
        from unittest.mock import patch
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
                cloudflare_enabled=False,
            )

        output = stdout_buf.getvalue()
        self.assertIn("• T3 Code:  https://test-t3.modal.run/pair#token=ABCD123", output)
        self.assertIn("Scan with T3 Code Mobile App (iOS / Android):", output)
        self.assertIn("█▀▀█", output)

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
        import tempfile

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
            secrets_dir = Path(tmpdir) / "secrets" / "my-secret"
            secrets_dir.mkdir(parents=True)
            (secrets_dir / "fetch.env").write_text("DUMMY=1")

            parser = create_parser()
            args = parser.parse_args(["-s", "my-secret", "--t3"])
            run_sandbox_launch(args, repo_root=Path(tmpdir))

        mock_sandbox.exec.assert_called_with("t3", "auth", "pairing", "create", "--ttl", "24h", "--json")
        call_kwargs = mock_print_access.call_args.kwargs
        self.assertEqual(call_kwargs["t3_pair_url"], "https://t3.modal.run/pair#token=SECRET_TOKEN_XYZ")
        self.assertIsNotNone(call_kwargs["t3_qr_code"])
