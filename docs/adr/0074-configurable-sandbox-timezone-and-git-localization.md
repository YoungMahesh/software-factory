# Configurable Sandbox Timezone and Git Localization

**Status**: Accepted (Amends [ADR 0054](0054-codebase-de-hardcoding-and-parameterization.md) and [ADR 0066](0066-multi-tier-git-identity-and-env-store-separation.md))

We introduce configurable sandbox timezone management across Modal sandboxes and developer workflows, allowing global timezone configuration via `DEFAULT_TIMEZONE` in `.env` (defaulting to Indian Standard Time, `Asia/Kolkata`), ambient `TZ` fallback, and repository-specific overrides via `env-store`, ensuring Git commits, `git log`, and background daemons natively reflect the developer's designated timezone.

## Context

Modal sandboxes run on Ubuntu 24.04 container images which default to UTC (`Etc/UTC`). Previously:
1. **Unconfigured System Timezone**: Containers ran without `TZ` or custom `/etc/localtime` configuration. System logs, cron jobs, background processes, and interactive shells operated exclusively in UTC.
2. **Git Commit Timestamps in UTC**: When commits were authored inside sandboxes (e.g. automated repository initialization in `shared/startup.sh`, or developer commits via T3 Code Web UI or terminal), Git checked the unconfigured system clock and recorded an offset of `+0000` (UTC).
3. **Git Log Formatting Discrepancies**: Developers operating in Indian Standard Time (IST) or other regional timezones had to manually decipher UTC commit dates, and `git log` presented UTC timestamps without local conversion.
4. **Lack of Configuration Seam**: There was no setting in the project `.env` file or `sandbox/config.py` to customize the container timezone.

## Decisions

1. **Declarative Timezone Configuration (`DEFAULT_TIMEZONE`)**:
   - Introduce `DEFAULT_TIMEZONE=Asia/Kolkata` in `.env` and `.env.example`.
   - In `sandbox/config.py`, export `DEFAULT_TIMEZONE` (falling back to ambient `os.environ["TZ"]` or `"Asia/Kolkata"`).
   - In `resolve_factory_credentials`, parse `DEFAULT_TIMEZONE` and `TZ` and mutate `os.environ` when present.

2. **Multi-Tier Timezone Precedence**:
   - **Tier 1 (Repository Override)**: Stored in `<repo>/git.env` or `<repo>/default.env` within the Central Environment Store (`env-store`). If a repository provides a `TZ` variable, it takes highest precedence for that sandbox.
   - **Tier 2 (Global Default Timezone)**: Configured via `DEFAULT_TIMEZONE` (or host `TZ`) in `.env` / environment.
   - **Tier 3 (Default Fallback)**: `Asia/Kolkata` (IST, UTC+05:30).

3. **Container System Clock & Environment Propagation**:
   - In `sandbox/launcher.py`, inject resolved `TZ` and `DEFAULT_TIMEZONE` into `modal.Sandbox.create(..., env=env)`.
   - In `shared/startup.sh`, initialize system clock localization during early boot:
     ```bash
     TARGET_TZ="${TZ:-${DEFAULT_TIMEZONE:-Asia/Kolkata}}"
     export TZ="$TARGET_TZ"
     grep -qxF "export TZ=\"$TARGET_TZ\"" ~/.bashrc 2>/dev/null || echo "export TZ=\"$TARGET_TZ\"" >> ~/.bashrc
     grep -qxF "TZ=\"$TARGET_TZ\"" /etc/environment 2>/dev/null || echo "TZ=\"$TARGET_TZ\"" >> /etc/environment
     if [ -f "/usr/share/zoneinfo/$TARGET_TZ" ]; then
         ln -sf "/usr/share/zoneinfo/$TARGET_TZ" /etc/localtime 2>/dev/null || true
         echo "$TARGET_TZ" > /etc/timezone 2>/dev/null || true
     fi
     ```

4. **Declarative Git Log Formatting**:
   - In `shared/gitconfig`, configure:
     ```ini
     [log]
         date = format-local:%a %b %d %H:%M:%S %Y %z
     ```
   - This ensures `git log` renders all commit timestamps in the container's designated local timezone with explicit timezone offset (e.g. `+0530`), while newly created commits natively record the local offset.

## Consequences

- **Localized Git Commits**: Commits created inside sandboxes are stamped with the developer's configured timezone and offset (`+0530` for IST).
- **Consistent Git Log Output**: Historical and newly authored commits are displayed cleanly in the local timezone when inspecting `git log`.
- **Seamless Reconfigurability**: Developers can switch timezones at any time by updating `DEFAULT_TIMEZONE` in `.env` without modifying container scripts or code.
- **Universal File Line Budget**: All files remain strictly within the $\le 500$ physical line limit.
