"""Subsystem tests for In-Studio File Explorer & Code Viewer backend endpoints."""

import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
import httpx

from fastapi.testclient import TestClient

from factory.ui.app import create_app
from factory.ui.registry import PreviewRegistry, PreviewState, PreviewStatus


class TestFilesEndpoints(unittest.TestCase):
    def setUp(self):
        self.preview_reg = PreviewRegistry()
        self.app = create_app(preview_reg=self.preview_reg)
        self.client = TestClient(self.app)
        self.auth_headers = {"Authorization": "Basic YWRtaW46YWRtaW4="}

    @patch("factory.ui.github._client.get_test_org_token")
    @patch("factory.ui.routes.files.httpx.Client")
    def test_get_tree_fallback_to_github_with_server_filtering(self, mock_client_cls, mock_token):
        """When container is not running, falls back to GitHub Git Database API and filters build artifacts."""
        mock_token.return_value = "ghp_mocktoken123"

        # Mock GitHub git database tree API response
        mock_tree_payload = {
            "sha": "tree-sha-123",
            "tree": [
                {"path": "package.json", "mode": "100644", "type": "blob", "size": 450},
                {"path": "src", "mode": "040000", "type": "tree"},
                {"path": "src/App.tsx", "mode": "100644", "type": "blob", "size": 1200},
                {"path": "node_modules", "mode": "040000", "type": "tree"},
                {"path": "node_modules/foo/index.js", "mode": "100644", "type": "blob", "size": 300},
                {"path": ".git", "mode": "040000", "type": "tree"},
                {"path": ".git/config", "mode": "100644", "type": "blob", "size": 200},
                {"path": ".venv/bin/python", "mode": "100755", "type": "blob", "size": 1000},
                {"path": ".next/static/bundle.js", "mode": "100644", "type": "blob", "size": 5000},
                {"path": "dist/bundle.js", "mode": "100644", "type": "blob", "size": 4000},
                {"path": "__pycache__/module.cpython-312.pyc", "mode": "100644", "type": "blob", "size": 800},
            ],
            "truncated": False,
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_tree_payload
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_resp

        res = self.client.get(
            "/api/repos/test1/tree?branch=main",
            headers=self.auth_headers,
        )

        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["repo"], "test1")
        self.assertEqual(data["branch"], "main")
        self.assertEqual(data["source"], "github")

        paths = [item["path"] for item in data["tree"]]
        self.assertIn("package.json", paths)
        self.assertIn("src", paths)
        self.assertIn("src/App.tsx", paths)

        # Server-side ignore filtering must exclude build/dependency artifacts
        self.assertNotIn("node_modules", paths)
        self.assertNotIn("node_modules/foo/index.js", paths)
        self.assertNotIn(".git", paths)
        self.assertNotIn(".git/config", paths)
        self.assertNotIn(".venv/bin/python", paths)
        self.assertNotIn(".next/static/bundle.js", paths)
        self.assertNotIn("dist/bundle.js", paths)
        self.assertNotIn("__pycache__/module.cpython-312.pyc", paths)

    def test_get_tree_live_sandbox(self):
        """When container is running, executes in-container discovery to surface uncommitted agent files."""
        mock_sandbox = MagicMock()
        mock_proc = MagicMock()
        # Simulated JSON tree output from sandbox execution
        sandbox_files = [
            {"path": "package.json", "type": "blob", "size": 450},
            {"path": "src/App.tsx", "type": "blob", "size": 1200},
            {"path": "src/UncommittedFeature.tsx", "type": "blob", "size": 850},
        ]
        mock_proc.stdout = [json.dumps(sandbox_files).encode("utf-8")]
        mock_proc.stderr = []
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_sandbox.exec.return_value = mock_proc

        # Register running preview state with active sandbox
        preview = PreviewState(
            repo="test1",
            branch="factory/feature-x",
            status=PreviewStatus.SERVING,
        )
        preview.sandbox = mock_sandbox
        self.preview_reg._previews["test1"] = preview

        res = self.client.get(
            "/api/repos/test1/tree",
            headers=self.auth_headers,
        )

        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["repo"], "test1")
        self.assertEqual(data["branch"], "factory/feature-x")
        self.assertEqual(data["source"], "sandbox")

        paths = [item["path"] for item in data["tree"]]
        self.assertIn("src/UncommittedFeature.tsx", paths)
        mock_sandbox.exec.assert_called_once()

    @patch("factory.ui.github._client.get_test_org_token")
    @patch("factory.ui.routes.files.httpx.Client")
    def test_get_file_fallback_to_github_text(self, mock_client_cls, mock_token):
        """When container is stopped, retrieves file content from GitHub Git Database API."""
        mock_token.return_value = "ghp_mocktoken123"

        # Mock GitHub contents API response (or blob)
        import base64
        code_content = "import React from 'react';\nexport const App = () => <div>Hello</div>;"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "name": "App.tsx",
            "path": "src/App.tsx",
            "size": len(code_content.encode("utf-8")),
            "encoding": "base64",
            "content": base64.b64encode(code_content.encode("utf-8")).decode("utf-8"),
        }
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_resp

        res = self.client.get(
            "/api/repos/test1/files?path=src/App.tsx&branch=main",
            headers=self.auth_headers,
        )

        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["path"], "src/App.tsx")
        self.assertEqual(data["content"], code_content)
        self.assertEqual(data["is_binary"], False)
        self.assertEqual(data["is_truncated"], False)
        self.assertEqual(data["language"], "typescript")
        self.assertEqual(data["source"], "github")

    def test_get_file_live_sandbox_content(self):
        """When container is running, reads live file content directly from sandbox."""
        mock_sandbox = MagicMock()
        mock_proc = MagicMock()
        live_content = "const greeting = 'Live from sandbox';"
        container_payload = {
            "exists": True,
            "size": len(live_content.encode("utf-8")),
            "is_binary": False,
            "content": live_content,
        }
        mock_proc.stdout = [json.dumps(container_payload).encode("utf-8")]
        mock_proc.stderr = []
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_sandbox.exec.return_value = mock_proc

        preview = PreviewState(
            repo="test1",
            branch="factory/feature-x",
            status=PreviewStatus.SERVING,
        )
        preview.sandbox = mock_sandbox
        self.preview_reg._previews["test1"] = preview

        res = self.client.get(
            "/api/repos/test1/files?path=src/Greeting.ts",
            headers=self.auth_headers,
        )

        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["path"], "src/Greeting.ts")
        self.assertEqual(data["content"], live_content)
        self.assertEqual(data["source"], "sandbox")
        self.assertEqual(data["language"], "typescript")
        self.assertFalse(data["is_binary"])
        self.assertFalse(data["is_truncated"])

    def test_get_file_large_payload_limit_500kb(self):
        """Files exceeding 500KB cap render informational placeholder and content is null."""
        mock_sandbox = MagicMock()
        mock_proc = MagicMock()
        container_payload = {
            "exists": True,
            "size": 600 * 1024,  # 600KB > 500KB limit
            "is_binary": False,
            "content": None,
        }
        mock_proc.stdout = [json.dumps(container_payload).encode("utf-8")]
        mock_proc.stderr = []
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_sandbox.exec.return_value = mock_proc

        preview = PreviewState(
            repo="test1",
            branch="main",
            status=PreviewStatus.SERVING,
        )
        preview.sandbox = mock_sandbox
        self.preview_reg._previews["test1"] = preview

        res = self.client.get(
            "/api/repos/test1/files?path=large_dataset.json",
            headers=self.auth_headers,
        )

        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertTrue(data["is_truncated"])
        self.assertIsNone(data["content"])
        self.assertIn("500KB", data["message"])

    def test_get_file_binary_detection(self):
        """Binary files render safe informational placeholder without raw text."""
        mock_sandbox = MagicMock()
        mock_proc = MagicMock()
        container_payload = {
            "exists": True,
            "size": 4096,
            "is_binary": True,
            "content": None,
        }
        mock_proc.stdout = [json.dumps(container_payload).encode("utf-8")]
        mock_proc.stderr = []
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_sandbox.exec.return_value = mock_proc

        preview = PreviewState(
            repo="test1",
            branch="main",
            status=PreviewStatus.SERVING,
        )
        preview.sandbox = mock_sandbox
        self.preview_reg._previews["test1"] = preview

        res = self.client.get(
            "/api/repos/test1/files?path=assets/logo.png",
            headers=self.auth_headers,
        )

        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertTrue(data["is_binary"])
        self.assertIsNone(data["content"])
        self.assertIn("Binary file", data["message"])

    def test_path_traversal_and_ignored_dir_protection(self):
        """Rejects traversal attempts and restricted ignored directories."""
        # Traversal attempt
        res = self.client.get(
            "/api/repos/test1/files?path=../../etc/passwd",
            headers=self.auth_headers,
        )
        self.assertEqual(res.status_code, 400)

        # Restricted directory
        res2 = self.client.get(
            "/api/repos/test1/files?path=node_modules/express/index.js",
            headers=self.auth_headers,
        )
        self.assertEqual(res2.status_code, 403)

    def test_get_raw_file_download(self):
        """Verifies raw download endpoint returns attachment header and file bytes."""
        mock_sandbox = MagicMock()
        mock_proc = MagicMock()
        import base64
        test_bytes = b"RAW_BINARY_CONTENT_12345"
        mock_proc.stdout = [base64.b64encode(test_bytes)]
        mock_proc.stderr = []
        mock_proc.wait.return_value = 0
        mock_sandbox.exec.return_value = mock_proc

        preview = PreviewState(
            repo="test1",
            branch="main",
            status=PreviewStatus.SERVING,
        )
        preview.sandbox = mock_sandbox
        self.preview_reg._previews["test1"] = preview

        res = self.client.get(
            "/api/repos/test1/raw?path=assets/binary.bin",
            headers=self.auth_headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.content, test_bytes)
        self.assertIn('attachment; filename="binary.bin"', res.headers.get("content-disposition", ""))


if __name__ == "__main__":
    unittest.main()
