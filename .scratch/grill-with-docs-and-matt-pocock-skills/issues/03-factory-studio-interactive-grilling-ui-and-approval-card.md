# 03: Factory Studio Interactive Grilling UI and Build Approval Card

**What to build:**
An interactive split-pane conversational experience in Factory Studio where developers can toggle grilling mode, review structured question rounds with recommended answers, inspect proposed Architectural Decision Records (ADRs), and trigger autonomous assembly line execution via an explicit "Approve Plan & Build" action.

**Blocked by:** 02: In-Studio Grilling Assistant and Conversational Turn Service

**Status:** done

- [x] Add a `[x] Grill & Align (Recommended)` checkbox toggle in `PromptComposer`, defaulting to enabled.
- [x] Render assistant interview turns in the chat timeline with formatted question cards, recommended answers, and status badges.
- [x] Display an interactive "Approve Plan & Build" card upon reaching `ready_for_approval`, featuring the finalized plan summary, draft ADR markdown preview, and action button.
- [x] Support text shortcuts (e.g. `/proceed` or `approve`) to trigger build approval directly from chat input.
- [x] Implement `POST /api/studio/approve` to commit the approved draft ADR (e.g. `docs/adr/0002-<slug>.md`) and `CONTEXT.md` to GitHub on branch `factory/<feature>`, create the milestone/issue, and dispatch the Unified Studio Sandbox assembly line.
- [x] Automated frontend tests verify the prompt composer toggle, grilling round rendering, approval card interactions, and build dispatch.

