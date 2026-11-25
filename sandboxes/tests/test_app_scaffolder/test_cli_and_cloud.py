"""Tests for create-app CLI, modal-sandbox alias, cloud wiring, and sandbox staging."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from sandbox.app_scaffolder import CloudWiringOptions, ensure_github_repo_and_push, wire_cloud_resources
from sandbox.core import LaunchResponse
from sandbox.db_host import DatabaseConnectionInfo
from sandbox.s3_host import S3BucketInfo
from scripts.create_app import create_parser, _resolve_options, main as create_app_main
from shared.image import stage_app_template_into_image


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


class TestCreateAppCliAndCloud(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)
        self.factory_root = _repo_root()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_app_help_and_modal_sandbox_alias(self):
        res_app = subprocess.run(
            [sys.executable, str(self.factory_root / "sandboxes" / "scripts" / "create_app.py"), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(res_app.returncode, 0)
        self.assertIn("--provision-db", res_app.stdout)
        self.assertIn("--cloud", res_app.stdout)

        res_alias = subprocess.run(
            [sys.executable, str(self.factory_root / "sandboxes" / "sandbox" / "main.py"), "create-app", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(res_alias.returncode, 0)
        self.assertIn("--provision-db", res_alias.stdout)
        self.assertIn("--deploy", res_alias.stdout)

    def test_deploy_flag_wires_hosted_app_deploy(self):
        parser = create_parser()
        raw = ["my-live-app", "--deploy", "--subdomain", "preview", "--base-domain", "sf.mahesh0.dev", "--skip-migrate"]
        args = parser.parse_args(raw)
        with patch("sys.stdin.isatty", return_value=False):
            _, cloud = _resolve_options(args, raw)
        self.assertTrue(cloud.deploy)
        self.assertEqual(cloud.subdomain, "preview")
        self.assertEqual(cloud.base_domain, "sf.mahesh0.dev")
        self.assertTrue(cloud.skip_migrate)

        project_dir = self.tmp_path / "my-live-app"
        project_dir.mkdir()
        (project_dir / ".env").write_text("NODE_ENV=development\n", encoding="utf-8")
        mock_deploy = MagicMock(return_value=MagicMock(url="https://preview.sf.mahesh0.dev", remote_dir="/root/my-live-app"))
        with patch.dict("os.environ", {"GH_ORG_NAME": "sFactory0"}, clear=False):
            res = wire_cloud_resources(
                "my-live-app",
                project_dir,
                cloud,
                repo_root=self.tmp_path,
                deploy_fn=mock_deploy,
            )
        self.assertEqual(res.deploy_result.url, "https://preview.sf.mahesh0.dev")
        mock_deploy.assert_called_once()

    def test_cloud_shorthand_resolves_db_github_vault_launch_and_keeps_s3_opt_in(self):
        parser = create_parser()
        raw = ["my-cloud-app", "--cloud", "--mobile-app"]
        args = parser.parse_args(raw)
        with patch("sys.stdin.isatty", return_value=False):
            req, cloud = _resolve_options(args, raw)
        self.assertTrue(req.mobile_app)
        self.assertTrue(req.db)
        self.assertTrue(cloud.github)
        self.assertTrue(cloud.provision_db)
        self.assertFalse(cloud.provision_s3)
        self.assertTrue(cloud.push_vault)
        self.assertTrue(cloud.launch)
        self.assertTrue(cloud.mobile_app)

        raw_no_db = ["my-cloud-app", "--cloud", "--no-db", "--provision-s3"]
        args_no_db = parser.parse_args(raw_no_db)
        with patch("sys.stdin.isatty", return_value=False):
            req2, cloud2 = _resolve_options(args_no_db, raw_no_db)
        self.assertFalse(req2.db)
        self.assertFalse(cloud2.provision_db)
        self.assertTrue(cloud2.provision_s3)

    def test_launch_without_github_or_repo_name_rejected(self):
        with patch("sys.stdin.isatty", return_value=False):
            with self.assertRaises(SystemExit) as ctx:
                create_app_main([str(self.tmp_path / "x"), "--launch", "--no-install", "--no-git"])
            self.assertNotEqual(ctx.exception.code, 0)

    def test_ensure_github_repo_and_push_creates_repo_and_uses_clean_origin(self):
        calls = []

        def fake_api(method, path, token, payload):
            calls.append((method, path, payload))
            if method == "GET":
                return 404, {"message": "Not Found"}
            return 201, {"full_name": "sFactory0/demo-app", "clone_url": "https://github.com/sFactory0/demo-app.git"}

        pushed = []

        def fake_push(project_dir, remote_url, token):
            pushed.append((project_dir, remote_url, token))

        full_name = ensure_github_repo_and_push(
            self.tmp_path,
            "sFactory0",
            "demo-app",
            public=False,
            gh_token="ghp_secret_tok",
            api_fn=fake_api,
            push_fn=fake_push,
        )
        self.assertEqual(full_name, "sFactory0/demo-app")
        self.assertEqual(calls[1], ("POST", "/orgs/sFactory0/repos", {"name": "demo-app", "private": True, "auto_init": False}))
        self.assertEqual(pushed[0][1], "https://github.com/sFactory0/demo-app.git")

    def test_wire_cloud_resources_orchestrates_db_s3_vault_and_sandbox_launch(self):
        project_dir = self.tmp_path / "my-saas"
        project_dir.mkdir()
        (project_dir / ".env").write_text("NODE_ENV=development\n", encoding="utf-8")

        db_info = DatabaseConnectionInfo(
            name="my_saas",
            username="u1",
            password="p1",
            host="rp.example.com",
            port=54320,
            connection_string="postgresql://u1:p1@rp.example.com:54320/my_saas?sslmode=verify-full&sslrootcert=/tmp/ca.crt",
            ca_cert_path=Path("/tmp/ca.crt"),
            project_name="my-saas",
            project_id="proj-1",
            already_existed=False,
        )
        s3_info = S3BucketInfo(
            id="b1",
            bucket_name="my-saas",
            project_name="my-saas",
            project_id="proj-1",
            access_key_id="ak1",
            secret_access_key="sk1",
            endpoint="https://s3.example.com",
            region="us-east-1",
            already_existed=False,
            s3_uri="s3://my-saas",
            formatted_env="",
            formatted_aws_cli="",
            formatted_node_sdk="",
            formatted_boto3="",
        )
        launch_resp = LaunchResponse(sandbox_id="sb-1", app_name="my-saas", sandbox_name="my-saas-1234", t3_pair_url="https://t3.example")
        mock_vault = MagicMock(return_value=MagicMock(success=True))
        mock_launch = MagicMock(return_value=(MagicMock(), launch_resp))
        mock_gh = MagicMock(return_value="sFactory0/my-saas")

        with patch.dict("os.environ", {"GH_ORG_NAME": "sFactory0", "GH_TOKEN": "ghp_tok"}, clear=False):
            res = wire_cloud_resources(
                "my-saas",
                project_dir,
                CloudWiringOptions(
                    github=True,
                    provision_db=True,
                    provision_s3=True,
                    push_vault=True,
                    launch=True,
                    mobile_app=True,
                ),
                repo_root=self.tmp_path,
                github_fn=mock_gh,
                create_db_fn=MagicMock(return_value=db_info),
                create_s3_fn=MagicMock(return_value=s3_info),
                push_vault_fn=mock_vault,
                launch_fn=mock_launch,
            )

        self.assertEqual(res.github_repo, "sFactory0/my-saas")
        self.assertTrue(res.vault_pushed)
        self.assertEqual(res.launch_response.sandbox_id, "sb-1")

        env_content = (project_dir / ".env").read_text(encoding="utf-8")
        self.assertIn("DATABASE_URL=", env_content)
        self.assertIn("AWS_ACCESS_KEY_ID=", env_content)
        self.assertIn("S3_BUCKET_NAME=", env_content)

        mock_vault.assert_called_once_with(
            repo_dir=project_dir,
            env_file=project_dir / ".env",
            repo_name="my-saas",
            org_name="sFactory0",
            gh_token="ghp_tok",
        )
        launch_req = mock_launch.call_args.args[0]
        self.assertEqual(launch_req.repo, "sFactory0/my-saas")
        self.assertTrue(launch_req.t3)
        self.assertTrue(launch_req.react_native)

    def test_stage_app_template_into_image_stages_blueprint_and_filtered_skills(self):
        mock_img = MagicMock()
        mock_img.add_local_dir.return_value = mock_img
        mock_img.add_local_file.return_value = mock_img

        out = stage_app_template_into_image(
            mock_img,
            template_dir=self.factory_root / "app-template",
            factory_root=self.factory_root,
        )
        self.assertIs(out, mock_img)
        remote_targets = [call.args[1] for call in mock_img.add_local_dir.call_args_list]
        self.assertIn("/opt/app-template", remote_targets)
        self.assertIn("/opt/app-template/_skills_source/.agents/skills", remote_targets)
        self.assertIn("/opt/app-template/_skills_source/docs/agents", remote_targets)

        skills_call = next(
            c for c in mock_img.add_local_dir.call_args_list
            if c.args[1] == "/opt/app-template/_skills_source/.agents/skills"
        )
        ignore_fn = skills_call.kwargs["ignore"]
        self.assertFalse(ignore_fn(Path("tdd/SKILL.md")))
        self.assertTrue(ignore_fn(Path("modal/SKILL.md")))
        self.assertTrue(ignore_fn(Path("close-modal-sandboxes/SKILL.md")))

    def test_startup_sh_caches_resource_plane_ca_and_includes_create_app_precedence(self):
        startup_sh = self.factory_root / "sandboxes" / "shared" / "startup.sh"
        content = startup_sh.read_text(encoding="utf-8")
        self.assertIn("create-app", content)
        self.assertIn("/root/.config/resource-plane/ca.crt", content)
        self.assertIn("/api/ca.crt", content)
