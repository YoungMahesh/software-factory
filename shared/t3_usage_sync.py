#!/usr/bin/env python3
"""T3 Code persistent usage and transcript synchronizer.

Synchronizes conversation databases, SQLite state, and usage scan caches
between the live sandbox filesystem (/root/.t3/userdata) and a persistent
Modal Volume mounted at /root/.t3-storage.
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import shutil
import signal
import sys
import time
from typing import Any

logger = logging.getLogger("t3-usage-sync")

DEFAULT_STORAGE_DIR = Path(os.environ.get("T3_STORAGE_DIR", "/root/.t3-storage"))
DEFAULT_USERDATA_DIR = Path(os.environ.get("T3_USERDATA_DIR", "/root/.t3/userdata"))
DEFAULT_INTERVAL_SECS = int(os.environ.get("T3_SYNC_INTERVAL", "30"))


def _atomic_copy_file(src: Path, dst: Path) -> bool:
    """Atomically copies src to dst if src is missing or newer, returning True if updated."""
    try:
        if not src.is_file():
            return False

        if dst.is_file():
            src_stat = src.stat()
            dst_stat = dst.stat()
            if src_stat.st_mtime <= dst_stat.st_mtime and src_stat.st_size == dst_stat.st_size:
                return False

        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp_dst = dst.with_name(f"{dst.name}.tmp.{os.getpid()}")
        shutil.copy2(src, tmp_dst)
        tmp_dst.replace(dst)
        return True
    except Exception as exc:
        logger.warning("Failed to copy %s to %s: %s", src, dst, exc)
        return False


class T3UsageSync:
    """Synchronizes T3 Code historical usage, caches, and transcripts with persistent volume storage."""

    def __init__(
        self,
        storage_dir: Path | str = DEFAULT_STORAGE_DIR,
        userdata_dir: Path | str = DEFAULT_USERDATA_DIR,
        sync_interval: int = DEFAULT_INTERVAL_SECS,
        home_dir: Path | str | None = None,
    ) -> None:
        self.storage_dir = Path(storage_dir)
        self.userdata_dir = Path(userdata_dir)
        self.interval = sync_interval
        self.home_dir = Path(home_dir) if home_dir else Path.home()
        self._running = True

        self.storage_conversations = self.storage_dir / "conversations"
        self.storage_cache = self.storage_dir / "cache"
        self.storage_claude = self.storage_dir / "claude"
        self.storage_codex = self.storage_dir / "codex"
        self.storage_opencode = self.storage_dir / "opencode"

    def ensure_storage_dirs(self) -> None:
        """Ensures all volume storage directories exist."""
        for d in [
            self.storage_conversations,
            self.storage_cache,
            self.storage_claude,
            self.storage_codex,
            self.storage_opencode,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def find_live_antigravity_conv_dirs(self) -> list[Path]:
        """Locates active Antigravity ACP conversation directories."""
        dirs: list[Path] = []
        p1 = self.userdata_dir / "providers" / "antigravity"
        if p1.is_dir():
            for child in p1.iterdir():
                acp_conv = child / "antigravity-acp" / "conversations"
                if acp_conv.is_dir() and acp_conv not in dirs:
                    dirs.append(acp_conv)

        gemini_acp = self.home_dir / ".gemini" / "antigravity-acp" / "conversations"
        if gemini_acp.is_dir() and gemini_acp not in dirs:
            dirs.append(gemini_acp)

        gemini_cli = self.home_dir / ".gemini" / "antigravity-cli" / "conversations"
        if gemini_cli.is_dir() and gemini_cli not in dirs:
            dirs.append(gemini_cli)

        return dirs

    def hydrate(self) -> dict[str, int]:
        """Hydrates persistent storage into the live sandbox environment."""
        if not self.storage_dir.is_dir():
            logger.info("Storage directory %s not found; skipping hydration", self.storage_dir)
            return {"caches": 0, "conversations": 0, "transcripts": 0}

        self.userdata_dir.mkdir(parents=True, exist_ok=True)
        counts = {"caches": 0, "conversations": 0, "transcripts": 0}

        # 1. Restore caches
        if self.storage_cache.is_dir():
            for cache_file in self.storage_cache.glob("usage-*.json"):
                target = self.userdata_dir / cache_file.name
                if _atomic_copy_file(cache_file, target):
                    counts["caches"] += 1

        # 2. Restore historical Antigravity conversations
        if self.storage_conversations.is_dir():
            live_dirs = self.find_live_antigravity_conv_dirs()
            if not live_dirs:
                default_target = self.home_dir / ".gemini" / "antigravity-acp" / "conversations"
                default_target.mkdir(parents=True, exist_ok=True)
                live_dirs = [default_target]

            for db_file in self.storage_conversations.glob("*.db*"):
                for target_dir in live_dirs:
                    target_file = target_dir / db_file.name
                    if _atomic_copy_file(db_file, target_file):
                        counts["conversations"] += 1

        # 3. Restore Claude transcripts
        if self.storage_claude.is_dir():
            claude_projects = self.home_dir / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)
            for f in self.storage_claude.glob("**/*"):
                if f.is_file():
                    rel = f.relative_to(self.storage_claude)
                    if _atomic_copy_file(f, claude_projects / rel):
                        counts["transcripts"] += 1

        # 4. Restore Codex transcripts
        if self.storage_codex.is_dir():
            codex_sessions = self.home_dir / ".codex" / "sessions"
            codex_sessions.mkdir(parents=True, exist_ok=True)
            for f in self.storage_codex.glob("**/*"):
                if f.is_file():
                    rel = f.relative_to(self.storage_codex)
                    if _atomic_copy_file(f, codex_sessions / rel):
                        counts["transcripts"] += 1

        # 5. Restore OpenCode databases
        if self.storage_opencode.is_dir():
            opencode_data = self.home_dir / ".local" / "share" / "opencode"
            opencode_data.mkdir(parents=True, exist_ok=True)
            for f in self.storage_opencode.glob("*.db*"):
                if f.is_file():
                    if _atomic_copy_file(f, opencode_data / f.name):
                        counts["transcripts"] += 1

        logger.info(
            "Hydration complete: %d cache files, %d conversations, %d transcripts restored",
            counts["caches"],
            counts["conversations"],
            counts["transcripts"],
        )
        return counts

    def sync(self) -> dict[str, int]:
        """Flushes live sandbox conversations and caches to persistent storage."""
        if not self.storage_dir.is_dir():
            return {"caches": 0, "conversations": 0, "transcripts": 0}

        self.ensure_storage_dirs()
        counts = {"caches": 0, "conversations": 0, "transcripts": 0}

        # 1. Sync scan caches & pricing
        if self.userdata_dir.is_dir():
            for cache_file in self.userdata_dir.glob("usage-*.json"):
                target = self.storage_cache / cache_file.name
                if _atomic_copy_file(cache_file, target):
                    counts["caches"] += 1

        # 2. Sync Antigravity conversations
        live_dirs = self.find_live_antigravity_conv_dirs()
        for ldir in live_dirs:
            for db_file in ldir.glob("*.db*"):
                target = self.storage_conversations / db_file.name
                if _atomic_copy_file(db_file, target):
                    counts["conversations"] += 1

        # 3. Sync Claude transcripts
        claude_projects = self.home_dir / ".claude" / "projects"
        if claude_projects.is_dir():
            for f in claude_projects.glob("**/*"):
                if f.is_file():
                    rel = f.relative_to(claude_projects)
                    if _atomic_copy_file(f, self.storage_claude / rel):
                        counts["transcripts"] += 1

        # 4. Sync Codex transcripts
        codex_sessions = self.home_dir / ".codex" / "sessions"
        if codex_sessions.is_dir():
            for f in codex_sessions.glob("**/*"):
                if f.is_file():
                    rel = f.relative_to(codex_sessions)
                    if _atomic_copy_file(f, self.storage_codex / rel):
                        counts["transcripts"] += 1

        # 5. Sync OpenCode databases
        opencode_data = self.home_dir / ".local" / "share" / "opencode"
        if opencode_data.is_dir():
            for f in opencode_data.glob("*.db*"):
                if f.is_file():
                    if _atomic_copy_file(f, self.storage_opencode / f.name):
                        counts["transcripts"] += 1

        try:
            os.sync()
        except AttributeError:
            pass

        return counts

    def status(self) -> dict[str, Any]:
        """Returns status of persistent storage and live usage state."""
        storage_mounted = self.storage_dir.is_dir()
        conv_count = (
            len(list(self.storage_conversations.glob("*.db*")))
            if self.storage_conversations.is_dir()
            else 0
        )
        cache_count = (
            len(list(self.storage_cache.glob("*.json"))) if self.storage_cache.is_dir() else 0
        )
        live_conv_count = sum(
            len(list(d.glob("*.db*"))) for d in self.find_live_antigravity_conv_dirs()
        )
        live_cache_count = (
            len(list(self.userdata_dir.glob("usage-*.json"))) if self.userdata_dir.is_dir() else 0
        )
        return {
            "storage_dir": str(self.storage_dir),
            "storage_mounted": storage_mounted,
            "persisted_conversations": conv_count,
            "persisted_cache_files": cache_count,
            "live_conversations": live_conv_count,
            "live_cache_files": live_cache_count,
        }

    def run_daemon(self) -> None:
        """Runs the continuous synchronization loop."""
        logger.info(
            "Starting T3 usage sync daemon (storage: %s, userdata: %s, interval: %ds)",
            self.storage_dir,
            self.userdata_dir,
            self.interval,
        )

        def _handle_signal(signum: int, _frame: object) -> None:
            logger.info("Received signal %d; performing final sync and exiting...", signum)
            self._running = False

        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)

        self.hydrate()

        while self._running:
            try:
                self.sync()
            except Exception as exc:
                logger.error("Error during sync cycle: %s", exc)

            for _ in range(self.interval):
                if not self._running:
                    break
                time.sleep(1)

        self.sync()
        logger.info("T3 usage sync daemon stopped.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Synchronize T3 Code usage and transcripts with persistent Modal storage."
    )
    parser.add_argument(
        "--storage-dir",
        default=DEFAULT_STORAGE_DIR,
        type=Path,
        help=f"Path to mounted persistent storage volume (default: {DEFAULT_STORAGE_DIR})",
    )
    parser.add_argument(
        "--userdata-dir",
        default=DEFAULT_USERDATA_DIR,
        type=Path,
        help=f"Path to T3 userdata directory (default: {DEFAULT_USERDATA_DIR})",
    )
    parser.add_argument(
        "--home-dir",
        default=Path.home(),
        type=Path,
        help="Path to home directory (default: current user home)",
    )
    parser.add_argument(
        "--interval",
        default=DEFAULT_INTERVAL_SECS,
        type=int,
        help=f"Sync interval in seconds for daemon mode (default: {DEFAULT_INTERVAL_SECS})",
    )
    parser.add_argument(
        "action",
        nargs="?",
        choices=["hydrate", "sync", "daemon", "status"],
        help="Action to perform (default: daemon if none specified)",
    )
    parser.add_argument("--hydrate", action="store_true", help="Perform a one-time hydration")
    parser.add_argument("--sync", action="store_true", help="Perform a one-time sync")
    parser.add_argument("--daemon", action="store_true", help="Run sync loop as daemon")
    parser.add_argument("--status", action="store_true", help="Print persistent storage status")

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] [t3-usage-sync] %(message)s",
    )

    syncer = T3UsageSync(
        storage_dir=args.storage_dir,
        userdata_dir=args.userdata_dir,
        sync_interval=args.interval,
        home_dir=args.home_dir,
    )

    action = args.action
    if args.status or action == "status":
        stat = syncer.status()
        print("T3 Usage Persistence Status:")
        print(
            f"  Storage Directory:       {stat['storage_dir']} (Mounted: {stat['storage_mounted']})"
        )
        print(f"  Persisted Conversations: {stat['persisted_conversations']}")
        print(f"  Persisted Caches:        {stat['persisted_cache_files']}")
        print(f"  Live Conversations:      {stat['live_conversations']}")
        print(f"  Live Caches:             {stat['live_cache_files']}")
        return 0

    if args.hydrate or action == "hydrate":
        res = syncer.hydrate()
        print(f"Hydrated: {res}")
        return 0

    if args.sync or action == "sync":
        res = syncer.sync()
        print(f"Synced: {res}")
        return 0

    # Default to running daemon
    syncer.run_daemon()
    return 0


if __name__ == "__main__":
    sys.exit(main())
