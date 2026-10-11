"""Tests for Factory Studio Database Engine and Persistence Services."""

import os
import tempfile
import threading
import time
import unittest

from factory.ui.db import StudioDatabase


class TestStudioDatabaseEngine(unittest.TestCase):
    def setUp(self):
        self.db = StudioDatabase(":memory:")

    def test_schema_initialization_idempotent(self):
        # Initialized once in setUp, initialize second time to verify idempotency
        self.db.init_schema()
        # Verify tables exist
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}
        self.assertIn("chat_messages", tables)
        self.assertIn("factory_jobs", tables)
        self.assertIn("job_telemetry_events", tables)
        self.assertIn("job_console_logs", tables)
        self.assertIn("previews", tables)

    def test_wal_mode_and_pragmas_on_file_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_studio.db")
            db = StudioDatabase(db_path)
            conn = db._get_connection()
            cursor = conn.cursor()

            cursor.execute("PRAGMA journal_mode;")
            journal_mode = cursor.fetchone()[0]
            self.assertEqual(journal_mode.lower(), "wal")

            cursor.execute("PRAGMA busy_timeout;")
            busy_timeout = cursor.fetchone()[0]
            self.assertEqual(busy_timeout, 5000)

            cursor.execute("PRAGMA synchronous;")
            synchronous = cursor.fetchone()[0]
            # synchronous=NORMAL is 1
            self.assertEqual(synchronous, 1)
            db.close()

    def test_chat_messages_crud_and_repo_isolation(self):
        # Save message for repo-a
        msg1 = self.db.save_chat_message(
            repo="repo-a",
            role="user",
            content="Build a login form",
            milestone_slug="auth-v1",
            issue_number=1,
            turn_data={"step": 1},
        )
        self.assertIsNotNone(msg1.get("id"))
        self.assertEqual(msg1["repo"], "repo-a")
        self.assertEqual(msg1["role"], "user")
        self.assertEqual(msg1["content"], "Build a login form")
        self.assertEqual(msg1["turn_data"], {"step": 1})

        # Save assistant message for repo-a
        msg2 = self.db.save_chat_message(
            repo="repo-a",
            role="assistant",
            content="Here is the grilling question frontier",
            turn_data={"question": "What auth provider?", "recommended": "OAuth"},
        )

        # Save message for repo-b
        msg_b = self.db.save_chat_message(
            repo="repo-b",
            role="user",
            content="Create navigation menu",
        )

        # Retrieve messages for repo-a
        messages_a = self.db.get_chat_messages("repo-a")
        self.assertEqual(len(messages_a), 2)
        self.assertEqual(messages_a[0]["id"], msg1["id"])
        self.assertEqual(messages_a[0]["turn_data"], {"step": 1})
        self.assertEqual(messages_a[1]["id"], msg2["id"])
        self.assertEqual(messages_a[1]["turn_data"]["recommended"], "OAuth")

        # Retrieve messages for repo-b
        messages_b = self.db.get_chat_messages("repo-b")
        self.assertEqual(len(messages_b), 1)
        self.assertEqual(messages_b[0]["id"], msg_b["id"])

        # Delete messages for repo-a
        deleted_count = self.db.delete_chat_messages("repo-a")
        self.assertEqual(deleted_count, 2)
        self.assertEqual(len(self.db.get_chat_messages("repo-a")), 0)
        # repo-b messages remain intact
        self.assertEqual(len(self.db.get_chat_messages("repo-b")), 1)

    def test_factory_jobs_crud_and_rehydration(self):
        job_data = {
            "id": "job-101",
            "repo": "inventory-tracker",
            "feature": "barcode-scanner",
            "issue": "01",
            "model": "deepseek-v4.1-flash",
            "vm": False,
            "dev": True,
            "preview_url": "https://3000.mahesh0.dev",
            "status": "RUNNING",
            "stage": "CODER",
            "created_at": 1000.0,
            "started_at": 1001.0,
            "ended_at": None,
            "exit_code": None,
            "error_message": None,
        }
        self.db.save_job(job_data)

        fetched = self.db.get_job("job-101")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["id"], "job-101")
        self.assertEqual(fetched["repo"], "inventory-tracker")
        self.assertEqual(fetched["status"], "RUNNING")
        self.assertEqual(fetched["stage"], "CODER")
        self.assertEqual(fetched["preview_url"], "https://3000.mahesh0.dev")

        # Update job
        job_data["status"] = "SUCCESS"
        job_data["stage"] = "COMPLETED"
        job_data["exit_code"] = 0
        job_data["ended_at"] = 1050.0
        self.db.save_job(job_data)

        updated = self.db.get_job("job-101")
        self.assertEqual(updated["status"], "SUCCESS")
        self.assertEqual(updated["stage"], "COMPLETED")
        self.assertEqual(updated["exit_code"], 0)

        # Recent jobs
        recent = self.db.get_recent_jobs(limit=10)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["id"], "job-101")

    def test_previews_crud(self):
        preview_data = {
            "repo": "inventory-tracker",
            "branch": "factory/barcode-scanner",
            "preview_url": "https://3000.mahesh0.dev",
            "status": "SERVING",
            "stage": "SERVING",
            "updated_at": 1000.0,
        }
        self.db.save_preview(preview_data)

        fetched = self.db.get_preview("inventory-tracker")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["branch"], "factory/barcode-scanner")
        self.assertEqual(fetched["status"], "SERVING")

        all_previews = self.db.get_all_previews()
        self.assertEqual(len(all_previews), 1)
        self.assertEqual(all_previews[0]["repo"], "inventory-tracker")

    def test_telemetry_events_and_console_logs(self):
        # Telemetry events
        events = [
            {"seq": 1, "type": "stage", "stage": "PLANNER", "data": {"step": "plan"}},
            {"seq": 2, "type": "tool_call", "stage": "PLANNER", "data": {"tool": "read_file"}},
        ]
        self.db.append_telemetry_events("job-201", events)
        saved_events = self.db.get_telemetry_events("job-201")
        self.assertEqual(len(saved_events), 2)
        self.assertEqual(saved_events[0]["seq"], 1)
        self.assertEqual(saved_events[0]["event_type"], "stage")
        self.assertEqual(saved_events[0]["data"]["step"], "plan")
        self.assertEqual(saved_events[1]["seq"], 2)

        # Console logs
        logs = [
            (1, "Starting build process\n", "stdout"),
            (2, "Running npm install\n", "stdout"),
            (3, "Warning: deprecated package\n", "stderr"),
        ]
        self.db.append_console_logs("job-201", logs)
        saved_logs = self.db.get_console_logs("job-201")
        self.assertEqual(len(saved_logs), 3)
        self.assertEqual(saved_logs[0]["line_num"], 1)
        self.assertEqual(saved_logs[0]["text"], "Starting build process\n")
        self.assertEqual(saved_logs[2]["stream_type"], "stderr")

    def test_concurrent_wal_writes_and_reads(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "concurrent_test.db")
            db = StudioDatabase(db_path)

            def worker_writer(writer_id: int):
                for i in range(20):
                    db.save_chat_message(
                        repo=f"repo-{writer_id}",
                        role="user",
                        content=f"Message {i} from writer {writer_id}",
                    )
                    time.sleep(0.005)

            def worker_reader():
                for _ in range(20):
                    db.get_recent_jobs(10)
                    time.sleep(0.005)

            threads = []
            for w in range(3):
                threads.append(threading.Thread(target=worker_writer, args=(w,)))
            for _ in range(2):
                threads.append(threading.Thread(target=worker_reader))

            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # Verify all messages were recorded
            total_messages = 0
            for w in range(3):
                total_messages += len(db.get_chat_messages(f"repo-{w}"))
            self.assertEqual(total_messages, 60)
            db.close()

    def test_asynchronous_batch_log_and_event_flushing(self):
        # Enqueue console logs
        self.db.enqueue_log("job-async-1", 1, "Log line 1\n", "stdout")
        self.db.enqueue_log("job-async-1", 2, "Log line 2\n", "stderr")

        # Enqueue telemetry event
        self.db.enqueue_event(
            "job-async-1",
            1,
            {"type": "stage", "stage": "PLANNER", "data": {"thought": "analyzing"}},
        )

        # Flush batches immediately
        self.db.flush_batches()

        logs = self.db.get_console_logs("job-async-1")
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0]["line_num"], 1)
        self.assertEqual(logs[0]["text"], "Log line 1\n")
        self.assertEqual(logs[1]["stream_type"], "stderr")

        events = self.db.get_telemetry_events("job-async-1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["seq"], 1)
        self.assertEqual(events[0]["event_type"], "stage")
        self.assertEqual(events[0]["data"]["thought"], "analyzing")


class TestJobRegistryPersistenceIntegration(unittest.TestCase):
    def setUp(self):
        self.db = StudioDatabase(":memory:")

    def tearDown(self):
        self.db.close()

    def test_job_registry_write_through_and_rehydration(self):
        from factory.ui.registry import JobRegistry, JobStatus, JobStage

        # 1. Create registry with database
        registry = JobRegistry(db=self.db)

        # 2. Create job and verify write-through
        job = registry.create_job(
            repo="test-repo",
            feature="login-flow",
            issue="10",
            model="deepseek-v4.1-flash",
            vm=False,
            dev=True,
        )
        job.preview_url = "https://3000.mahesh0.dev"

        # Check job in database
        db_job = self.db.get_job(job.id)
        self.assertIsNotNone(db_job)
        self.assertEqual(db_job["repo"], "test-repo")
        self.assertEqual(db_job["feature"], "login-flow")
        self.assertEqual(db_job["status"], JobStatus.QUEUED.value)

        # 3. Stream log and telemetry event through registry
        registry.append_log(job.id, "Building application assets\n")
        registry.append_log(job.id, "Compilation warning\n", stream_type="stderr")
        registry.append_log(
            job.id,
            '__SF_EVENT__:{"type": "tool_call", "stage": "CODER", "data": {"tool": "edit"}}\n',
        )

        # Flush async DB queue
        self.db.flush_batches()

        # Verify logs in DB
        db_logs = self.db.get_console_logs(job.id)
        self.assertEqual(len(db_logs), 2)
        self.assertEqual(db_logs[0]["text"], "Building application assets\n")
        self.assertEqual(db_logs[0]["stream_type"], "stdout")
        self.assertEqual(db_logs[1]["text"], "Compilation warning\n")
        self.assertEqual(db_logs[1]["stream_type"], "stderr")

        db_events = self.db.get_telemetry_events(job.id)
        self.assertEqual(len(db_events), 1)
        self.assertEqual(db_events[0]["event_type"], "tool_call")

        # 4. Simulate server restart: create a new JobRegistry with the same DB and rehydrate
        new_registry = JobRegistry(db=self.db)
        new_registry.rehydrate()

        rehydrated_job = new_registry.get_job(job.id)
        self.assertIsNotNone(rehydrated_job)
        self.assertEqual(rehydrated_job.repo, "test-repo")
        self.assertEqual(rehydrated_job.feature, "login-flow")
        self.assertEqual(rehydrated_job.issue, "10")
        self.assertEqual(len(rehydrated_job.logs), 2)
        self.assertEqual(rehydrated_job.logs[0], "Building application assets\n")
        self.assertEqual(rehydrated_job.logs[1], "Compilation warning\n")
        self.assertEqual(len(rehydrated_job.events), 1)
        self.assertEqual(rehydrated_job.events[0]["type"], "tool_call")
        self.assertEqual(rehydrated_job.events[0]["stage"], "CODER")
        self.assertEqual(rehydrated_job.events[0]["data"]["tool"], "edit")

    def test_preview_registry_write_through_and_rehydration(self):
        from factory.ui.registry import PreviewRegistry, PreviewStatus, PreviewStage

        prev_reg = PreviewRegistry(db=self.db)
        # Seed preview state
        with prev_reg._lock:
            from factory.ui.registry import PreviewState
            state = PreviewState(
                repo="preview-repo",
                branch="factory/preview-repo",
                preview_url="https://preview.dev",
                status=PreviewStatus.SERVING,
                stage=PreviewStage.SERVING,
            )
            prev_reg._previews["preview-repo"] = state
            prev_reg._persist_preview(state)

        # Verify preview saved in DB
        db_prev = self.db.get_preview("preview-repo")
        self.assertIsNotNone(db_prev)
        self.assertEqual(db_prev["branch"], "factory/preview-repo")
        self.assertEqual(db_prev["status"], PreviewStatus.SERVING.value)

        # Simulate restart
        new_prev_reg = PreviewRegistry(db=self.db)
        new_prev_reg.rehydrate()

        rehydrated = new_prev_reg.get_preview("preview-repo")
        self.assertIsNotNone(rehydrated)
        self.assertEqual(rehydrated.branch, "factory/preview-repo")
        self.assertEqual(rehydrated.preview_url, "https://preview.dev")


if __name__ == "__main__":
    unittest.main()

