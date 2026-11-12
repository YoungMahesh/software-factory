# T3 Code Browser Headless Shell and Sandbox Environment

**Status**: Accepted (Amends [ADR 0003](0009-prebaked-chrome-for-browser-mcp-tooling.md) and [ADR 0025](0025-t3-code-server-and-agent-control-surface.md))

We pre-bake headless Chromium system libraries and fonts into the Shared Base Image, update `browser_enabled` to treat `--t3` as an active browser capability, pre-initialize T3 Code's browser during image build via `t3 browser setup`, and configure `T3CODE_SERVER_BROWSER_SANDBOX=0` inside the container startup script so T3 Code's built-in browser panel functions seamlessly in root sandbox containers.

## Context

T3 Code (`pingdotgg/t3code`) ships with a dedicated embedded web preview browser in its right panel backed by headless Chromium (`chrome-headless-shell` managed under `/root/.t3/tools/chrome-headless-shell/`).

When developers attempted to open the "Browser" panel inside Modal sandboxes launched with `--t3`, T3 Code failed with:

```text
This server's host is missing libraries its browser needs. Run this once on the host, then try again:
sudo env "PATH=$PATH" t3 browser setup
```

Investigation revealed two root causes:

1. **Missing Dynamic Shared Libraries**: The `base_image` in `shared/image.py` (Ubuntu 24.04) omitted the system libraries and fonts required by headless Chromium/Chrome (`libnspr4`, `libnss3`, `libatk-1.0`, `libatk-bridge2.0`, `libatspi2.0`, `libxcomposite1`, `libxdamage1`, `libxfixes3`, `libxrandr2`, `libgbm1`, `libxkbcommon0`, `libasound2`, `fontconfig`, `fonts-liberation`). When `t3 serve` probed `chrome-headless-shell --version`, the dynamic linker (`ld.so`) failed immediately with `error while loading shared libraries: libnspr4.so`. T3 Code's `PreviewBrowserHost` detected missing libraries via `ldd` and emitted `PreviewBrowserLibrariesError`. Furthermore, `browser_enabled()` only checked `browser`, `opencode`, and `agy`, omitting `t3`.
2. **Root User Sandbox Restriction in Containers**: In Modal container sandboxes, all processes run as `root` (`uid=0`). Chrome's security model forbids starting the Linux zygote sandbox as `root` without `--no-sandbox` (`Running as root without --no-sandbox is not supported`). Without `T3CODE_SERVER_BROWSER_SANDBOX=0` set in the server's environment, T3 Code refuses to start the browser and reports `PreviewBrowserRootError`.

## Decisions

1. **Pre-bake Chrome System Libraries and Fonts in Shared Base Image**:
   - In `shared/image.py`, add `libnss3`, `libatk1.0-0t64`, `libatk-bridge2.0-0t64`, `libatspi2.0-0t64`, `libdbus-1-3`, `libx11-6`, `libxcb1`, `libxcomposite1`, `libxdamage1`, `libxext6`, `libxfixes3`, `libxrandr2`, `libxkbcommon0`, `libgbm1`, `libasound2t64`, `libexpat1`, `fontconfig`, and `fonts-liberation` to `base_image.apt_install()`.
   - Pre-baking these packages into the shared base image ensures zero runtime apt overhead and avoids network latency or transient package repository failures on fresh sandbox boots.

2. **Expand `browser_enabled` to Include `--t3`**:
   - Update `browser_enabled(browser=browser, opencode=opencode, agy=agy, t3=t3)` in `shared/image.py` and `sandbox/launcher.py`. Launching with `--t3` automatically implies browser readiness, activates `ENABLE_BROWSER=1`, and advertises `Browser` in the launch banner.

3. **Pre-validate Browser Setup during Image Build**:
   - In `shared/image.py` under the `if t3:` build layer, invoke `/opt/t3/t3 browser setup`. This ensures T3's browser dependencies are validated and pre-configured at Modal image build time.

4. **Export `T3CODE_SERVER_BROWSER_SANDBOX=0` for Root Containers**:
   - In `shared/startup.sh`, export `T3CODE_SERVER_BROWSER_SANDBOX=0` before `nohup t3 serve ...` and persist it to `/etc/environment` and `~/.bashrc`. This allows Chrome headless shell to execute as `root` without failing on unprivileged user namespace checks.
   - Updated `/usr/local/bin/check-t3` to print the browser sandbox environment state (`T3CODE_SERVER_BROWSER_SANDBOX`).

## Consequences

- The embedded "Browser" panel and preview browser tabs in T3 Code WebUI open immediately without requiring manual `t3 browser setup` execution.
- Sandboxes launched with `--t3` inherit browser tooling out of the box.
- All files remain compliant with universal file line limits (ADR 0027 / AGENTS.md).
