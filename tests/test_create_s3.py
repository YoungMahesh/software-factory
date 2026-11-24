"""Unit and integration tests for create-s3 CLI and s3-host client module."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from sandbox.s3_host import (
    S3BucketInfo,
    create_s3_bucket,
    generate_boto3_snippet,
    validate_bucket_name,
    write_s3_env_vars,
)
from scripts.create_s3 import create_parser, format_text_output, main


class TestS3HostDomain(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_validate_bucket_name_valid(self):
        valid_names = [
            "my-bucket",
            "bucket-123",
            "abc",
            "123-bucket",
            "a" * 63,
        ]
        for name in valid_names:
            self.assertEqual(validate_bucket_name(name), name)

    def test_validate_bucket_name_invalid(self):
        invalid_names = [
            "",
            "   ",
            "ab",  # too short
            "a" * 64,  # too long
            "MyBucket",  # uppercase
            "my_bucket",  # underscore
            "-mybucket",  # starts with hyphen
            "mybucket-",  # ends with hyphen
            "my bucket",  # spaces
            "my.bucket",  # dots
        ]
        for name in invalid_names:
            with self.assertRaises(ValueError):
                validate_bucket_name(name)

    def test_generate_boto3_snippet(self):
        snippet = generate_boto3_snippet(
            endpoint="http://db-host.mahesh0.dev:8333",
            access_key_id="TEST_KEY",
            secret_access_key="TEST_SECRET",
            region="us-east-1",
            bucket_name="my-test-bucket",
        )
        self.assertIn("import boto3", snippet)
        self.assertIn("endpoint_url='http://db-host.mahesh0.dev:8333'", snippet)
        self.assertIn("aws_access_key_id='TEST_KEY'", snippet)
        self.assertIn("aws_secret_access_key='TEST_SECRET'", snippet)
        self.assertIn("region_name='us-east-1'", snippet)
        self.assertIn("Bucket='my-test-bucket'", snippet)

    def test_write_s3_env_vars(self):
        env_file = self.tmp_path / ".env"
        env_file.write_text("EXISTING=1\nAWS_ACCESS_KEY_ID=old\n")

        info = S3BucketInfo(
            id="storage-1",
            bucket_name="test-bucket",
            project_name="demo-proj",
            project_id="p-1",
            access_key_id="NEW_KEY",
            secret_access_key="NEW_SECRET",
            endpoint="http://db-host.mahesh0.dev:8333",
            region="us-east-1",
            already_existed=False,
            s3_uri="s3://test-bucket",
            formatted_env="",
            formatted_aws_cli="",
            formatted_node_sdk="",
            formatted_boto3="",
        )

        keys = write_s3_env_vars(env_file, info)
        self.assertIn("AWS_ACCESS_KEY_ID", keys)
        self.assertIn("AWS_SECRET_ACCESS_KEY", keys)
        self.assertIn("AWS_ENDPOINT_URL_S3", keys)
        self.assertIn("AWS_REGION", keys)
        self.assertIn("S3_BUCKET_NAME", keys)

        content = env_file.read_text()
        self.assertIn('AWS_ACCESS_KEY_ID="NEW_KEY"', content)
        self.assertIn('AWS_SECRET_ACCESS_KEY="NEW_SECRET"', content)
        self.assertIn('AWS_ENDPOINT_URL_S3="http://db-host.mahesh0.dev:8333"', content)
        self.assertIn('AWS_REGION="us-east-1"', content)
        self.assertIn('S3_BUCKET_NAME="test-bucket"', content)
        self.assertIn("EXISTING=1", content)

    def test_write_s3_env_vars_with_prefix(self):
        env_file = self.tmp_path / ".env"
        info = S3BucketInfo(
            id="storage-1",
            bucket_name="test-bucket",
            project_name="demo-proj",
            project_id="p-1",
            access_key_id="KEY",
            secret_access_key="SECRET",
            endpoint="http://db-host.mahesh0.dev:8333",
            region="us-east-1",
            already_existed=False,
            s3_uri="s3://test-bucket",
            formatted_env="",
            formatted_aws_cli="",
            formatted_node_sdk="",
            formatted_boto3="",
        )

        keys = write_s3_env_vars(env_file, info, prefix="APP_")
        self.assertIn("APP_AWS_ACCESS_KEY_ID", keys)
        self.assertIn("APP_S3_BUCKET_NAME", keys)

        content = env_file.read_text()
        self.assertIn('APP_AWS_ACCESS_KEY_ID="KEY"', content)
        self.assertIn('APP_S3_BUCKET_NAME="test-bucket"', content)

    @patch("sandbox.s3_host.call_mcp_tool")
    def test_create_s3_bucket_flow(self, mock_mcp):
        def side_effect(base_url, admin_token, tool_name, arguments, **kwargs):
            if tool_name == "list_projects":
                return [{"id": "p-1", "name": "my-repo", "slug": "my-repo"}]
            if tool_name == "create_object_storage":
                return {"id": "st-1", "bucketName": "my-bucket"}
            if tool_name == "get_storage_credentials":
                return {
                    "id": "st-1",
                    "bucketName": "my-bucket",
                    "accessKeyId": "AKIA123",
                    "secretAccessKey": "SECRET456",
                    "endpoint": "http://db-host.mahesh0.dev:8333",
                    "region": "us-east-1",
                    "formatted": {
                        "env": "AWS_ACCESS_KEY_ID=AKIA123\n",
                        "awsCli": "aws s3 ls ...",
                        "nodeSdk": "import { S3Client } ...",
                    },
                }
            return {}

        mock_mcp.side_effect = side_effect

        info = create_s3_bucket(
            bucket_name="my-bucket",
            project_name="my-repo",
            domain="db-host.mahesh0.dev",
            token="admin-token",
        )

        self.assertEqual(info.bucket_name, "my-bucket")
        self.assertEqual(info.project_id, "p-1")
        self.assertEqual(info.access_key_id, "AKIA123")
        self.assertEqual(info.secret_access_key, "SECRET456")
        self.assertEqual(info.endpoint, "http://db-host.mahesh0.dev:8333")
        self.assertEqual(info.s3_uri, "s3://my-bucket")
        self.assertFalse(info.already_existed)
        self.assertIn("s3 = boto3.client", info.formatted_boto3)

    @patch("sandbox.s3_host.call_mcp_tool")
    def test_create_s3_bucket_idempotent_reused(self, mock_mcp):
        def side_effect(base_url, admin_token, tool_name, arguments, **kwargs):
            if tool_name == "list_projects":
                return [{"id": "p-1", "name": "my-repo", "slug": "my-repo"}]
            if tool_name == "create_object_storage":
                raise RuntimeError("MCP tool 'create_object_storage' returned error: Bucket \"existing-bucket\" already exists")
            if tool_name == "get_storage_credentials":
                return {
                    "id": "st-existing",
                    "bucketName": "existing-bucket",
                    "accessKeyId": "AKIAEXISTING",
                    "secretAccessKey": "SECRETEXISTING",
                    "endpoint": "http://db-host.mahesh0.dev:8333",
                    "region": "us-east-1",
                    "formatted": {},
                }
            return {}

        mock_mcp.side_effect = side_effect

        info = create_s3_bucket(
            bucket_name="existing-bucket",
            project_name="my-repo",
            domain="db-host.mahesh0.dev",
            token="admin-token",
            if_not_exists=True,
        )

        self.assertEqual(info.bucket_name, "existing-bucket")
        self.assertTrue(info.already_existed)
        self.assertEqual(info.access_key_id, "AKIAEXISTING")

    @patch("sandbox.s3_host.call_mcp_tool")
    def test_create_s3_bucket_fail_if_exists(self, mock_mcp):
        def side_effect(base_url, admin_token, tool_name, arguments, **kwargs):
            if tool_name == "list_projects":
                return [{"id": "p-1", "name": "my-repo", "slug": "my-repo"}]
            if tool_name == "create_object_storage":
                raise RuntimeError("MCP tool 'create_object_storage' returned error: Bucket \"existing-bucket\" already exists")
            return {}

        mock_mcp.side_effect = side_effect

        with self.assertRaises(RuntimeError) as ctx:
            create_s3_bucket(
                bucket_name="existing-bucket",
                project_name="my-repo",
                domain="db-host.mahesh0.dev",
                token="admin-token",
                if_not_exists=False,
            )
        self.assertIn("already exists", str(ctx.exception))


class TestCreateS3Cli(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parser_configuration(self):
        parser = create_parser()
        args = parser.parse_args(["my-bucket", "--write-env", "--prefix", "PRE_"])
        self.assertEqual(args.name, "my-bucket")
        self.assertTrue(args.write_env)
        self.assertEqual(args.prefix, "PRE_")
        self.assertFalse(args.push_vault)
        self.assertFalse(args.json)
        self.assertFalse(args.quiet)

    def test_format_text_output(self):
        info = S3BucketInfo(
            id="st-1",
            bucket_name="demo-bucket",
            project_name="my-proj",
            project_id="p-1",
            access_key_id="KEY",
            secret_access_key="SECRET",
            endpoint="http://db-host.mahesh0.dev:8333",
            region="us-east-1",
            already_existed=False,
            s3_uri="s3://demo-bucket",
            formatted_env="",
            formatted_aws_cli="",
            formatted_node_sdk="",
            formatted_boto3="",
        )
        text = format_text_output(info, written_env=["AWS_ACCESS_KEY_ID"], env_path=Path(".env"))
        self.assertIn("Created new S3 bucket: demo-bucket", text)
        self.assertIn("s3://demo-bucket", text)
        self.assertIn("http://db-host.mahesh0.dev:8333", text)
        self.assertIn("Injected into .env", text)

        info.already_existed = True
        text_reused = format_text_output(info)
        self.assertIn("Reused existing S3 bucket", text_reused)

    @patch("scripts.create_s3.create_s3_bucket")
    def test_cli_main_success(self, mock_create):
        mock_info = S3BucketInfo(
            id="st-1",
            bucket_name="cli-bucket",
            project_name="cli-proj",
            project_id="p-1",
            access_key_id="KEY",
            secret_access_key="SECRET",
            endpoint="http://db-host.mahesh0.dev:8333",
            region="us-east-1",
            already_existed=False,
            s3_uri="s3://cli-bucket",
            formatted_env="",
            formatted_aws_cli="",
            formatted_node_sdk="",
            formatted_boto3="",
        )
        mock_create.return_value = mock_info

        with patch("sys.stdout") as mock_stdout:
            exit_code = main(["cli-bucket", "--domain", "test.dev", "--token", "tok"])
            self.assertEqual(exit_code, 0)

    @patch("scripts.create_s3.create_s3_bucket")
    def test_cli_main_quiet(self, mock_create):
        mock_info = S3BucketInfo(
            id="st-1",
            bucket_name="quiet-bucket",
            project_name="cli-proj",
            project_id="p-1",
            access_key_id="KEY",
            secret_access_key="SECRET",
            endpoint="http://db-host.mahesh0.dev:8333",
            region="us-east-1",
            already_existed=False,
            s3_uri="s3://quiet-bucket",
            formatted_env="",
            formatted_aws_cli="",
            formatted_node_sdk="",
            formatted_boto3="",
        )
        mock_create.return_value = mock_info

        with patch("sys.stdout.write") as mock_write:
            exit_code = main(["quiet-bucket", "-q", "--domain", "test.dev", "--token", "tok"])
            self.assertEqual(exit_code, 0)
            written = "".join(call[0][0] for call in mock_write.call_args_list)
            self.assertEqual(written.strip(), "s3://quiet-bucket")

    @patch("scripts.create_s3.create_s3_bucket")
    def test_cli_main_json(self, mock_create):
        mock_info = S3BucketInfo(
            id="st-1",
            bucket_name="json-bucket",
            project_name="cli-proj",
            project_id="p-1",
            access_key_id="KEY",
            secret_access_key="SECRET",
            endpoint="http://db-host.mahesh0.dev:8333",
            region="us-east-1",
            already_existed=False,
            s3_uri="s3://json-bucket",
            formatted_env="",
            formatted_aws_cli="",
            formatted_node_sdk="",
            formatted_boto3="",
        )
        mock_create.return_value = mock_info

        with patch("sys.stdout.write") as mock_write:
            exit_code = main(["json-bucket", "--json", "--domain", "test.dev", "--token", "tok"])
            self.assertEqual(exit_code, 0)
            written = "".join(call[0][0] for call in mock_write.call_args_list)
            data = json.loads(written)
            self.assertEqual(data["bucket_name"], "json-bucket")
            self.assertEqual(data["s3_uri"], "s3://json-bucket")

    @patch("scripts.create_s3.create_s3_bucket")
    def test_cli_main_write_env_and_push_vault(self, mock_create):
        mock_info = S3BucketInfo(
            id="st-1",
            bucket_name="vault-bucket",
            project_name="cli-proj",
            project_id="p-1",
            access_key_id="KEY",
            secret_access_key="SECRET",
            endpoint="http://db-host.mahesh0.dev:8333",
            region="us-east-1",
            already_existed=False,
            s3_uri="s3://vault-bucket",
            formatted_env="",
            formatted_aws_cli="",
            formatted_node_sdk="",
            formatted_boto3="",
        )
        mock_create.return_value = mock_info

        env_file = self.tmp_path / ".env"

        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value = MagicMock(returncode=0)
            exit_code = main([
                "vault-bucket",
                "--write-env",
                "--env-file", str(env_file),
                "--push-vault",
                "--domain", "test.dev",
                "--token", "tok",
            ])
            self.assertEqual(exit_code, 0)
            self.assertTrue(env_file.exists())
            self.assertIn('AWS_ACCESS_KEY_ID="KEY"', env_file.read_text())
            mock_sub.assert_called_once()

    def test_cli_main_invalid_name_error(self):
        with patch("sys.stderr.write"):
            exit_code = main(["INVALID_NAME", "--domain", "test.dev", "--token", "tok"])
            self.assertEqual(exit_code, 1)
