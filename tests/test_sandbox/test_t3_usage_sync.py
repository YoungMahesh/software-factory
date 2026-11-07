"""Unit tests for T3 Code usage and transcript synchronization daemon."""

from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from shared.t3_usage_sync import T3UsageSync, _atomic_copy_file, main


class TestT3UsageSync(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.storage_dir = self.root / "storage"
        self.userdata_dir = self.root / "userdata"
        self.home_dir = self.root / "home"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_atomic_copy_file(self):
        src = self.root / "src.txt"
        dst = self.root / "sub" / "dst.txt"

        # Missing src returns False
        self.assertFalse(_atomic_copy_file(src, dst))

        # Copy non-existent destination
        src.write_text("hello world")
        self.assertTrue(_atomic_copy_file(src, dst))
        self.assertEqual(dst.read_text(), "hello world")

        # Destination identical: returns False (no-op)
        self.assertFalse(_atomic_copy_file(src, dst))

        # Newer source: updates destination
        time.sleep(0.01)
        src.write_text("updated content")
        self.assertTrue(_atomic_copy_file(src, dst))
        self.assertEqual(dst.read_text(), "updated content")

    def test_hydrate_skips_when_storage_missing(self):
        syncer = T3UsageSync(
            storage_dir=self.storage_dir,
            userdata_dir=self.userdata_dir,
            home_dir=self.home_dir,
        )
        counts = syncer.hydrate()
        self.assertEqual(counts, {"caches": 0, "conversations": 0, "transcripts": 0})
        self.assertFalse(self.userdata_dir.exists())

    def test_hydrate_restores_caches_and_conversations(self):
        syncer = T3UsageSync(
            storage_dir=self.storage_dir,
            userdata_dir=self.userdata_dir,
            home_dir=self.home_dir,
        )
        syncer.ensure_storage_dirs()

        # Seed storage with cache and conversation
        cache_file = syncer.storage_cache / "usage-scan-cache-v9.json"
        cache_file.write_text('{"rates": {}}')
        rates_file = syncer.storage_cache / "usage-model-rates.json"
        rates_file.write_text('{"pricing": {}}')
        conv_file = syncer.storage_conversations / "chat-uuid.db"
        conv_file.write_text("sqlite-db-binary-mock")

        # Claude transcript in storage
        claude_t = syncer.storage_claude / "proj1" / "chat.json"
        claude_t.parent.mkdir(parents=True, exist_ok=True)
        claude_t.write_text('{"messages": []}')

        # Fake live conversation target directory
        fake_conv_dir = self.userdata_dir / "providers" / "antigravity" / "inst-1" / "antigravity-acp" / "conversations"
        fake_conv_dir.mkdir(parents=True, exist_ok=True)

        counts = syncer.hydrate()
        self.assertEqual(counts["caches"], 2)
        self.assertEqual(counts["conversations"], 1)
        self.assertEqual(counts["transcripts"], 1)

        self.assertTrue((self.userdata_dir / "usage-scan-cache-v9.json").is_file())
        self.assertTrue((self.userdata_dir / "usage-model-rates.json").is_file())
        self.assertTrue((fake_conv_dir / "chat-uuid.db").is_file())
        self.assertTrue((self.home_dir / ".claude" / "projects" / "proj1" / "chat.json").is_file())

    def test_sync_flushes_live_caches_and_conversations_to_storage(self):
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        syncer = T3UsageSync(
            storage_dir=self.storage_dir,
            userdata_dir=self.userdata_dir,
            home_dir=self.home_dir,
        )

        # Create live cache file in userdata
        self.userdata_dir.mkdir(parents=True, exist_ok=True)
        live_cache = self.userdata_dir / "usage-scan-cache-v9.json"
        live_cache.write_text('{"scanned": 42}')

        # Create live conversation DB
        fake_conv_dir = self.userdata_dir / "providers" / "antigravity" / "inst-2" / "antigravity-acp" / "conversations"
        fake_conv_dir.mkdir(parents=True, exist_ok=True)
        live_conv = fake_conv_dir / "history.db"
        live_conv.write_text("db-content-123")

        # Create live Codex session
        codex_dir = self.home_dir / ".codex" / "sessions"
        codex_dir.mkdir(parents=True, exist_ok=True)
        (codex_dir / "session1.json").write_text('{"codex": true}')

        counts = syncer.sync()
        self.assertEqual(counts["caches"], 1)
        self.assertEqual(counts["conversations"], 1)
        self.assertEqual(counts["transcripts"], 1)

        self.assertTrue((syncer.storage_cache / "usage-scan-cache-v9.json").is_file())
        self.assertEqual(
            (syncer.storage_cache / "usage-scan-cache-v9.json").read_text(),
            '{"scanned": 42}',
        )
        self.assertTrue((syncer.storage_conversations / "history.db").is_file())
        self.assertEqual(
            (syncer.storage_conversations / "history.db").read_text(),
            "db-content-123",
        )
        self.assertTrue((syncer.storage_codex / "session1.json").is_file())

    def test_status_reports_accurate_counts(self):
        syncer = T3UsageSync(
            storage_dir=self.storage_dir,
            userdata_dir=self.userdata_dir,
            home_dir=self.home_dir,
        )
        st_initial = syncer.status()
        self.assertFalse(st_initial["storage_mounted"])
        self.assertEqual(st_initial["persisted_conversations"], 0)
        self.assertEqual(st_initial["persisted_cache_files"], 0)

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        syncer.ensure_storage_dirs()
        (syncer.storage_cache / "usage-scan-cache-v9.json").write_text("{}")
        (syncer.storage_conversations / "test1.db").write_text("data")

        st_updated = syncer.status()
        self.assertTrue(st_updated["storage_mounted"])
        self.assertEqual(st_updated["persisted_conversations"], 1)
        self.assertEqual(st_updated["persisted_cache_files"], 1)

    def test_cli_subcommands(self):
        syncer_storage = self.storage_dir
        syncer_userdata = self.userdata_dir
        syncer_home = self.home_dir
        syncer_storage.mkdir(parents=True, exist_ok=True)

        # 1. status CLI
        code = main([
            "--storage-dir", str(syncer_storage),
            "--userdata-dir", str(syncer_userdata),
            "--home-dir", str(syncer_home),
            "status",
        ])
        self.assertEqual(code, 0)

        # 2. sync CLI
        code = main([
            "--storage-dir", str(syncer_storage),
            "--userdata-dir", str(syncer_userdata),
            "--home-dir", str(syncer_home),
            "sync",
        ])
        self.assertEqual(code, 0)

        # 3. hydrate CLI
        code = main([
            "--storage-dir", str(syncer_storage),
            "--userdata-dir", str(syncer_userdata),
            "--home-dir", str(syncer_home),
            "hydrate",
        ])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
