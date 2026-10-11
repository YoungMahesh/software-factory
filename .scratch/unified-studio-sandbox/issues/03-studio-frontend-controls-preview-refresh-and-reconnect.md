# 03: Studio Frontend Controls, Preview Refresh & Reconnect

**What to build:** Enforce prompt input locking while an in-sandbox agent turn is active, provide manual and event-driven preview iframe refresh controls, and handle idle container timeouts with an explicit disconnect dialog and seamless branch reconnection.

**Blocked by:** 02: Studio Prompt Endpoint Sandbox Reuse & Auto-Provisioning

**Status:** resolved

- [x] Factory Studio locks prompt input and displays an in-flight status indicator while an in-sandbox assembly line turn is executing, preventing concurrent prompt submissions.
- [x] The LivePreview toolbar includes an explicit "Refresh" button that reloads the preview iframe DOM on demand.
- [x] Factory Studio listens for the `preview_refresh` event on the telemetry stream and automatically triggers an iframe refresh when an agent run finishes.
- [x] When the container reaches its 30-minute idle timeout or enters a stopped state, the UI transitions to a disconnected state and displays an explicit "Sandbox Disconnected" dialog.
- [x] Chat conversation history is fully preserved across container disconnection.
- [x] Clicking "Reconnect Environment" rehydrates a fresh Unified Studio Sandbox tracked to the active remote branch (`origin/factory/<feature>`), attaches the new preview tunnel URL, and re-enables chat input.
- [x] Component and UI integration tests verify input locking, manual/event-driven iframe reload, and the disconnect/reconnect workflow.
