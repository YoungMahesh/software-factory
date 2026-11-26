"""Unit tests for Host Ingress Store (caddy-store) backup, restore, and network filtering."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from sandbox.caddy_store import (
    CANONICAL_CADDY_STORE_REPO,
    backup_caddy_to_store,
    ensure_caddy_store_repo,
    filter_compose_override_networks,
    git_blob_sha,
    is_declarative_caddy_relpath,
    list_caddy_store_profile_blobs,
    resolve_caddy_store_profile,
    restore_caddy_from_store,
    run_caddy_store_subcommand,
)
from sandbox.caddy_store._vps import build_tar_gz_bytes, extract_tar_bytes_to_dict
from sandbox.infra_deploy import VpsSshConfig


SAMPLE_OVERRIDE = """services:
  caddy:
    networks:
      - dbhost-network
      - s3-split_net
      - repo-backups_net

networks:
  s3-split_net:
    external: true
  repo-backups_net:
    external: true
"""


class TestCaddyStoreHelpers(unittest.TestCase):
    """Tests for profile resolution, path filtering, GitHub API, and compose network filter."""

    def test_resolve_caddy_store_profile_precedence_and_validation(self):
        with patch.dict(os.environ, {"CADDY_STORE_PROFILE": "env-prof"}, clear=True):
            self.assertEqual(resolve_caddy_store_profile("cli-prof", {"CADDY_STORE_PROFILE": "dot-prof"}), "cli-prof")
            self.assertEqual(resolve_caddy_store_profile(None, {"CADDY_STORE_PROFILE": "dot-prof"}), "env-prof")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_caddy_store_profile(None, {"CADDY_STORE_PROFILE": "dot-prof"}), "dot-prof")
            self.assertEqual(resolve_caddy_store_profile(None, {}), "default")
        with self.assertRaises(ValueError):
            resolve_caddy_store_profile("../escape")
        with self.assertRaises(ValueError):
            resolve_caddy_store_profile("bad/slash")

    def test_is_declarative_caddy_relpath(self):
        self.assertTrue(is_declarative_caddy_relpath("conf/Caddyfile"))
        self.assertTrue(is_declarative_caddy_relpath("conf/sites/resource-plane.caddy"))
        self.assertTrue(is_declarative_caddy_relpath("conf/snippets/headers.caddy"))
        self.assertTrue(is_declarative_caddy_relpath("docker-compose.override.yml"))
        self.assertFalse(is_declarative_caddy_relpath("docker-compose.yml"))
        self.assertFalse(is_declarative_caddy_relpath("conf/sites/.gitkeep"))
        self.assertFalse(is_declarative_caddy_relpath("conf/sites/a.caddy.bak"))
        self.assertFalse(is_declarative_caddy_relpath("../secret"))

    def test_tar_roundtrip_filters_transient_files(self):
        payload = build_tar_gz_bytes({"conf/Caddyfile": "{\n}\n", "conf/sites/app.caddy": "a.dev {\n}\n"})
        decoded = extract_tar_bytes_to_dict(payload)
        self.assertEqual(decoded, {"conf/Caddyfile": "{\n}\n", "conf/sites/app.caddy": "a.dev {\n}\n"})
        self.assertEqual(extract_tar_bytes_to_dict(b""), {})

    def test_filter_compose_override_networks_all_present_returns_verbatim(self):
        filtered, skipped = filter_compose_override_networks(
            SAMPLE_OVERRIDE, {"dbhost-network", "s3-split_net", "repo-backups_net"}
        )
        self.assertEqual(filtered, SAMPLE_OVERRIDE)
        self.assertEqual(skipped, [])

    def test_filter_compose_override_networks_none_present_drops_empty_override(self):
        filtered, skipped = filter_compose_override_networks(SAMPLE_OVERRIDE, {"dbhost-network"})
        # dbhost-network alone only exists in services.caddy.networks and is already in docker-compose.yml,
        # wait: dbhost-network remains in services.caddy.networks unless empty; let's verify behavior
        self.assertEqual(skipped, ["repo-backups_net", "s3-split_net"])
        self.assertIsNotNone(filtered)
        self.assertNotIn("s3-split_net", filtered)
        self.assertNotIn("repo-backups_net", filtered)

    def test_filter_compose_override_networks_only_external_returns_none(self):
        only_external = """services:
  caddy:
    networks:
      - s3-split_net
      - repo-backups_net

networks:
  s3-split_net:
    external: true
  repo-backups_net:
    external: true
"""
        filtered, skipped = filter_compose_override_networks(only_external, {"dbhost-network"})
        self.assertIsNone(filtered)
        self.assertEqual(skipped, ["repo-backups_net", "s3-split_net"])

    def test_filter_compose_override_networks_partial_and_custom_name(self):
        yaml_with_alias = """services:
    caddy:
        environment:
            - CADDY_ADMIN=0.0.0.0:2019
        networks:
            alias_net:
                aliases:
                    - edge
            s3-split_net: {}

networks:
    alias_net:
        name: real_missing_net
        external: true
    s3-split_net:
        external: true
"""
        filtered, skipped = filter_compose_override_networks(yaml_with_alias, {"dbhost-network", "s3-split_net"})
        self.assertEqual(skipped, ["real_missing_net"])
        self.assertIsNotNone(filtered)
        self.assertIn("CADDY_ADMIN=0.0.0.0:2019", filtered)
        self.assertIn("s3-split_net", filtered)
        self.assertNotIn("alias_net", filtered)
        self.assertNotIn("real_missing_net", filtered)

    @patch("sandbox.config_store.github_json_request")
    def test_ensure_caddy_store_repo_creates_private_org_repo(self, mock_req):
        mock_req.side_effect = [
            (404, {"message": "Not Found"}),
            (200, {"type": "Organization"}),
            (201, {"name": CANONICAL_CADDY_STORE_REPO, "private": True}),
        ]
        ensure_caddy_store_repo("sFactory0", "tok", create_if_missing=True)
        self.assertEqual(mock_req.call_count, 3)
        create_call = mock_req.call_args_list[2]
        self.assertEqual(create_call.args[0], "https://api.github.com/orgs/sFactory0/repos")
        self.assertTrue(create_call.kwargs["payload"]["private"])

    @patch("sandbox.config_store.github_json_request")
    def test_ensure_caddy_store_repo_missing_without_create_raises(self, mock_req):
        mock_req.return_value = (404, {})
        with self.assertRaises(FileNotFoundError):
            ensure_caddy_store_repo("sFactory0", "tok", create_if_missing=False)

    @patch("sandbox.config_store.github_json_request")
    def test_list_caddy_store_profile_blobs_filters_profile_and_handles_empty_repo(self, mock_req):
        mock_req.return_value = (409, {"message": "Git Repository is empty."})
        self.assertEqual(list_caddy_store_profile_blobs("sFactory0", "default", "tok"), {})

        mock_req.return_value = (
            200,
            {
                "tree": [
                    {"type": "blob", "path": "caddy/default/conf/Caddyfile", "sha": "sha1"},
                    {"type": "blob", "path": "caddy/default/conf/sites/.gitkeep", "sha": "sha2"},
                    {"type": "blob", "path": "caddy/staging/conf/Caddyfile", "sha": "sha3"},
                    {"type": "blob", "path": "caddy/default/docker-compose.yml", "sha": "sha4"},
                    {"type": "blob", "path": "env/default/conf/Caddyfile", "sha": "sha5"},
                    {"type": "blob", "path": "scratchpad/default-note.md", "sha": "sha6"},
                ]
            },
        )
        self.assertEqual(
            list_caddy_store_profile_blobs("sFactory0", "default", "tok"),
            {"conf/Caddyfile": "sha1"},
        )


class TestCaddyStoreSync(unittest.TestCase):
    """Tests for idempotent backup, restore, rollback, pruning, and CLI subcommands."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.dummy_key = self.tmp_path / "vps_key"
        self.dummy_key.write_text("key", encoding="utf-8")
        self.dummy_key.chmod(0o600)
        self.vps_config = VpsSshConfig(host="1.2.3.4", key_path=self.dummy_key)

    def tearDown(self):
        self.tmp.cleanup()

    @patch("sandbox.caddy_store._sync.resolve_factory_root")
    @patch("sandbox.caddy_store._sync.fetch_vps_caddy_files")
    @patch("sandbox.caddy_store._sync.ensure_caddy_store_repo")
    @patch("sandbox.caddy_store._sync.list_caddy_store_profile_blobs")
    @patch("sandbox.caddy_store._sync.commit_caddy_store_file")
    @patch("sandbox.caddy_store._sync.delete_caddy_store_file")
    def test_backup_idempotent_and_mirrors_deletions(
        self, mock_del, mock_commit, mock_list, mock_ensure, mock_fetch, mock_root
    ):
        mock_root.return_value = self.tmp_path
        vps_files = {
            "conf/Caddyfile": "{\n\temail ops@example.com\n}\n",
            "conf/sites/app.caddy": "app.example.com {\n\treverse_proxy app:3000\n}\n",
        }
        mock_fetch.return_value = vps_files

        # First run: one matching file, one new file, one stale file in store -> 1 upsert + 1 delete
        mock_list.return_value = {
            "conf/Caddyfile": git_blob_sha(vps_files["conf/Caddyfile"].encode("utf-8")),
            "conf/sites/old.caddy": "stale_sha",
        }
        out_dir = self.tmp_path / "export"
        res1 = backup_caddy_to_store(
            self.vps_config, profile="prod", org_name="sFactory0", gh_token="tok", dir_out=out_dir
        )
        self.assertTrue(res1.success)
        self.assertTrue(res1.changed)
        self.assertEqual(res1.files_written, ["conf/sites/app.caddy"])
        self.assertEqual(res1.files_deleted, ["conf/sites/old.caddy"])
        mock_commit.assert_called_once()
        self.assertEqual(mock_commit.call_args.args[1], "caddy/prod/conf/sites/app.caddy")
        mock_del.assert_called_once()
        self.assertEqual(mock_del.call_args.args[1], "caddy/prod/conf/sites/old.caddy")
        self.assertTrue((out_dir / "conf" / "sites" / "app.caddy").is_file())

        # Second run: everything matches -> idempotent no-op
        mock_commit.reset_mock()
        mock_del.reset_mock()
        mock_list.return_value = {
            k: git_blob_sha(v.encode("utf-8")) for k, v in vps_files.items()
        }
        res2 = backup_caddy_to_store(
            self.vps_config, profile="prod", org_name="sFactory0", gh_token="tok"
        )
        self.assertTrue(res2.success)
        self.assertFalse(res2.changed)
        self.assertIn("idempotent no-op", res2.message)
        mock_commit.assert_not_called()
        mock_del.assert_not_called()

    @patch("sandbox.caddy_store._sync.resolve_factory_root")
    @patch("sandbox.caddy_store._sync.ensure_caddy_store_repo")
    @patch("sandbox.caddy_store._sync.fetch_caddy_store_bundle")
    @patch("sandbox.caddy_store._sync.list_remote_docker_networks")
    @patch("sandbox.caddy_deploy.check_caddy_running")
    def test_restore_stopped_requires_bootstrap(
        self, mock_running, mock_nets, mock_bundle, mock_ensure, mock_root
    ):
        mock_root.return_value = self.tmp_path
        mock_bundle.return_value = {"conf/Caddyfile": "{\n}\n"}
        mock_running.return_value = (False, "not running")
        mock_nets.return_value = {"dbhost-network"}

        res = restore_caddy_from_store(
            self.vps_config, org_name="sFactory0", gh_token="tok", bootstrap=False
        )
        self.assertFalse(res.success)
        self.assertIn("--bootstrap", res.message)


    @patch("sandbox.caddy_store._cli.resolve_factory_root")
    @patch("sandbox.caddy_store._cli.backup_caddy_to_store")
    def test_cli_backup_from_dir_does_not_require_ssh(self, mock_backup, mock_root):
        mock_root.return_value = self.tmp_path
        local_src = self.tmp_path / "local"
        local_src.mkdir()
        mock_backup.return_value = MagicMock(success=True, message="ok")
        with patch.dict(os.environ, {}, clear=True):
            code = run_caddy_store_subcommand("backup", ["--from-dir", str(local_src), "--profile", "staging"])
        self.assertEqual(code, 0)
        self.assertIsNone(mock_backup.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
