# 01: Studio Dispatch API and GitHub Issue Normalization

**What to build:** A dedicated backend dispatch endpoint (`POST /api/studio/dispatch`) and enhanced GitHub issue normalization that allow Factory Studio to launch individual issues or entire milestone batches directly against the Unified Studio Sandbox, binding the target branch (`factory/<milestone-slug>` or `factory/issue-<number>`), updating the live preview URL, and recording a structured dispatch card in the SQLite Studio Database (`chat_messages`).

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] `POST /api/studio/dispatch` endpoint accepts repository name, optional issue number, optional milestone slug/title, model identifier, and VM flag.
- [x] For milestone-associated issues or milestone batches, the endpoint resolves the canonical milestone slug and binds the target branch to `factory/<milestone-slug>`.
- [x] For standalone issues without a milestone, the endpoint binds the target branch to `factory/issue-<number>`.
- [x] Dispatched jobs ensure the Unified Studio Sandbox is running or launched on the target branch in `dev=True` mode and attach the active preview tunnel URL.
- [x] A structured execution card is persisted to the SQLite `chat_messages` table containing the job ID, issue number, milestone slug, target branch, and preview URL.
- [x] GitHub issue normalization extracts milestone metadata (`number`, `title`, `slug`) and parses `Blocked by: #<id>` tokens from the issue body into `blocked_by` lists.
- [x] Full backend test coverage verifies dispatch behavior, branch binding, preview URL attachment, and chat database persistence using an in-memory database.
