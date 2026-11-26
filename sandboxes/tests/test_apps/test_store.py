"""Tests for per-record JSON FactoryStateStore and Modal Volume synchronization."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

from sandbox.apps import FactoryAppRecord, FactoryStateStore, LaunchRequestRecord


class TestFactoryStateStore(unittest.TestCase):
    def test_app_and_launch_crud_roundtrip_and_sorting(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            app_old = FactoryAppRecord(
                app_id="app_old",
                slug="old-app",
                title="Old App",
                prompt="Build old app",
                created_at="2026-11-26T08:00:00+00:00",
                updated_at="2026-11-26T08:00:00+00:00",
            )
            app_new = FactoryAppRecord(
                app_id="app_new",
                slug="new-app",
                title="New App",
                prompt="Build new app",
                created_at="2026-11-26T09:00:00+00:00",
                updated_at="2026-11-26T09:00:00+00:00",
            )
            launch = LaunchRequestRecord(
                request_id="req_1",
                app_id="app_new",
                status="queued",
            )

            store.save_app(app_old)
            store.create_app_and_launch(app_new, launch)

            listed = store.list_apps()
            self.assertEqual([item.app_id for item in listed], ["app_new", "app_old"])
            self.assertEqual(store.get_app("app_new").slug, "new-app")
            self.assertEqual(store.get_launch("req_1").status, "queued")

            future_expiry = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
            updated = store.update_launch(
                "req_1",
                status="ready",
                handoff_url="https://t3/env/thr#token=abc",
                handoff_expires_at=future_expiry,
            )
            self.assertEqual(updated.status, "ready")
            self.assertEqual(store.get_launch("req_1").handoff_url, "https://t3/env/thr#token=abc")

            self.assertTrue(store.delete_app("app_new"))
            self.assertIsNone(store.get_app("app_new"))
            self.assertIsNone(store.get_launch("req_1"))
            self.assertTrue(store.delete_app("app_old"))
            self.assertFalse(store.delete_app("app_missing"))

    def test_volume_reload_on_read_and_commit_on_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            events: list[str] = []
            mock_volume = MagicMock()
            mock_volume.reload.side_effect = lambda: events.append("reload")
            mock_volume.commit.side_effect = lambda: events.append("commit")

            store = FactoryStateStore(root_dir=Path(tmpdir), volume=mock_volume)
            app = FactoryAppRecord(
                app_id="app_vol",
                slug="vol-app",
                title="Vol App",
                prompt="Build vol app",
            )
            launch = LaunchRequestRecord(request_id="req_vol", app_id="app_vol")

            store.create_app_and_launch(app, launch)
            self.assertEqual(events, ["commit"])

            events.clear()
            fetched_launch = store.get_launch("req_vol")
            self.assertIsNotNone(fetched_launch)
            self.assertEqual(events, ["reload"])

            events.clear()
            apps = store.list_apps()
            self.assertEqual(len(apps), 1)
            self.assertEqual(events, ["reload"])

            events.clear()
            store.update_launch("req_vol", status="launching_sandbox")
            self.assertEqual(events, ["reload", "commit"])

    def test_expired_handoff_url_is_scrubbed_on_read(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            app = FactoryAppRecord(app_id="app_exp", slug="exp", title="Exp", prompt="Exp")
            past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
            launch = LaunchRequestRecord(
                request_id="req_exp",
                app_id="app_exp",
                status="ready",
                handoff_url="https://t3/env/thr#token=stale",
                handoff_expires_at=past,
            )
            store.create_app_and_launch(app, launch)
            fetched = store.get_launch("req_exp")
            self.assertIsNotNone(fetched)
            self.assertIsNone(fetched.handoff_url)

    def test_concurrent_updates_across_distinct_keys_and_shared_store_lock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_a = FactoryStateStore(root_dir=Path(tmpdir))
            store_b = FactoryStateStore(root_dir=Path(tmpdir))
            self.assertIs(store_a._lock, store_b._lock)

            for idx in range(6):
                store_a.create_app_and_launch(
                    FactoryAppRecord(app_id=f"app_{idx}", slug=f"app-{idx}", title=f"App {idx}", prompt="P"),
                    LaunchRequestRecord(request_id=f"req_{idx}", app_id=f"app_{idx}"),
                )

            def _update(idx: int) -> None:
                target = store_a if idx % 2 == 0 else store_b
                target.update_app(f"app_{idx}", status="ready", sandbox_id=f"sb-{idx}")
                target.update_launch(f"req_{idx}", status="ready")

            with ThreadPoolExecutor(max_workers=6) as pool:
                list(pool.map(_update, range(6)))

            apps = {a.app_id: a for a in store_a.list_apps()}
            self.assertEqual(len(apps), 6)
            for idx in range(6):
                self.assertEqual(apps[f"app_{idx}"].status, "ready")
                self.assertEqual(store_b.get_launch(f"req_{idx}").status, "ready")

    def test_update_app_if_current_request_prevents_stale_clobber(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            store.save_app(
                FactoryAppRecord(
                    app_id="app_race",
                    slug="race",
                    title="Race",
                    prompt="Race",
                    latest_request_id="req_new",
                )
            )
            self.assertIsNone(store.update_app_if_current_request("app_race", "req_old", status="ready"))
            self.assertEqual(store.get_app("app_race").status, "provisioning")
            updated = store.update_app_if_current_request("app_race", "req_new", status="ready")
            self.assertIsNotNone(updated)
            self.assertEqual(updated.status, "ready")
            self.assertIsNone(store.update_app_if_current_request("app_missing", "req_new", status="ready"))

    def test_rejects_unsafe_record_ids(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            self.assertIsNone(store.get_app("../etc/passwd"))
            with self.assertRaises(ValueError):
                store.save_app(
                    FactoryAppRecord(
                        app_id="../escape",
                        slug="escape",
                        title="Escape",
                        prompt="Escape",
                    )
                )
