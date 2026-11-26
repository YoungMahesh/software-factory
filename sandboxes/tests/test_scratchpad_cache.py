"""Tests for FactoryStateStore and FactoryStateClient Scratchpad Catalog Cache seam."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

from sandbox.apps import CachedScratchpadNote, FactoryStateStore
from sandbox.apps._state_rpc import FactoryStateClient, dispatch_state_operation


class TestScratchpadCatalogCacheStore(unittest.TestCase):
    """Tests persisted Scratchpad Catalog Cache and Factory State Authority RPC parity."""

    def test_store_persists_ideas_raw_and_prunes_stale_bodies_on_refresh(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_vol = MagicMock()
            store = FactoryStateStore(root_dir=Path(tmpdir), volume=mock_vol)

            empty = store.get_scratchpad_catalog()
            self.assertEqual(empty.ideas, [])
            self.assertEqual(empty.raw, [])
            self.assertEqual(empty.bodies, {})

            idea = CachedScratchpadNote(
                section="ideas",
                filename="plan.md",
                slug="plan",
                path="scratchpad/plan.md",
                title="My Exact Title",
                sha="sha-1",
                size=25,
            )
            raw = CachedScratchpadNote(
                section="raw",
                filename="dump.md",
                slug="dump",
                path="raw/dump.md",
                title="Dump",
                sha="r-1",
                size=10,
            )
            store.record_scratchpad_commit("org/config", idea, "# My Exact Title\n\nBody\n")
            store.record_scratchpad_commit("org/config", raw, "raw body\n")

            loaded = store.get_scratchpad_catalog()
            self.assertEqual(len(loaded.ideas), 1)
            self.assertEqual(len(loaded.raw), 1)
            self.assertIn("scratchpad/plan.md", loaded.bodies)
            self.assertIn("raw/dump.md", loaded.bodies)

            # Refresh with unchanged idea SHA and updated raw SHA + dropped file
            refreshed = store.save_scratchpad_catalog(
                "org/config",
                "2026-11-26T17:00:00+00:00",
                [idea.model_copy(update={"title": "Plan"})],
                [raw.model_copy(update={"sha": "r-2"})],
            )
            self.assertEqual(refreshed.ideas[0].title, "My Exact Title")
            self.assertIn("scratchpad/plan.md", refreshed.bodies)
            self.assertNotIn("raw/dump.md", refreshed.bodies)

            # Switching config_repo resets prior bodies
            switched = store.save_scratchpad_catalog("other/config", "2026-11-26T17:01:00+00:00", [], [])
            self.assertEqual(switched.bodies, {})
            self.assertGreaterEqual(mock_vol.commit.call_count, 3)

    def test_factory_state_client_seam_handles_all_scratchpad_operations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FactoryStateStore(root_dir=Path(tmpdir))
            client = FactoryStateClient(lambda op, args, kwargs: dispatch_state_operation(store, op, args, kwargs))

            raw_note = CachedScratchpadNote(
                section="raw",
                filename="log.md",
                slug="log",
                path="raw/log.md",
                title="Log",
                sha="s1",
                size=7,
            )
            client.save_scratchpad_catalog("org/config", "2026-11-26T17:00:00+00:00", [], [raw_note])
            client.cache_scratchpad_body("org/config", raw_note, "raw log")
            client.record_scratchpad_commit(
                "org/config",
                CachedScratchpadNote(
                    section="ideas",
                    filename="arch.md",
                    slug="arch",
                    path="scratchpad/arch.md",
                    title="Arch",
                    sha="s2",
                    size=12,
                ),
                "# Arch\n\nOk\n",
            )

            catalog = client.get_scratchpad_catalog()
            self.assertEqual([n.filename for n in catalog.ideas], ["arch.md"])
            self.assertEqual([n.filename for n in catalog.raw], ["log.md"])
            self.assertEqual(catalog.bodies["raw/log.md"].content, "raw log")
            self.assertEqual(catalog.bodies["scratchpad/arch.md"].content, "# Arch\n\nOk\n")


if __name__ == "__main__":
    unittest.main()
