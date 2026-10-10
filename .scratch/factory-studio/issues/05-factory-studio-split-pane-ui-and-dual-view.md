# 05: Factory Studio Split-Pane UI and Dual-View Navigation

**What to build:** An interactive, Lovable-style web workspace with seamless navigation switching between Studio View (chat sidebar + live preview iframe) and Console View (parameter controls + live terminal logs), maintaining synchronized active job tracking, milestone stepper progress, and responsive preview controls within a single-page application.

**Blocked by:** 01: Dedicated Port 3010 and HTTP Basic Auth Security, 02: TanStack Start Template Repository Provisioning, 03: Fast Intent Guard and Conversational Ticket Orchestration, 04: In-Sandbox Dev Server Keep-Alive Daemon

**Status:** ready-for-agent

- [ ] Top navigation header includes an interactive view toggle between `[🎨 Studio]` and `[📟 Console]` without page reloads.
- [ ] Studio View provides a left sidebar containing a project selector dropdown with `+ New App` modal, conversation history, and a prompt input bar.
- [ ] Submitting a prompt in Studio View displays the conversational message, handles real-time response states, and shows strict refusal messages for non-frontend requests.
- [ ] Studio View provides a right workspace embedding an interactive live preview `<iframe>` pointing to `https://3000.mahesh0.dev` with URL bar, manual reload, and device viewport toggles (Desktop, Tablet, Mobile).
- [ ] A compact floating status badge displays the active assembly line stage with a one-click shortcut to inspect live logs in Console View.
- [ ] Console View maintains full existing functionality (parameter dispatch form, milestone stepper, SSE terminal streaming, Cancel Run button).
- [ ] Both views share active job state, active timers, and live SSE event streams seamlessly.
- [ ] Web interface tests and template rendering tests verify both views, interactive toggling, and authentication compatibility.
