"""Subsystem tests for Factory Testing Console and Studio UI."""

import json
import os
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from fastapi.testclient import TestClient

from factory.run import main, parse_args
from factory.ui.app import create_app
from factory.ui.github import (
    DEFAULT_TEST_ORG,
    fetch_repo_issue,
    fetch_repo_issues,
    fetch_repo_milestones,
    fetch_repo_milestones_and_issues,
    check_tanstack_start_compatibility,
    fetch_test_org_repos,
    fetch_test_org_repos_detailed,
    get_test_org_token,
    instantiate_repo_from_template,
    map_github_issue_status,
    parse_github_blocked_by,
    RepoCreationError,
    validate_github_repo_name,
    create_repo_milestone,
    create_repo_issue,
    resolve_or_create_milestone,
    synthesize_ticket_content,
    synthesize_and_create_issue,
    _normalize_github_issue,
    fetch_repo_pull_requests,
    merge_repo_pull_request,
    PullRequestMergeError,
    fetch_repo_branches,
    reopen_repo_issue_for_rollback,
    update_local_markdown_issue_for_rollback,
)
from factory.ui.db import StudioDatabase
from factory.ui.registry import (
    JobRegistry,
    JobStage,
    JobStatus,
    PreviewRegistry,
    PreviewStage,
    PreviewState,
    PreviewStatus,
)


class TestJobRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = JobRegistry(max_log_lines=50)

    def test_create_and_get_job(self):
        job = self.registry.create_job(
            repo="test3",
            feature="slug-generator",
            issue="01",
            model="deepseek-v4.1-flash",
            vm=True,
        )
        self.assertEqual(job.repo, "test3")
        self.assertEqual(job.feature, "slug-generator")
        self.assertEqual(job.issue, "01")
        self.assertEqual(job.status, JobStatus.QUEUED)
        self.assertEqual(job.stage, JobStage.IDLE)
        self.assertTrue(job.vm)

        fetched = self.registry.get_job(job.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, job.id)

    def test_append_log_and_stage_detection(self):
        job = self.registry.create_job(repo="test3", feature="slug-generator")
        q = self.registry.add_listener(job.id)

        # Stage 0: Preflight
        self.registry.append_log(job.id, "Running Pre-flight Guard Check on workspace...\n")
        self.assertEqual(job.stage, JobStage.PREFLIGHT)
        event1 = q.get_nowait()
        self.assertEqual(event1["event"], "stage")
        self.assertEqual(event1["stage"], JobStage.PREFLIGHT.value)

        # Stage 1: Planner
        self.registry.append_log(job.id, "Stage 1: Planner Agent analyzing codebase\n")
        self.assertEqual(job.stage, JobStage.PLANNER)

        # Stage 2: Coder
        self.registry.append_log(job.id, "Stage 2: Coder Agent coding implementation\n")
        self.assertEqual(job.stage, JobStage.CODER)

        # Stage 3: Verifier
        self.registry.append_log(job.id, "Stage 3: Deterministic Verifier running test suite\n")
        self.assertEqual(job.stage, JobStage.VERIFIER)

        # Stage 4: Reviewer
        self.registry.append_log(job.id, "Stage 4: Reviewer Agent auditing diff\n")
        self.assertEqual(job.stage, JobStage.REVIEWER)

        # Stage complete
        self.registry.append_log(job.id, "🎉 Assembly line pipeline completed successfully!\n")
        self.assertEqual(job.stage, JobStage.COMPLETED)

        self.registry.remove_listener(job.id, q)

    def test_cancel_running_job(self):
        job = self.registry.create_job(repo="test3", feature="slug-generator")
        mock_sandbox = MagicMock()
        job.sandbox = mock_sandbox
        job.status = JobStatus.RUNNING

        res = self.registry.cancel_job(job.id)
        self.assertTrue(res)
        self.assertEqual(job.status, JobStatus.CANCELLED)
        mock_sandbox.terminate.assert_called_once()
        self.assertIn("cancelled", job.logs[-1].lower())

    def test_create_job_with_dev_preview(self):
        job = self.registry.create_job(
            repo="test3",
            feature="preview-feat",
            dev=True,
        )
        self.assertTrue(job.dev)
        self.assertEqual(job.preview_url, "https://3000.mahesh0.dev")
        d = job.to_dict()
        self.assertTrue(d["dev"])
        self.assertEqual(d["preview_url"], "https://3000.mahesh0.dev")

    def test_stage_detection_serving(self):
        job = self.registry.create_job(repo="test3", feature="slug-generator", dev=True)
        self.registry.append_log(job.id, "🎉 Assembly line pipeline completed successfully!\n")
        self.assertEqual(job.stage, JobStage.COMPLETED)

        self.registry.append_log(job.id, "⏳ Container entering active serving keep-alive state (https://3000.mahesh0.dev)...\n")
        self.assertEqual(job.stage, JobStage.SERVING)

    def test_cancel_serving_job_terminates_sandbox(self):
        job = self.registry.create_job(repo="test3", feature="slug-generator", dev=True)
        mock_sandbox = MagicMock()
        job.sandbox = mock_sandbox
        job.status = JobStatus.RUNNING
        job.stage = JobStage.SERVING

        res = self.registry.cancel_job(job.id)
        self.assertTrue(res)
        self.assertEqual(job.status, JobStatus.CANCELLED)
        mock_sandbox.terminate.assert_called_once()
        self.assertIn("cancelled", job.logs[-1].lower())
