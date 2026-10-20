"""Subsystem tests for Pre-Merge Diff Viewer backend endpoints."""

import json
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from factory.ui.app import create_app
from factory.ui.registry import PreviewRegistry, PreviewState, PreviewStatus


class TestDiffEndpoints(unittest.TestCase):
    def setUp(self):
        self.preview_reg = PreviewRegistry()
        self.app = create_app(preview_reg=self.preview_reg)
        self.client = TestClient(self.app)
        self.auth_headers = {"Authorization": "Basic YWRtaW46YWRtaW4="}

    def test_get_diff_working_tree_sandbox_uncommitted(self):
        """When container is running, executes in-container git diff HEAD and returns uncommitted edits."""
        mock_sandbox = MagicMock()
        mock_proc = MagicMock()

        sample_diff = (
            "diff --git a/src/App.tsx b/src/App.tsx\n"
            "index 1234567..89abcdef 100644\n"
            "--- a/src/App.tsx\n"
            "+++ b/src/App.tsx\n"
            "@@ -10,3 +10,5 @@ export function App() {\n"
            "   const count = 0;\n"
            "+  const active = true;\n"
            "+  const name = 'Studio';\n"
            "   return <div>{count}</div>;\n"
        )
        untracked_json = json.dumps(["src/NewComponent.tsx", "node_modules/temp.js"])

        payload = {
            "diff": sample_diff,
            "untracked": [
                {
                    "path": "src/NewComponent.tsx",
                    "content": "export function NewComponent() {\n  return <div>New</div>;\n}\n",
                }
            ],
        }

        mock_proc.stdout = [json.dumps(payload).encode("utf-8")]
        mock_proc.stderr = []
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_sandbox.exec.return_value = mock_proc

        preview = PreviewState(
            repo="test-repo",
            branch="factory/feature-diff",
            status=PreviewStatus.SERVING,
        )
        preview.sandbox = mock_sandbox
        self.preview_reg._previews["test-repo"] = preview

        res = self.client.get(
            "/api/repos/test-repo/diff?scope=working_tree",
            headers=self.auth_headers,
        )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()

        self.assertEqual(data["repo"], "test-repo")
        self.assertEqual(data["scope"], "working_tree")
        self.assertEqual(data["source"], "sandbox")
        self.assertFalse(data["clean"])

        paths = [f["path"] for f in data["files"]]
        self.assertIn("src/App.tsx", paths)
        self.assertIn("src/NewComponent.tsx", paths)
        self.assertNotIn("node_modules/temp.js", paths)

        app_file = next(f for f in data["files"] if f["path"] == "src/App.tsx")
        self.assertEqual(app_file["status"], "modified")
        self.assertEqual(app_file["additions"], 2)
        self.assertEqual(app_file["deletions"], 0)

        new_file = next(f for f in data["files"] if f["path"] == "src/NewComponent.tsx")
        self.assertEqual(new_file["status"], "added")
        self.assertEqual(new_file["additions"], 3)
        self.assertEqual(new_file["deletions"], 0)

        self.assertEqual(data["summary"]["total_files"], 2)
        self.assertEqual(data["summary"]["additions"], 5)
        self.assertEqual(data["summary"]["deletions"], 0)

    def test_get_diff_working_tree_sandbox_stopped_is_clean(self):
        """When container is not running, working tree diff returns clean empty state."""
        res = self.client.get(
            "/api/repos/test-repo/diff?scope=working_tree",
            headers=self.auth_headers,
        )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()

        self.assertEqual(data["repo"], "test-repo")
        self.assertEqual(data["scope"], "working_tree")
        self.assertTrue(data["clean"])
        self.assertEqual(data["files"], [])
        self.assertEqual(data["summary"]["total_files"], 0)

    @patch("factory.ui.github._client.get_test_org_token")
    @patch("factory.ui.routes.diffs.httpx.Client")
    def test_get_diff_branch_fallback_to_github_compare(self, mock_client_cls, mock_token):
        """When scope is branch, queries GitHub compare API and filters ignored directories."""
        mock_token.return_value = "ghp_mocktoken123"

        mock_compare_payload = {
            "status": "ahead",
            "ahead_by": 2,
            "behind_by": 0,
            "total_commits": 2,
            "files": [
                {
                    "filename": "src/routes.ts",
                    "status": "modified",
                    "additions": 12,
                    "deletions": 3,
                    "changes": 15,
                    "patch": "@@ -1,5 +1,14 @@\n-const old = 1;\n+const next = 2;\n",
                },
                {
                    "filename": "dist/bundle.js",
                    "status": "modified",
                    "additions": 100,
                    "deletions": 100,
                    "changes": 200,
                    "patch": "@@ -1,1 +1,1 @@\n",
                },
                {
                    "filename": "src/Deleted.ts",
                    "status": "removed",
                    "additions": 0,
                    "deletions": 8,
                    "changes": 8,
                    "patch": "@@ -1,8 +0,0 @@\n-line\n",
                },
            ],
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_compare_payload
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_resp

        res = self.client.get(
            "/api/repos/test-repo/diff?scope=branch&branch=factory/feature-1&base=main",
            headers=self.auth_headers,
        )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()

        self.assertEqual(data["repo"], "test-repo")
        self.assertEqual(data["scope"], "branch")
        self.assertEqual(data["branch"], "factory/feature-1")
        self.assertEqual(data["base"], "main")
        self.assertEqual(data["source"], "github")
        self.assertFalse(data["clean"])

        paths = [f["path"] for f in data["files"]]
        self.assertIn("src/routes.ts", paths)
        self.assertIn("src/Deleted.ts", paths)
        self.assertNotIn("dist/bundle.js", paths)

        deleted_file = next(f for f in data["files"] if f["path"] == "src/Deleted.ts")
        self.assertEqual(deleted_file["status"], "deleted")
        self.assertEqual(deleted_file["deletions"], 8)

        self.assertEqual(data["summary"]["total_files"], 2)
        self.assertEqual(data["summary"]["additions"], 12)
        self.assertEqual(data["summary"]["deletions"], 11)

    @patch("factory.ui.github._client.get_test_org_token")
    @patch("factory.ui.routes.diffs.httpx.Client")
    def test_get_diff_branch_identical_is_clean(self, mock_client_cls, mock_token):
        """When branch has no differences compared to base, returns clean=True."""
        mock_token.return_value = "ghp_mocktoken123"

        mock_compare_payload = {
            "status": "identical",
            "ahead_by": 0,
            "behind_by": 0,
            "total_commits": 0,
            "files": [],
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_compare_payload
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.return_value = mock_resp

        res = self.client.get(
            "/api/repos/test-repo/diff?scope=branch&branch=main&base=main",
            headers=self.auth_headers,
        )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()

        self.assertTrue(data["clean"])
        self.assertEqual(data["files"], [])
        self.assertEqual(data["summary"]["total_files"], 0)

    def test_get_diff_branch_live_sandbox(self):
        """When container is running, executes in-container git diff against base branch."""
        mock_sandbox = MagicMock()
        mock_proc = MagicMock()

        sample_diff = (
            "diff --git a/src/feature.ts b/src/feature.ts\n"
            "index 0000000..1111111 100644\n"
            "--- a/src/feature.ts\n"
            "+++ b/src/feature.ts\n"
            "@@ -0,0 +1,3 @@\n"
            "+export const feature = true;\n"
            "+export const version = '2.0';\n"
            "+export const ready = true;\n"
        )
        mock_proc.stdout = [json.dumps({"diff": sample_diff, "success": True}).encode("utf-8")]
        mock_proc.stderr = []
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_sandbox.exec.return_value = mock_proc

        preview = PreviewState(
            repo="test-repo",
            branch="factory/feature-2",
            status=PreviewStatus.SERVING,
        )
        preview.sandbox = mock_sandbox
        self.preview_reg._previews["test-repo"] = preview

        res = self.client.get(
            "/api/repos/test-repo/diff?scope=branch&branch=factory/feature-2&base=main",
            headers=self.auth_headers,
        )
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()

        self.assertEqual(data["repo"], "test-repo")
        self.assertEqual(data["scope"], "branch")
        self.assertEqual(data["source"], "sandbox")
        self.assertFalse(data["clean"])
        self.assertEqual(len(data["files"]), 1)
        self.assertEqual(data["files"][0]["path"], "src/feature.ts")
        self.assertEqual(data["files"][0]["additions"], 3)
        self.assertEqual(data["files"][0]["deletions"], 0)

