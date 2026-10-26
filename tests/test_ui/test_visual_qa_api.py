"""Subsystem tests for Visual QA telemetry and screenshot REST API."""

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from fastapi.testclient import TestClient

from factory.ui.app import create_app
from factory.ui.registry import JobRegistry, JobStatus, FactoryJob


class TestVisualQaApi(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="visual-qa-test-")
        self.orig_artifacts_dir = os.environ.get("FACTORY_ARTIFACTS_DIR")
        os.environ["FACTORY_ARTIFACTS_DIR"] = self.temp_dir

        self.registry = JobRegistry()
        self.app = create_app(registry=self.registry)
        self.client = TestClient(self.app)
        self.client.auth = ("admin", "admin")

    def tearDown(self):
        if self.orig_artifacts_dir is not None:
            os.environ["FACTORY_ARTIFACTS_DIR"] = self.orig_artifacts_dir
        else:
            os.environ.pop("FACTORY_ARTIFACTS_DIR", None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_visual_qa_endpoints_require_auth(self):
        unauth_client = TestClient(self.app)
        resp_meta = unauth_client.get("/api/studio/repos/test-repo/visual-qa")
        self.assertEqual(resp_meta.status_code, 401)

        resp_shot = unauth_client.get("/api/studio/repos/test-repo/visual-qa/screenshot")
        self.assertEqual(resp_shot.status_code, 401)

    def test_visual_qa_pending_state_when_no_artifacts(self):
        """When no artifacts or jobs exist, returns 200 with pending state."""
        resp = self.client.get("/api/studio/repos/my-app/visual-qa")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["passed"])
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["errors"], [])
        self.assertIsNone(data["desktop_url"])
        self.assertIsNone(data["mobile_url"])
        self.assertIsNone(data["captured_at"])

        # Canonical /api/repos/... alias should return identical structure
        resp_canonical = self.client.get("/api/repos/my-app/visual-qa")
        self.assertEqual(resp_canonical.status_code, 200)
        self.assertEqual(resp_canonical.json(), data)

    def test_visual_qa_from_disk_artifacts(self):
        """Reads metadata.json and serves screenshot URLs from artifacts directory."""
        vqa_dir = Path(self.temp_dir) / "visual-qa"
        vqa_dir.mkdir(parents=True, exist_ok=True)

        meta = {
            "passed": True,
            "status": "passed",
            "cleanCanvas": True,
            "errors": [],
            "captured_at": 1729900000.5,
        }
        (vqa_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
        (vqa_dir / "desktop.png").write_bytes(b"\x89PNG\r\n\x1a\nfake-desktop-png")
        (vqa_dir / "mobile.png").write_bytes(b"\x89PNG\r\n\x1a\nfake-mobile-png")

        resp = self.client.get("/api/studio/repos/my-app/visual-qa")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["passed"])
        self.assertEqual(data["status"], "passed")
        self.assertEqual(data["errors"], [])
        self.assertEqual(data["captured_at"], 1729900000.5)
        self.assertIsNotNone(data["desktop_url"])
        self.assertIn("viewport=desktop", data["desktop_url"])
        self.assertIsNotNone(data["mobile_url"])
        self.assertIn("viewport=mobile", data["mobile_url"])

    def test_visual_qa_with_branch_parameter(self):
        """Branch query param propagates to screenshot URLs and looks in branch folder."""
        branch_vqa_dir = Path(self.temp_dir) / "my-app" / "factory-feat" / "visual-qa"
        branch_vqa_dir.mkdir(parents=True, exist_ok=True)

        meta = {
            "passed": True,
            "status": "passed",
            "errors": [],
            "captured_at": 1729900111.0,
        }
        (branch_vqa_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
        (branch_vqa_dir / "desktop.png").write_bytes(b"\x89PNG\r\n\x1a\nbranch-desktop")

        resp = self.client.get("/api/studio/repos/my-app/visual-qa?branch=factory-feat")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["passed"])
        self.assertIn("branch=factory-feat", data["desktop_url"])

    def test_visual_qa_failure_telemetry(self):
        """Reports failure status and error details if Clean Canvas or runtime errors failed."""
        vqa_dir = Path(self.temp_dir) / "visual-qa"
        vqa_dir.mkdir(parents=True, exist_ok=True)

        meta = {
            "passed": False,
            "status": "failed",
            "cleanCanvas": False,
            "errors": [
                "Uncaught TypeError: Cannot read properties of undefined (reading 'map')",
                "Clean Canvas Invariant failed: #root has zero dimensions",
            ],
            "captured_at": 1729900222.0,
        }
        (vqa_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")

        resp = self.client.get("/api/studio/repos/my-app/visual-qa")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["passed"])
        self.assertEqual(data["status"], "failed")
        self.assertEqual(len(data["errors"]), 2)
        self.assertIn("Cannot read properties", data["errors"][0])

    def test_visual_qa_telemetry_from_job_events(self):
        """Falls back to JobRegistry events if metadata.json is absent on disk."""
        job = FactoryJob(
            id="job-vqa-1",
            repo="my-app",
            feature="vqa-test",
            issue="1",
            model="default",
            vm=False,
            status=JobStatus.SUCCESS,
        )
        job.events.append({
            "type": "visual_qa",
            "stage": "VERIFIER",
            "data": {
                "passed": True,
                "cleanCanvas": True,
                "errors": [],
                "screenshots": {
                    "desktop": "/tmp/nonexistent-desktop.png",
                    "mobile": "/tmp/nonexistent-mobile.png",
                },
                "summary": "Visual QA passed",
            },
            "timestamp": 1729900333.0,
        })
        self.registry._jobs[job.id] = job

        resp = self.client.get("/api/studio/repos/my-app/visual-qa")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["passed"])
        self.assertEqual(data["status"], "passed")
        self.assertEqual(data["captured_at"], 1729900333.0)

    def test_visual_qa_telemetry_branch_filtering_from_job_events(self):
        """Filters job events by target branch when branch parameter is provided."""
        job_feat_a = FactoryJob(
            id="job-vqa-feat-a",
            repo="my-app",
            feature="feat-a",
            issue="1",
            model="default",
            vm=False,
            status=JobStatus.SUCCESS,
        )
        job_feat_a.events.append({
            "type": "visual_qa",
            "stage": "VERIFIER",
            "data": {
                "passed": True,
                "cleanCanvas": True,
                "errors": [],
                "screenshots": {"desktop": "/tmp/nonexistent-a.png"},
                "summary": "Visual QA passed on feat-a",
            },
            "timestamp": 1729900100.0,
        })

        job_feat_b = FactoryJob(
            id="job-vqa-feat-b",
            repo="my-app",
            feature="feat-b",
            issue="2",
            model="default",
            vm=False,
            status=JobStatus.SUCCESS,
        )
        job_feat_b.events.append({
            "type": "visual_qa",
            "stage": "VERIFIER",
            "data": {
                "passed": False,
                "cleanCanvas": False,
                "errors": ["Clean Canvas failed on feat-b"],
                "screenshots": {},
                "summary": "Visual QA failed on feat-b",
            },
            "timestamp": 1729900200.0,
        })

        self.registry._jobs[job_feat_a.id] = job_feat_a
        self.registry._jobs[job_feat_b.id] = job_feat_b

        # Query feat-a: returns job_feat_a event
        resp_a = self.client.get("/api/studio/repos/my-app/visual-qa?branch=factory/feat-a")
        self.assertEqual(resp_a.status_code, 200)
        data_a = resp_a.json()
        self.assertTrue(data_a["passed"])
        self.assertEqual(data_a["captured_at"], 1729900100.0)

        # Query feat-b: returns job_feat_b event
        resp_b = self.client.get("/api/studio/repos/my-app/visual-qa?branch=feat-b")
        self.assertEqual(resp_b.status_code, 200)
        data_b = resp_b.json()
        self.assertFalse(data_b["passed"])
        self.assertEqual(data_b["captured_at"], 1729900200.0)

        # Query nonexistent branch: returns pending
        resp_c = self.client.get("/api/studio/repos/my-app/visual-qa?branch=feat-nonexistent")
        self.assertEqual(resp_c.status_code, 200)
        self.assertEqual(resp_c.json()["status"], "pending")

    def test_screenshot_endpoint_serves_png(self):
        """Serves PNG image with image/png media type."""
        vqa_dir = Path(self.temp_dir) / "visual-qa"
        vqa_dir.mkdir(parents=True, exist_ok=True)
        sample_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        (vqa_dir / "desktop.png").write_bytes(sample_png)
        (vqa_dir / "mobile.png").write_bytes(b"\x89PNG\r\n\x1a\nmobile-bytes")

        # Desktop viewport
        resp_desktop = self.client.get("/api/studio/repos/my-app/visual-qa/screenshot?viewport=desktop")
        self.assertEqual(resp_desktop.status_code, 200)
        self.assertTrue(resp_desktop.headers["content-type"].startswith("image/png"))
        self.assertEqual(resp_desktop.content, sample_png)

        # Mobile viewport
        resp_mobile = self.client.get("/api/studio/repos/my-app/visual-qa/screenshot?viewport=mobile")
        self.assertEqual(resp_mobile.status_code, 200)
        self.assertTrue(resp_mobile.headers["content-type"].startswith("image/png"))
        self.assertEqual(resp_mobile.content, b"\x89PNG\r\n\x1a\nmobile-bytes")

        # Canonical route alias
        resp_canon = self.client.get("/api/repos/my-app/visual-qa/screenshot?viewport=desktop")
        self.assertEqual(resp_canon.status_code, 200)
        self.assertEqual(resp_canon.content, sample_png)

    def test_screenshot_endpoint_404_when_missing(self):
        """Returns 404 when screenshot file does not exist."""
        resp = self.client.get("/api/studio/repos/my-app/visual-qa/screenshot?viewport=desktop")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()
