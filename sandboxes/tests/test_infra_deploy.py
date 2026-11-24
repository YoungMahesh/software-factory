"""Unit tests for Resource Plane VPS infrastructure deployment module."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from sandbox.infra_deploy import (
    DEFAULT_REMOTE_DIR,
    DEFAULT_SSH_PORT,
    DEFAULT_SSH_USER,
    VpsSshConfig,
    build_ssh_cmd,
    check_remote_docker,
    check_ssh_connection,
    deploy_resource_plane,
    execute_remote_deploy,
    find_resource_plane_source_dir,
    main,
    resolve_vps_ssh_config,
    sync_resource_plane_to_vps,
)

from sandbox.main import main as sandbox_main


class TestInfraDeploy(unittest.TestCase):
    """Test suite for infra_deploy configuration, commands, and orchestration."""

    def setUp(self):
        self.sample_config = VpsSshConfig(
            host="vps.example.com",
            user="admin",
            port=2222,
            key_path=Path("/tmp/test_key"),
            remote_dir="/srv/resource-plane",
        )

    def test_infra_deploy_check_only_reads_checkout_env(self):
        argv = ["modal-sandbox", "infra", "deploy", "--check-only"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("RESOURCE_PLANE_SSH_HOST=fixture.invalid\n")
            with (
                patch("sys.argv", argv),
                patch.dict(os.environ, {}, clear=True),
                patch("sandbox.infra_deploy.resolve_factory_root", return_value=root),
                patch("sandbox.infra_deploy.check_ssh_connection", return_value=True) as ssh,
                patch("sandbox.infra_deploy.check_remote_docker", return_value=(True, "Docker OK")),
                self.assertRaises(SystemExit) as exit_context,
            ):
                sandbox_main()

        self.assertEqual(exit_context.exception.code, 0)
        self.assertEqual(ssh.call_args.args[0].host, "fixture.invalid")

    def test_resolve_vps_ssh_config_from_args(self):
        """Resolves configuration directly from explicit arguments."""
        cfg = resolve_vps_ssh_config(
            host="myhost.test",
            user="ubuntu",
            port=2200,
            key_path="/tmp/key",
            remote_dir="/var/resource-plane",
        )
        self.assertEqual(cfg.host, "myhost.test")
        self.assertEqual(cfg.user, "ubuntu")
        self.assertEqual(cfg.port, 2200)
        self.assertEqual(cfg.key_path, Path("/tmp/key").resolve())
        self.assertEqual(cfg.remote_dir, "/var/resource-plane")

    def test_resolve_vps_ssh_config_missing_host_raises(self):
        """Raises ValueError when host is not provided in args or environment."""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                resolve_vps_ssh_config()
            self.assertIn("Missing VPS SSH host", str(ctx.exception))

    def test_resolve_vps_ssh_config_from_env(self):
        """Resolves configuration from RESOURCE_PLANE_SSH_* environment variables."""
        env = {
            "RESOURCE_PLANE_SSH_HOST": "envhost.test",
            "RESOURCE_PLANE_SSH_USER": "deploy",
            "RESOURCE_PLANE_SSH_PORT": "22022",
            "RESOURCE_PLANE_REMOTE_DIR": "/custom/path",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = resolve_vps_ssh_config()
            self.assertEqual(cfg.host, "envhost.test")
            self.assertEqual(cfg.user, "deploy")
            self.assertEqual(cfg.port, 22022)
            self.assertEqual(cfg.remote_dir, "/custom/path")

    def test_resolve_vps_ssh_config_db_host_fallback(self):
        """Falls back to legacy DB_HOST_SSH_* variables if RESOURCE_PLANE_* is unset."""
        env = {
            "DB_HOST_SSH_HOST": "legacyhost.test",
            "DB_HOST_SSH_USER": "legacyuser",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = resolve_vps_ssh_config()
            self.assertEqual(cfg.host, "legacyhost.test")
            self.assertEqual(cfg.user, "legacyuser")
            self.assertEqual(cfg.port, DEFAULT_SSH_PORT)
            self.assertEqual(cfg.remote_dir, DEFAULT_REMOTE_DIR)

    def test_build_ssh_cmd(self):
        """Verifies SSH command structure with and without key and remote command."""
        cmd = build_ssh_cmd(self.sample_config)
        self.assertEqual(cmd, ["ssh", "-p", "2222", "-i", "/tmp/test_key", "admin@vps.example.com"])

        cmd_with_remote = build_ssh_cmd(self.sample_config, "uptime")
        self.assertEqual(
            cmd_with_remote,
            ["ssh", "-p", "2222", "-i", "/tmp/test_key", "admin@vps.example.com", "uptime"],
        )

        simple_cfg = VpsSshConfig(host="simple.test")
        simple_cmd = build_ssh_cmd(simple_cfg)
        self.assertEqual(simple_cmd, ["ssh", "-p", "22", "root@simple.test"])

    @patch("subprocess.run")
    def test_check_ssh_connection_success(self, mock_run):
        """Returns True when SSH probe command returns exit code 0."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        self.assertTrue(check_ssh_connection(self.sample_config))
        mock_run.assert_called_once()
        self.assertIn("exit 0", mock_run.call_args[0][0])

    @patch("subprocess.run")
    def test_check_ssh_connection_failure(self, mock_run):
        """Returns False when SSH probe fails or times out."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=255)
        self.assertFalse(check_ssh_connection(self.sample_config))

        mock_run.side_effect = subprocess.TimeoutExpired(cmd=[], timeout=5)
        self.assertFalse(check_ssh_connection(self.sample_config))

    @patch("subprocess.run")
    def test_check_remote_docker_success(self, mock_run):
        """Returns True when remote Docker check outputs ok."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="ok\n",
        )
        ok, msg = check_remote_docker(self.sample_config)
        self.assertTrue(ok)
        self.assertIn("detected", msg)

    @patch("subprocess.run")
    def test_check_remote_docker_failure(self, mock_run):
        """Returns False when remote Docker check outputs missing or fails."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="missing\n",
        )
        ok, msg = check_remote_docker(self.sample_config)
        self.assertFalse(ok)
        self.assertIn("missing or non-functional", msg)

    def test_find_resource_plane_source_dir(self):
        """Discovers resource-plane directory in monorepo."""
        found = find_resource_plane_source_dir()
        self.assertTrue(found.is_dir())
        self.assertTrue((found / "deploy.sh").is_file())

    @patch("subprocess.Popen")
    def test_sync_resource_plane_to_vps_success(self, mock_popen):
        """Simulates tar pipe over SSH and verifies success."""
        p_tar = MagicMock()
        p_tar.stdout = MagicMock()
        p_tar.wait.return_value = 0

        p_ssh = MagicMock()
        p_ssh.returncode = 0
        p_ssh.communicate.return_value = (b"", b"")

        mock_popen.side_effect = [p_tar, p_ssh]

        result = sync_resource_plane_to_vps(self.sample_config)
        self.assertTrue(result)
        self.assertEqual(mock_popen.call_count, 2)
        self.assertIn("--exclude=.env", mock_popen.call_args_list[0].args[0])

    @patch("subprocess.run")
    def test_execute_remote_deploy_stream(self, mock_run):
        """Executes deploy.sh remotely in stream mode."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        code, out = execute_remote_deploy(self.sample_config, stream=True)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        mock_run.assert_called_once()
        self.assertIn("./deploy.sh", mock_run.call_args[0][0][-1])

    @patch("sandbox.infra_deploy.check_ssh_connection")
    @patch("sandbox.infra_deploy.check_remote_docker")
    @patch("sandbox.infra_deploy.sync_resource_plane_to_vps")
    @patch("sandbox.infra_deploy.execute_remote_deploy")
    def test_deploy_resource_plane_pipeline_full_success(
        self,
        mock_exec,
        mock_sync,
        mock_docker,
        mock_ssh,
    ):
        """Verifies full orchestration flow when all steps succeed."""
        mock_ssh.return_value = True
        mock_docker.return_value = (True, "Docker OK")
        mock_sync.return_value = True
        mock_exec.return_value = (0, "Success output")

        code = deploy_resource_plane(self.sample_config, stream=False)
        self.assertEqual(code, 0)
        mock_ssh.assert_called_once()
        mock_docker.assert_called_once()
        mock_sync.assert_called_once()
        mock_exec.assert_called_once()

    @patch("sandbox.infra_deploy.check_ssh_connection")
    def test_deploy_resource_plane_pipeline_ssh_failure(self, mock_ssh):
        """Aborts deployment immediately when SSH connectivity check fails."""
        mock_ssh.return_value = False
        code = deploy_resource_plane(self.sample_config)
        self.assertEqual(code, 1)

    @patch("sandbox.infra_deploy.check_ssh_connection")
    @patch("sandbox.infra_deploy.check_remote_docker")
    def test_main_check_only(self, mock_docker, mock_ssh):
        """Runs check-only mode and reports status without deploying."""
        mock_ssh.return_value = True
        mock_docker.return_value = (True, "Docker OK")

        code = main(["--host", "test.vps", "--check-only"])
        self.assertEqual(code, 0)
        mock_ssh.assert_called_once()
        mock_docker.assert_called_once()
