"""Unit tests for the Shared Base Image package, env, and tool configuration."""

import importlib
import unittest
from unittest.mock import MagicMock, patch


class TestSharedBaseImage(unittest.TestCase):
    def test_base_image_includes_approved_utilities_and_excludes_bloat(self):
        from shared.image import BASE_IMAGE_APT_PACKAGES

        expected_included = {
            "file",
            "bsdextrautils",
            "bc",
            "gettext-base",
            "xxd",
            "dos2unix",
            "zip",
            "zstd",
            "dnsutils",
            "iputils-ping",
            "rsync",
            "socat",
            "strace",
            "postgresql-client",
            "sqlite3",
            "shfmt",
            "tmux",
            "nano",
        }
        expected_excluded = {
            "redis-tools",
            "shellcheck",
            "actionlint",
            "yq",
            "git-lfs",
            "parallel",
            "bsdmainutils",
            "mysql-client",
            "vim",
            "golang-go",
            "rustc",
            "cargo",
            "clang",
            "cmake",
            "sudo",
            "net-tools",
        }

        pkg_set = set(BASE_IMAGE_APT_PACKAGES)
        self.assertTrue(expected_included.issubset(pkg_set))
        self.assertTrue(pkg_set.isdisjoint(expected_excluded))

    def test_base_image_env_and_pinned_ruff_install_command(self):
        from shared.image import (
            BASE_IMAGE_ENV,
            RUFF_INSTALL_COMMAND,
            RUFF_VERSION,
            UV_TOOL_BIN_DIR,
            UV_TOOL_DIR,
        )

        self.assertEqual(UV_TOOL_DIR, "/opt/uv-tools")
        self.assertEqual(UV_TOOL_BIN_DIR, "/usr/local/bin")
        self.assertEqual(
            BASE_IMAGE_ENV,
            {
                "DEBIAN_FRONTEND": "noninteractive",
                "UV_TOOL_DIR": "/opt/uv-tools",
                "UV_TOOL_BIN_DIR": "/usr/local/bin",
            },
        )
        self.assertEqual(RUFF_VERSION, "0.17.6")
        self.assertIn("--no-cache", RUFF_INSTALL_COMMAND)
        self.assertIn("--no-python-downloads", RUFF_INSTALL_COMMAND)
        self.assertIn("--python python3", RUFF_INSTALL_COMMAND)
        self.assertIn(f"ruff=={RUFF_VERSION}", RUFF_INSTALL_COMMAND)

    def test_base_image_wires_env_apt_packages_and_ruff_into_modal_image(self):
        import shared.image as image_mod

        mock_image = MagicMock()
        mock_image.env.return_value = mock_image
        mock_image.apt_install.return_value = mock_image
        mock_image.run_commands.return_value = mock_image
        mock_image.add_local_file.return_value = mock_image
        mock_image.add_local_dir.return_value = mock_image

        try:
            with (
                patch("modal.Image.from_registry", return_value=mock_image) as mock_from_registry,
                patch("shared.app_staging.stage_app_template_into_image", side_effect=lambda img: img),
                patch("shared.app_staging.stage_sandbox_runtime_into_image", side_effect=lambda img: img),
            ):
                reloaded = importlib.reload(image_mod)

                mock_from_registry.assert_called_once_with("ubuntu:24.04", add_python="3.12")
                mock_image.env.assert_called_once_with(reloaded.BASE_IMAGE_ENV)
                mock_image.apt_install.assert_called_once_with(*reloaded.BASE_IMAGE_APT_PACKAGES)

                first_run_cmds = mock_image.run_commands.call_args_list[0].args
                uv_idx = next(i for i, cmd in enumerate(first_run_cmds) if "astral.sh/uv/install.sh" in cmd)
                ruff_idx = first_run_cmds.index(reloaded.RUFF_INSTALL_COMMAND)
                self.assertGreater(ruff_idx, uv_idx)
        finally:
            importlib.reload(image_mod)
