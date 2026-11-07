# Persistent T3 Code Usage, Agent Transcripts, and Scan Caches via Modal Volume

**Status**: Accepted (Amends [ADR 0046](0046-t3-code-server-and-agent-control-surface.md), [ADR 0073](0073-multi-account-antigravity-provider-instances-in-t3-code.md), [ADR 0080](0080-default-antigravity-text-and-source-control-writer-model-in-t3-code.md), and [ADR 0081](0081-modal-tunnel-pairing-url-in-t3-code-cli.md))

We establish persistent storage for T3 Code token usage metrics, conversation databases, and agent transcripts across ephemeral Modal Sandboxes using a dedicated `modal.Volume` (`t3code-usage-v1`) mounted at `/root/.t3-storage` coupled with a lightweight bidirectional synchronization daemon (`t3-usage-sync`).

## Context

Developers launching ephemeral Modal Sandboxes with `--t3` or `--t3code` interact with T3 Code via its WebUI, mobile pairing links, and multi-provider agent harnesses (Antigravity, OpenCode, Claude, Codex). However, upon container termination or sandbox replacement, the entire container filesystem—including all historical conversation SQLite databases, token accounting, and scanner caches—was destroyed.

Inspecting the T3 Code single-executable Node runtime (`/opt/t3/t3`) revealed the exact mechanisms governing token calculation and usage aggregation:

1. **Antigravity Conversation Scanning**: The binary defines `AntigravityUsage.dataRoots = [process.env.ANTIGRAVITY_DATA_DIR ?? defaultPath]`. Pointing `ANTIGRAVITY_DATA_DIR` to `/root/.t3-storage/conversations` instructs T3 Code to discover and parse conversation SQLite databases directly from persistent storage.
2. **Scan & Rate Caches**: T3 Code maintains persistent usage calculation state in `config.stateDir` (`/root/.t3/userdata`):
   - `usage-scan-cache-v9.json`: records SQLite conversation mtimes and aggregated token usage to eliminate re-scanning.
   - `usage-model-rates.json`: caches model pricing metrics.
   Restoring these files prior to starting `t3 serve` enables instant usage dashboard rendering without re-parsing hundreds of conversation steps.
3. **Multi-Agent Transcripts**: Claude projects (`~/.claude/projects`), Codex sessions (`~/.codex/sessions`), and OpenCode databases (`~/.local/share/opencode`) store session state read by their respective usage limit and transcript readers.

## Considered Options

- **Full `/root/.t3/userdata` Mount**: Mounting a Modal Volume over the entirety of `/root/.t3/userdata`. Rejected because `userdata` contains instance-specific runtime locks, ephemeral UNIX domain sockets, PID files, and `server-runtime.json` (which binds ephemeral port numbers and tunnel URLs specific to the active sandbox). Mounting it directly causes cross-sandbox instance corruption.
- **Root Filesystem Snapshots Only**: Capturing snapshots via `--snapshot` and resuming via `--from-snapshot`. Rejected as a sole solution because snapshots are point-in-time images intended for full environment state rather than continuous, automatic accumulation of billing and token metrics across independent project sandboxes.
- **Targeted Modal Volume with Bidirectional Sync Daemon (Approach A)**:
  - Mount a dedicated `modal.Volume` (`t3code-usage-v1`) at `/root/.t3-storage`.
  - Configure `ANTIGRAVITY_DATA_DIR="/root/.t3-storage/conversations"` in the container environment.
  - Execute `t3-usage-sync hydrate` during startup prior to `t3 serve` to populate live caches and historical transcripts.
  - Run `t3-usage-sync daemon` in the background with a 30-second flush interval, atomic file staging (`.tmp.<pid>`), and container exit traps (`trap cleanup_t3 EXIT SIGTERM`) calling `os.sync()`.
  - Provide CLI flags `--t3-usage-volume <name>` and `--no-t3-persist`.
  Accepted.

## Architecture

### Storage Directory Layout (`/root/.t3-storage`)

```text
/root/.t3-storage/
├── conversations/       # Antigravity ACP conversation SQLite DBs (*.db, *.db-wal)
├── cache/               # usage-scan-cache-v9.json, usage-model-rates.json
├── claude/              # Claude agent projects and transcripts
├── codex/               # Codex session JSON files
└── opencode/            # OpenCode session databases
```

### Synchronization Daemon (`shared/t3_usage_sync.py`)

- **Atomic File Writing**: `_atomic_copy_file` compares mtime and size before writing to a temporary file in the target directory and performing an atomic `replace()`, preventing race conditions during concurrent reads by T3 Code.
- **Hydration Phase**: Runs synchronously at container startup in `shared/startup.sh`:
  - Restores `usage-scan-cache-v9.json` and `usage-model-rates.json` into `/root/.t3/userdata`.
  - Restores historical conversation databases and agent transcripts.
- **Flush Phase**: Runs periodically (default: 30s) and synchronously upon `SIGTERM` or process exit:
  - Detects modified SQLite databases and caches in live directories and copies updated files to the volume.
  - Calls `os.sync()` to ensure storage buffers flush to Modal's distributed block layer.

### CLI & Web Configuration

- `--t3-usage-volume <name>`: Customizes the Modal Volume name (defaults to `t3code-usage-v1`).
- `--no-t3-persist`: Disables volume mounting and background synchronization for completely isolated or throwaway sandboxes.
- Both flags are validated against `--snapshot` and ensure `--t3` is active.

## Consequences

- **Usage Continuity**: Developers switching across multiple sandboxes retain historical token consumption and conversation transcripts in the T3 Code sidebar and usage breakdown widgets.
- **Zero Startup Lag**: Pre-hydrated scan caches allow T3 Code to display accurate usage numbers immediately upon boot without CPU-intensive re-indexing.
- **Clean Decoupling**: Factoring `setup_t3` into `sandbox/t3.py` ensures all core codebase files remain strictly within the universal <= 500 lines budget ratchet (ADR 0057 / AGENTS.md).
- **Graceful Shutdown**: The `cleanup_t3` trap in `shared/startup.sh` guarantees that conversations created in the final seconds of sandbox execution are persisted before container termination.
