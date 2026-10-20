# 03: In-Sandbox Interactive Terminal in Activity Drawer

**What to build:**
A dedicated "Interactive Terminal" tab in Factory Studio's Activity Drawer powered by xterm.js. The terminal connects over a full-duplex WebSocket (`/api/repos/{repo}/terminal/ws`) directly to Modal's pseudo-terminal execution (`sandbox.exec(pty=True)`), anchored at `/root/{repo}` with an interactive login bash shell. Keystrokes, tab completion, arrow keys, and ANSI escape codes stream with real-time responsiveness, and the terminal canvas dynamically resizes to fit drawer dimensions. When the drawer is closed or the WebSocket disconnects, the backend subshell process terminates immediately to prevent leaked processes. When an autonomous Assembly Line Pipeline job is actively executing, a warning badge alerts the developer of concurrent container operations. `ActivityDrawer.tsx` decomposes the terminal tab into a private child component (`InteractiveTerminalTab.tsx`) to strictly respect the Universal File Line Budget (<= 500 lines).

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] An "Interactive Terminal" tab is added to the Activity Drawer tab bar.
- [ ] Opening the tab mounts an xterm.js terminal emulator with `@xterm/addon-fit` dynamically resizing to the drawer pane.
- [ ] The terminal initiates a full-duplex WebSocket connection to `/api/repos/{repo}/terminal/ws`.
- [ ] The backend WebSocket handler connects to Modal's `sandbox.exec(pty=True)` running an interactive login bash shell in `/root/{repo}` sourcing `/root/.bashrc`.
- [ ] Keystrokes, navigation keys, and control sequences (Ctrl+C, Ctrl+L, Tab autocompletion) operate as a native interactive shell.
- [ ] Disconnecting the WebSocket (closing the drawer or navigating away) immediately terminates the container process.
- [ ] An alert badge in the terminal header warns the developer when an autonomous Assembly Line Pipeline job is actively running in the container.
- [ ] `ActivityDrawer.tsx` remains strictly <= 500 lines, delegating terminal logic to `InteractiveTerminalTab.tsx`.
- [ ] Automated tests verify the WebSocket bridge and frontend component, and the compiled bundle in `factory/ui/static/dist/` is refreshed.
