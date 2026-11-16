# XFCE Desktop Environment and Google Chrome in VM Sandboxes

**Status**: Accepted (Amends [ADR 0008](0008-unified-base-image-for-standard-and-vm-sandboxes.md), [ADR 0009](0009-prebaked-chrome-for-browser-mcp-tooling.md), [ADR 0012](0012-prebaked-cloudflared-and-default-tunnel-ingress.md), and [ADR 0031](0031-migrate-vm-runtime-to-modal-stable-runtime.md))

We establish first-class support for an XFCE 4 desktop environment with TigerVNC, noVNC, and Google Chrome in Modal VM Sandboxes via the `--xfce` CLI flag, enabling instant graphical desktop interaction directly in web browsers over Cloudflare Ingress.

## Context

Modal sandboxes provide isolated cloud execution environments for terminal and agent workflows. Certain development and testing tasks—such as visual end-to-end debugging, browser extension testing, interactive frontend inspection, and cross-platform desktop UI development—require a complete graphical desktop environment with an interactive web browser.

Historically:
1. Sandboxes lacked X11 and desktop window managers out of the box, requiring manual `apt install` cycles (~60–90 seconds) on every boot.
2. Running Google Chrome under root in container environments failed with sandbox permission restrictions (`Running as root without --no-sandbox is not supported`).
3. Launching Google Chrome from the desktop application menu (`Applications -> Internet -> Google Chrome`) failed because standard `.desktop` shortcuts did not include root bypass flags (`--no-sandbox --disable-dev-shm-usage`).
4. TigerVNC's Perl wrapper (`/usr/share/perl5/TigerVNC/Wrapper.pm`) prematurely unlinked temporary password directories on process backgrounding (`CLEANUP => 1`), causing authentication crashes when launched via background daemons.
5. Ingress for graphical interfaces required complex SSH port-forwarding tunnels or unauthenticated public exposure.

## Decisions

1. **First-Class `--xfce` Flag Implying VM Sandbox Mode**:
   - Added `--xfce`, `--xfce-port`, and `--xfce-password` flags to `modal-sandbox` and `LaunchRequest`.
   - `--xfce` automatically implies and enforces VM Sandbox mode (`vm=True`) to provide burstable RAM up to 16 GB, `/dev/shm` access, and full Linux kernel compatibility required for X11, desktop daemons, and Google Chrome.

2. **Pre-Baked Image Layering (`shared/image.py`)**:
   - When `xfce=True`, `build_sandbox_image` bakes XFCE 4, `xfce4-terminal`, `dbus-x11`, `tigervnc-standalone-server`, `tigervnc-tools`, `novnc`, `websockify`, `xdotool`, and `scrot` into the image.
   - Google Chrome (`google-chrome-stable`) is downloaded and installed into the image layer at build time, eliminating runtime apt delays.

3. **Baking in TigerVNC and Root Chrome Fixes**:
   - TigerVNC's Perl wrapper is patched during image creation: `sed -i 's/CLEANUP => 1/CLEANUP => 0/' /usr/share/perl5/TigerVNC/Wrapper.pm`.
   - Chrome's root execution wrapper is patched: `sed -i 's|"$HERE/chrome"|"$HERE/chrome" --no-sandbox --disable-dev-shm-usage|' /opt/google/chrome/google-chrome`.
   - The desktop menu launcher is patched: `sed -i 's|Exec=/usr/bin/google-chrome-stable|Exec=/usr/bin/google-chrome-stable --no-sandbox --disable-dev-shm-usage|' /usr/share/applications/google-chrome.desktop`.

4. **Default Port 3000 Ingress via Cloudflare Tunnel**:
   - noVNC websockify bridge defaults to port 3000 (`DEFAULT_XFCE_PORT`), automatically monitored by `cloudflared-port-watcher` in `shared/startup.sh`.
   - `/usr/share/novnc/index.html` redirects automatically to `vnc.html?autoconnect=true&resize=remote`, providing instant browser desktop loading upon visiting the public Cloudflare URL.
   - Defaults to passwordless access (`SecurityTypes=None`) while supporting an opt-in `--xfce-password` flag for authenticated VNC sessions.

5. **Modular Desktop Service Daemon (`/usr/local/bin/desktop-service`)**:
   - Encapsulated lifecycle script managing `start`, `stop`, `restart`, `status`, and `password` operations for TigerVNC and websockify.
   - Staged into the shared base image and automatically started on boot when `ENABLE_XFCE=1`.

## Consequences

- Engineers can launch a full cloud desktop with Google Chrome in seconds using a single command: `modal-sandbox --name my-box --xfce`.
- Clicking the Cloudflare tunnel URL opens an interactive, auto-resizing XFCE 4 desktop session in any browser without installing local VNC clients.
- Google Chrome launches reliably from both command line and the XFCE application menu under root without crashes or sandbox permission errors.
