"""Unit tests for Modal Sandbox Snapshot Registry."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from sandbox.snapshots import (
    delete_snapshot,
    get_snapshot,
    list_snapshots,
    record_snapshot,
)


class TestSnapshotRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.registry_file = Path(self.tmp_dir.name) / "test-snapshots.json"

    def tearDown(self):
        self.tmp_dir.cleanup()

    @patch("sandbox.snapshots._get_modal_dict", return_value=None)
    def test_local_fallback_record_and_list(self, _mock_dict):
        with patch("sandbox.snapshots.LOCAL_REGISTRY_FILE", self.registry_file):
            # Initially empty
            self.assertEqual(list_snapshots(), [])

            # Record snapshot
            rec1 = record_snapshot(
                image_id="im-test1",
                sandbox_id="sb-test1",
                name="first-snapshot",
                ttl_days=14,
                is_vm=False,
            )
            self.assertEqual(rec1["image_id"], "im-test1")
            self.assertEqual(rec1["name"], "first-snapshot")
            self.assertEqual(rec1["ttl_days"], 14)
            self.assertFalse(rec1["is_vm"])

            # Verify saved locally
            self.assertTrue(self.registry_file.is_file())

            # List snapshots
            snapshots = list_snapshots()
            self.assertEqual(len(snapshots), 1)
            self.assertEqual(snapshots[0]["image_id"], "im-test1")

            # Get snapshot
            fetched = get_snapshot("im-test1")
            self.assertIsNotNone(fetched)
            self.assertEqual(fetched["image_id"], "im-test1")

            # Record second snapshot
            record_snapshot(
                image_id="im-test2",
                sandbox_id="sb-test2",
                name="second-snapshot",
                ttl_days=30,
                is_vm=True,
            )
            self.assertEqual(len(list_snapshots()), 2)

            # Delete snapshot
            self.assertTrue(delete_snapshot("im-test1"))
            self.assertFalse(delete_snapshot("im-nonexistent"))
            self.assertEqual(len(list_snapshots()), 1)
            self.assertIsNone(get_snapshot("im-test1"))

    def test_modal_dict_integration(self):
        mock_dict = {}
        mock_modal_dict = MagicMock()
        mock_modal_dict.__setitem__.side_effect = mock_dict.__setitem__
        mock_modal_dict.__getitem__.side_effect = mock_dict.__getitem__
        mock_modal_dict.values.side_effect = mock_dict.values
        mock_modal_dict.get.side_effect = mock_dict.get
        mock_modal_dict.__contains__.side_effect = mock_dict.__contains__
        mock_modal_dict.pop.side_effect = mock_dict.pop

        with patch("sandbox.snapshots._get_modal_dict", return_value=mock_modal_dict):
            rec = record_snapshot(
                image_id="im-cloud",
                sandbox_id="sb-cloud",
                name="cloud-snap",
                ttl_days=30,
                is_vm=True,
            )
            self.assertEqual(rec["image_id"], "im-cloud")
            self.assertIn("im-cloud", mock_dict)

            # List
            snaps = list_snapshots()
            self.assertEqual(len(snaps), 1)
            self.assertEqual(snaps[0]["image_id"], "im-cloud")

            # Get
            item = get_snapshot("im-cloud")
            self.assertIsNotNone(item)
            self.assertEqual(item["name"], "cloud-snap")

            # Delete
            deleted = delete_snapshot("im-cloud")
            self.assertTrue(deleted)
            self.assertNotIn("im-cloud", mock_dict)
