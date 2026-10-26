"""Tests for Studio Database snapshot metadata persistence and migration."""

import os
import sqlite3 as raw_sqlite
import tempfile
import unittest

from factory.ui.db import StudioDatabase


class TestStudioDatabaseSnapshot(unittest.TestCase):
    def setUp(self):
        self.db = StudioDatabase(":memory:")

    def tearDown(self):
        self.db.close()

    def test_snapshot_metadata_persistence(self):
        self.assertIsNone(self.db.get_snapshot_metadata("repo-snap"))
        self.db.save_snapshot_metadata(
            repo="repo-snap",
            snapshot_image_id="im-test-1234",
            snapshot_commit_sha="a" * 40,
            captured_at=123456.0,
        )
        snap = self.db.get_snapshot_metadata("repo-snap")
        self.assertIsNotNone(snap)
        self.assertEqual(snap["repo"], "repo-snap")
        self.assertEqual(snap["snapshot_image_id"], "im-test-1234")
        self.assertEqual(snap["snapshot_commit_sha"], "a" * 40)
        self.assertEqual(snap["snapshot_captured_at"], 123456.0)

        # Updating preview state preserves snapshot metadata
        self.db.save_preview({
            "repo": "repo-snap",
            "branch": "factory/feature-1",
            "status": "SERVING",
            "stage": "SERVING",
        })
        snap_after = self.db.get_snapshot_metadata("repo-snap")
        self.assertIsNotNone(snap_after)
        self.assertEqual(snap_after["snapshot_image_id"], "im-test-1234")
        preview = self.db.get_preview("repo-snap")
        self.assertEqual(preview["status"], "SERVING")
        self.assertEqual(preview["snapshot_image_id"], "im-test-1234")

    def test_preview_snapshot_schema_migration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "legacy.db")
            conn = raw_sqlite.connect(db_path)
            conn.execute(
                "CREATE TABLE previews (repo TEXT PRIMARY KEY, branch TEXT, preview_url TEXT, status TEXT NOT NULL, stage TEXT NOT NULL, updated_at REAL NOT NULL);"
            )
            conn.execute("INSERT INTO previews VALUES ('legacy-repo', 'main', NULL, 'IDLE', 'IDLE', 100.0);")
            conn.commit()
            conn.close()

            legacy_db = StudioDatabase(db_path)
            self.assertIsNone(legacy_db.get_snapshot_metadata("legacy-repo"))
            legacy_db.save_snapshot_metadata("legacy-repo", "im-migrated", "b" * 40, 200.0)
            meta = legacy_db.get_snapshot_metadata("legacy-repo")
            self.assertEqual(meta["snapshot_image_id"], "im-migrated")
            legacy_db.close()


if __name__ == "__main__":
    unittest.main()
