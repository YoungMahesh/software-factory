# 06: Factory Studio Activity Drawer & Inline Disclosures

**What to build:** The complete agent observability experience within Factory Studio. In the conversational chat column on the left, assistant message bubbles display inline pulsating thought disclosures ("Thinking...") and compact step chips for executed tools (e.g. `[Ran test]`, `[Edited index.tsx]`). Clicking any step chip or the header status badge opens a full-height slide-over Agent Activity drawer displaying the complete command timeline, diff previews, and raw logs, allowing developers to inspect autonomous execution deeply without leaving Factory Studio or losing context on the live app preview.

**Blocked by:** 02: Real-Time LLM Reasoning & Thinking Accordion, 03: Command Execution Timeline & Windowed Output

**Status:** closed

- [x] In Factory Studio (`factory/ui/templates/index.html`), the active assistant message stream renders an inline pulsating thought disclosure that streams LLM thinking deltas.
- [x] As tool commands complete, step chips (e.g., `[Ran bash: pnpm test]`, `[Edited src/routes/index.tsx]`) append sequentially inside the assistant turn container.
- [x] A slide-over "Agent Activity" drawer component exists in the Factory Studio view, initially hidden.
- [x] An "Activity" button on the floating status badge and clicking any tool chip slides open the drawer from the right or left edge.
- [x] The slide-over drawer subscribes to the same `/api/jobs/{id}/stream` SSE events, rendering the full command timeline, accordions, and synchronized terminal logs.
- [x] Closing the drawer smoothly returns full view to the chat column and live TanStack Start app preview iframe.
- [x] Tests verify that Studio chat turns render inline thinking disclosures and that the slide-over drawer correctly syncs with SSE event streams.
