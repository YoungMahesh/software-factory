# Factory Studio GitHub Issue Drawer and Unified Dispatch

**Status**: Accepted

To enable developers to discover, triage, and implement GitHub issues directly within Factory Studio without leaving the workspace, we decided to implement the **Studio Issue Drawer** with dual execution paths (conversational **Grill & Align** vs. direct **Instant Dispatch**) and Unified Studio Sandbox branch binding.

## Considered Options

- **Tabbed Left Panel (Replacing Chat Timeline)**: Swapping out the chat history for an issues list in the left panel. Rejected because it interrupts active conversational turns and loses immediate visibility into the ongoing Grilling Assistant frontier.
- **Dedicated Modal Overlay Dialog**: Presenting issues in a centralized modal. Rejected because it blocks simultaneous inspection of the Live Preview iframe and obscures active stage progress badges.
- **Studio Issue Drawer with Dual Action Paths**: A non-disruptive slide-over drawer (consistent with `ActivityDrawer`) opened from the top control bar with an open issue count badge. Provides issue inspection, dependency alerts, milestone grouping, and dual execution actions ("Grill & Align" to seed the Grilling Assistant vs. "Instant Dispatch" for fast builds). Accepted.

## Consequences

- The canonical term **Studio Issue Drawer** is recorded in `CONTEXT.md`.
- **UI Components & Interactions**:
  - `StudioView` adds an "Issues" button with an open issue badge to the top control bar.
  - `IssueDrawer` (`factory/ui/frontend/src/components/IssueDrawer.tsx`) renders issues grouped by GitHub Milestone (plus an unassigned backlog section), filterable by state (`open`, `closed`, `all`) and searchable by title/number.
  - Blocked issues (`Blocked by: #...`) and active in-progress issues (`factory:claimed`) disable "Instant Dispatch" with visual explanation, while allowing "Grill & Align".
  - Milestone group headers offer a "Run Milestone" button protected by a pre-flight confirmation popover.
  - Clicking "Grill & Align" closes the drawer and sends the issue's full specification to `/api/studio/prompt` (`grill=true`), immediately engaging the Grilling Assistant.
- **Backend Dispatch Seam**:
  - `POST /api/studio/dispatch` is introduced to handle direct issue and milestone dispatches.
  - Binds execution to the Unified Studio Sandbox (`_ensure_sandbox_and_dispatch_job`), sets target branch (`factory/<milestone-slug>` or `factory/issue-<number>`), and reflects hot updates in the Live Preview iframe.
  - Persists a structured dispatch card into SQLite Studio Database (`chat_messages`) so the action is durably visible in the conversational timeline.
- **Data Freshness**:
  - Managed via TanStack Query (`studioQueryKeys.issues(repo)`), invalidated automatically on drawer open, job completion, and via manual refresh.
