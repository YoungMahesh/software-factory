"""Unit and integration tests for create-db CLI and db-host client module."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import httpx

from sandbox.db_host import (
    DEFAULT_PORT,
    DatabaseConnectionInfo,
    DbHostClient,
    DbHostConfig,
    call_mcp_tool,
    create_database_connection,
    download_ca_cert,
    ensure_project,
    get_or_download_ca_cert,
    normalize_base_url,
    resolve_db_host_config,
    resolve_project_name,
    update_env_file,
)
from scripts.create_db import create_parser, format_text_output, main


class TestDbHostClient(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_normalize_base_url(self):
        self.assertEqual(normalize_base_url("db-host.example.com"), "https://db-host.example.com")
        self.assertEqual(normalize_base_url("https://db-host.example.com/"), "https://db-host.example.com")
        self.assertEqual(normalize_base_url("http://localhost:3000"), "http://localhost:3000")
        with self.assertRaises(ValueError):
            normalize_base_url("")

    def test_resolve_db_host_config_from_args(self):
        config = resolve_db_host_config(domain="test.domain.com", token="tok123")
        self.assertEqual(config.domain, "test.domain.com")
        self.assertEqual(config.admin_token, "tok123")
        self.assertEqual(config.base_url, "https://test.domain.com")

    def test_resolve_db_host_config_from_env(self):
        with patch.dict("os.environ", {"DB_HOST_DOMAIN": "env.domain.com", "DB_HOST_ADMIN_TOKEN": "envtok"}, clear=True):
            config = resolve_db_host_config()
            self.assertEqual(config.domain, "env.domain.com")
            self.assertEqual(config.admin_token, "envtok")

    def test_resolve_db_host_config_missing_domain(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                resolve_db_host_config(token="tok")
            self.assertIn("Missing db-host domain", str(ctx.exception))

    def test_resolve_db_host_config_missing_token(self):
        with patch.dict("os.environ", {"DB_HOST_DOMAIN": "test.com"}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                resolve_db_host_config()
            self.assertIn("Missing db-host admin token", str(ctx.exception))

    def test_download_ca_cert_success(self):
        ca_file = self.tmp_path / "test_ca.crt"
        dummy_pem = "-----BEGIN CERTIFICATE-----\nMIIB...\n-----END CERTIFICATE-----\n"

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=dummy_pem)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        with patch("httpx.Client", return_value=client):
            res_path = download_ca_cert("https://db-host.test", dest_path=ca_file)
            self.assertEqual(res_path, ca_file.resolve())
            self.assertTrue(ca_file.exists())
            self.assertEqual(ca_file.read_text(), dummy_pem)

    def test_download_ca_cert_invalid_content(self):
        ca_file = self.tmp_path / "invalid_ca.crt"

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="Not a certificate")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        with patch("httpx.Client", return_value=client):
            with self.assertRaises(ValueError):
                download_ca_cert("https://db-host.test", dest_path=ca_file)

    def test_get_or_download_ca_cert_uses_cache(self):
        ca_file = self.tmp_path / "cached_ca.crt"
        ca_file.write_text("-----BEGIN CERTIFICATE-----\nCA\n-----END CERTIFICATE-----\n")
        with patch("sandbox.db_host.download_ca_cert") as mock_dl:
            res = get_or_download_ca_cert("https://db-host.test", dest_path=ca_file)
            self.assertEqual(res, ca_file.resolve())
            mock_dl.assert_not_called()

    def test_call_mcp_tool_success(self):
        expected_result = {"id": "proj-1", "name": "my-project"}

        def handler(request: httpx.Request) -> httpx.Response:
            data = json.loads(request.content.decode())
            self.assertEqual(data["method"], "tools/call")
            self.assertEqual(data["params"]["name"], "create_project")
            self.assertEqual(request.headers.get("authorization"), "Bearer secret-token")
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(expected_result)}]
                    },
                },
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        res = call_mcp_tool(
            base_url="https://db-host.test",
            admin_token="secret-token",
            tool_name="create_project",
            arguments={"name": "my-project"},
            client=client,
        )
        self.assertEqual(res, expected_result)

    def test_call_mcp_tool_jsonrpc_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "error": {"message": "Unauthorized"}})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        with self.assertRaises(RuntimeError) as ctx:
            call_mcp_tool("https://db-host.test", "bad-token", "list_projects", {}, client=client)
        self.assertIn("Unauthorized", str(ctx.exception))

    def test_ensure_project_finds_existing(self):
        existing_projects = [{"id": "uuid-123", "name": "demo-proj", "slug": "demo-proj"}]

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {"content": [{"type": "text", "text": json.dumps(existing_projects)}]},
                },
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        proj = ensure_project("https://db-host.test", "tok", "demo-proj", client=client)
        self.assertEqual(proj["id"], "uuid-123")

    def test_ensure_project_creates_when_missing(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            data = json.loads(request.content.decode())
            tool = data["params"]["name"]
            calls.append(tool)
            if tool == "list_projects":
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "[]"}]}})
            if tool == "create_project":
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": json.dumps({"id": "new-p1", "name": "new-proj"})}]}})
            return httpx.Response(500)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        proj = ensure_project("https://db-host.test", "tok", "new-proj", client=client)
        self.assertEqual(proj["id"], "new-p1")
        self.assertEqual(calls, ["list_projects", "create_project"])

    def test_update_env_file(self):
        env_file = self.tmp_path / ".env"
        env_file.write_text("FOO=bar\nDATABASE_URL=old_url\nBAZ=qux\n")
        update_env_file(env_file, "DATABASE_URL", "postgresql://new_url")
        content = env_file.read_text()
        self.assertIn('DATABASE_URL="postgresql://new_url"', content)
        self.assertIn("FOO=bar", content)
        self.assertIn("BAZ=qux", content)

        # Appending new variable
        update_env_file(env_file, "NEW_VAR", "hello")
        self.assertIn('NEW_VAR="hello"', env_file.read_text())


class TestCreateDbCli(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("sandbox.db_host.get_or_download_ca_cert")
    @patch("sandbox.db_host.call_mcp_tool")
    def test_create_database_connection_flow(self, mock_mcp, mock_ca):
        mock_ca.return_value = Path("/tmp/ca.crt")

        def side_effect(base_url, admin_token, tool_name, arguments, **kwargs):
            if tool_name == "list_projects":
                return [{"id": "p-1", "name": "test-repo", "slug": "test-repo"}]
            if tool_name == "create_database":
                return {"id": "db-1", "name": "my_db", "username": "db_user"}
            if tool_name == "get_database_credentials":
                return {
                    "id": "db-1",
                    "name": "my_db",
                    "username": "db_user",
                    "password": "secretpassword",
                    "host": "db-host.example.com",
                    "port": 54320,
                    "connectionString": "postgresql://db_user:secretpassword@db-host.example.com:54320/my_db?sslmode=verify-full&sslrootcert=ca.crt",
                }
            return {}

        mock_mcp.side_effect = side_effect

        info = create_database_connection(
            database_name="my_db",
            project_name="test-repo",
            domain="db-host.example.com",
            token="admin-token",
        )

        self.assertEqual(info.name, "my_db")
        self.assertEqual(info.username, "db_user")
        self.assertEqual(info.port, 54320)
        self.assertFalse(info.already_existed)
        self.assertIn("sslrootcert=/tmp/ca.crt", info.connection_string)

    @patch("sandbox.db_host.get_or_download_ca_cert")
    @patch("sandbox.db_host.call_mcp_tool")
    def test_create_database_connection_idempotent_reused(self, mock_mcp, mock_ca):
        mock_ca.return_value = Path("/tmp/ca.crt")

        def side_effect(base_url, admin_token, tool_name, arguments, **kwargs):
            if tool_name == "list_projects":
                return [{"id": "p-1", "name": "test-repo", "slug": "test-repo"}]
            if tool_name == "create_database":
                raise RuntimeError("MCP tool 'create_database' returned error: Database with name \"my_db\" already exists")
            if tool_name == "get_database_credentials":
                return {
                    "id": "db-existing",
                    "name": "my_db",
                    "username": "existing_user",
                    "password": "existingpassword",
                    "host": "db-host.example.com",
                    "port": 54320,
                }
            return {}

        mock_mcp.side_effect = side_effect

        info = create_database_connection(
            database_name="my_db",
            project_name="test-repo",
            domain="db-host.example.com",
            token="admin-token",
            if_not_exists=True,
        )

        self.assertTrue(info.already_existed)
        self.assertEqual(info.username, "existing_user")

    @patch("scripts.create_db.create_database_connection")
    def test_cli_main_json_and_write_env(self, mock_create):
        ca_path = self.tmp_path / "ca.crt"
        env_file = self.tmp_path / ".env"

        mock_create.return_value = DatabaseConnectionInfo(
            name="demo_db",
            username="u_demo",
            password="pwd",
            host="db-host.test",
            port=DEFAULT_PORT,
            connection_string="postgresql://u_demo:pwd@db-host.test:54320/demo_db?sslmode=verify-full&sslrootcert=/tmp/ca.crt",
            ca_cert_path=ca_path,
            project_name="demo-proj",
            project_id="proj-123",
            already_existed=False,
        )

        exit_code = main([
            "demo_db",
            "--domain", "db-host.test",
            "--token", "test-token",
            "--write-env",
            "--env-file", str(env_file),
            "--json",
        ])

        self.assertEqual(exit_code, 0)
        self.assertTrue(env_file.exists())
        self.assertIn('DATABASE_URL="postgresql://u_demo:pwd@db-host.test:54320/demo_db', env_file.read_text())

    @patch("scripts.create_db.create_database_connection")
    def test_cli_main_write_env_and_push_vault_passes_env_flag(self, mock_create):
        ca_path = self.tmp_path / "ca.crt"
        env_file = self.tmp_path / "apps" / "web" / ".env"

        mock_create.return_value = DatabaseConnectionInfo(
            name="demo_db",
            username="u_demo",
            password="pwd",
            host="db-host.test",
            port=DEFAULT_PORT,
            connection_string="postgresql://u_demo:pwd@db-host.test:54320/demo_db",
            ca_cert_path=ca_path,
            project_name="demo-proj",
            project_id="proj-123",
            already_existed=False,
        )

        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value = MagicMock(returncode=0)
            exit_code = main([
                "demo_db",
                "--domain", "db-host.test",
                "--token", "test-token",
                "--write-env",
                "--env-file", str(env_file),
                "--push-vault",
                "--json",
            ])

        self.assertEqual(exit_code, 0)
        mock_sub.assert_called_once_with(["push-repo-env", "-e", str(env_file)], check=False)

    @patch("scripts.create_db.create_database_connection")
    def test_cli_main_quiet_flag(self, mock_create):
        mock_create.return_value = DatabaseConnectionInfo(
            name="demo_db",
            username="u_demo",
            password="pwd",
            host="db-host.test",
            port=DEFAULT_PORT,
            connection_string="postgresql://u_demo:pwd@db-host.test:54320/demo_db",
            ca_cert_path=Path("/tmp/ca.crt"),
            project_name="demo-proj",
            project_id="proj-123",
            already_existed=True,
        )

        with patch("sys.stdout") as mock_stdout:
            exit_code = main(["demo_db", "--domain", "db-host.test", "--token", "tok", "-q"])
            self.assertEqual(exit_code, 0)


class TestDbHostClientDirect(unittest.TestCase):
    def test_client_init_and_properties(self):
        client = DbHostClient.from_env(domain="test.host.internal", token="admintok123")
        self.assertEqual(client.domain, "test.host.internal")
        self.assertEqual(client.admin_token, "admintok123")
        self.assertEqual(client.base_url, "https://test.host.internal")

    @patch("sandbox.db_host_client.call_mcp_tool")
    def test_client_call_tool_and_ensure_project(self, mock_tool):
        mock_tool.return_value = {"id": "p-1", "name": "my-proj"}
        client = DbHostClient(domain="test.host.internal", token="tok")
        res = client.call_tool("list_projects", {})
        self.assertEqual(res["id"], "p-1")
        mock_tool.assert_called_once()

    def test_client_update_env_file(self):
        with tempfile.TemporaryDirectory() as td:
            env_file = Path(td) / ".env"
            client = DbHostClient(domain="test.host.internal", token="tok")
            client.update_env_file(env_file, "FOO", "BAR")
            self.assertIn('FOO="BAR"', env_file.read_text())

