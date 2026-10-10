# 05: Factory Studio Split-Pane UI and Dual-View Navigation

**What to build:** An interactive, Lovable-style web workspace with seamless navigation switching between Studio View (chat sidebar + live preview iframe) and Console View (parameter controls + live terminal logs), maintaining synchronized active job tracking, milestone stepper progress, and responsive preview controls within a single-page application.

**Blocked by:** 01: Dedicated Port 3010 and HTTP Basic Auth Security, 02: TanStack Start Template Repository Provisioning, 03: Fast Intent Guard and Conversational Ticket Orchestration, 04: In-Sandbox Dev Server Keep-Alive Daemon

**Status:** resolved

- [x] Top navigation header includes an interactive view toggle between `[🎨 Studio]` and `[📟 Console]` without page reloads.
- [x] Studio View provides a left sidebar containing a project selector dropdown with `+ New App` modal, conversation history, and a prompt input bar.
- [x] Submitting a prompt in Studio View displays the conversational message, handles real-time response states, and shows strict refusal messages for non-frontend requests.
- [x] Studio View provides a right workspace embedding an interactive live preview `<iframe>` pointing to `https://3000.mahesh0.dev` with URL bar, manual reload, and device viewport toggles (Desktop, Tablet, Mobile).
- [x] A compact floating status badge displays the active assembly line stage with a one-click shortcut to inspect live logs in Console View.
- [x] Console View maintains full existing functionality (parameter dispatch form, milestone stepper, SSE terminal streaming, Cancel Run button).
- [x] Both views share active job state, active timers, and live SSE event streams seamlessly.
- [x] Web interface tests and template rendering tests verify both views, interactive toggling, and authentication compatibility.

## Answer

Resolved by implementing the split-pane Factory Studio and unified dual-view Single-Page Application (SPA):

1. **Top Navigation Header & View Switcher (`factory/ui/templates/index.html`)**:
   - Added interactive view toggles in the top navigation bar (`[🎨 Studio]` and `[📟 Console]`).
   - Integrated client-side view switching (`switchView('studio')` / `switchView('console')`) toggling between `#studio-view` and `#console-view` without page reloads or loss of active connection state.
2. **Studio View Split-Pane Workspace (`factory/ui/templates/index.html`)**:
   - **Left Sidebar**:
     - Embedded project selector dropdown (`#studio-select-repo`) synchronized with GitHub test repositories and TanStack Start templates.
     - Added `+ New App` trigger button and modal dialog (`#modal-new-app`) to provision new repositories from `software-factory-09-test/tanstack-start-template` via `POST /api/studio/repos`.
     - Added scrollable conversation history (`#studio-chat-history`) rendering user messages, real-time evaluating states, structured job dispatch cards, and strict refusal messages when non-frontend constraints are violated.
     - Embedded prompt input bar (`#studio-prompt-form`, `#studio-prompt-input`, `#btn-studio-send`) submitting requests to `POST /api/studio/prompt`.
   - **Right Workspace & Live Preview Frame**:
     - Embedded live preview `<iframe>` (`#preview-frame`) pointing to `https://3000.mahesh0.dev`.
     - Added preview header toolbar with viewport size toggles (`Desktop` at 100%, `Tablet` at 768px, `Mobile` at 375px), live SSL URL bar indicator, manual reload button, and external tab link.
3. **Compact Floating Status Badge & Shared Execution State (`factory/ui/templates/index.html`)**:
   - Implemented compact floating status badge (`#studio-floating-status-badge`) in Studio View reflecting active assembly line stages (Provisioning, Preflight, Planner, Coder, Verifier, Reviewer, Gate, Serving).
   - Added one-click shortcut (`[📟 Inspect Logs]`) on the floating status badge instantly switching view to Console View for live terminal inspection.
   - Connected both views to shared in-memory job state, active timers, emergency cancellation, and SSE event streaming.
4. **Console View Preservation (`factory/ui/templates/index.html`)**:
   - Maintained 100% of existing Console View capabilities: launch configuration form, milestone/issue discovery, stepper progress, live SSE terminal streaming with auto-scroll and clipboard copy, and historical test runs drawer.
5. **Automated Unit & Integration Verification (`tests/test_ui.py`)**:
   - Added `TestStudioSplitPaneAndDualView` verifying view toggle headers, sidebar project selectors, modal components, conversation containers, preview iframes, viewport controls, and floating status badge rendering.
   - Verified template rendering of repository options in both views and recent test runs in the history drawer.
   - Verified HTTP Basic Authentication enforcement across views and Studio APIs.
