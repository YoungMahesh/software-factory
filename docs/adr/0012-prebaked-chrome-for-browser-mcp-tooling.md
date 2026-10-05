# Pre-baked Chrome for Browser MCP Tooling

Previously, `shared/opencode.json` enabled the Playwright and Chrome DevTools MCP servers, but the `Shared Base Image` shipped no browser. Both servers launched on demand and then failed with `Could not find Google Chrome executable for channel 'stable' at /opt/google/chrome/chrome`; neither ran headless, and neither disabled Chrome's sandbox, so they could not start as root in a display-less container. Every agent session saw two dead MCP servers that required manual provisioning. We decided to pre-bake a single headless Google Chrome into a dynamic image layer whenever Browser Tooling is requested, and to launch both MCP servers against that one binary with the flags the sandbox environment requires.

## Considered Options

- **Install Chrome on demand at agent run time**: Leave the servers broken until an agent manually installs a browser. Rejected because it adds download latency and a network dependency to the first browser call, and leaves the MCP servers visibly failing on every fresh sandbox.
- **Two separate browser builds (one per MCP server)**: Use Playwright's bundled Chromium for `playwright` and Puppeteer's Chrome for `chrome-devtools`. Rejected because both servers are only Chrome DevTools Protocol frontends that can share one binary, so two builds would duplicate hundreds of megabytes and two caches for no benefit.
- **Pre-baked shared Google Chrome stable**: Install Google Chrome once via `npx playwright install --with-deps chrome` into a dynamic layer, resolving to `/opt/google/chrome/chrome` — the default `chrome`/`stable` channel both servers look for — and launch both headless with the sandbox disabled. Accepted because it makes both MCP servers work out of the box from a single browser install, reuses Modal's layer cache, and follows the existing pre-baked-toolchain pattern (ADR 0001).
- **Explicit `--browser` flag that is also implied by agent surfaces**: Add a standalone `--browser` flag, and enable it implicitly when `--opencode` or `--agy` is passed. Accepted because browser MCP servers work with existing `--opencode`/`--agy` commands out of the box, while Chrome remains independently provisionable for plain shells, test suites, and other tooling.

## Consequences

- `shared/image.py` gains a `browser` parameter on `build_sandbox_image` and a `browser_enabled(...)` helper; the browser layer runs `npx -y playwright install --with-deps chrome`.
- `standard_sandbox/main.py` and `vm_sandbox/main.py` gain a `--browser` flag; `--opencode` and `--agy` imply it through `browser_enabled`, set `ENABLE_BROWSER=1`, and list `Browser` in the launch banner.
- `shared/startup.sh` prints a Browser Tooling banner and installs the on-demand `check-browser` utility when `ENABLE_BROWSER=1`.
- `shared/opencode.json` launches `playwright` with `--browser chrome --headless --no-sandbox` and `chrome-devtools` with `--headless --chrome-arg=--no-sandbox --chrome-arg=--disable-dev-shm-usage`.
- Sandboxes launched without Browser Tooling (`--browser`, `--opencode`, or `--agy`) do not carry the Chrome layer.
- Chrome tracks latest stable at build time; Modal's layer cache freezes the resolved version until the layer input changes.
