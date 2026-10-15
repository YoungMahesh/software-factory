# 03: Factory Studio Pull Request UI and In-Studio Merge Controls

**What to build:** Build the frontend components and state hooks in Factory Studio for viewing Feature Pull Request status in the top control bar, inspecting delivery details in the conversational timeline via reactive Delivery Gate Cards, and executing in-Studio squash merges with confirmation dialogs.

**Blocked by:** 01-backend-pull-request-api-and-squash-merge, 02-pipeline-delivery-gate-telemetry

**Status:** resolved

- [x] Add client API functions `fetchPullRequests` and `mergePullRequest` in `factory/ui/frontend/src/api.ts`.
- [x] Add TanStack Query hook `useStudioPullRequestQuery` and query key definitions in `factory/ui/frontend/src/hooks/useStudioQueries.ts`.
- [x] Implement the Pull Request status button in the top control bar of `StudioView.tsx`, displaying status badges (`Draft`, `Ready for Review`, `Merged`, `Conflict`) and a popover with PR details, link to GitHub, and guarded merge trigger.
- [x] Implement the reactive `DeliveryGateCard` component in `factory/ui/frontend/src/components/DeliveryGateCard.tsx` (and in chat timeline in `StudioView.tsx`), rendering PR number, title, resolved issue checklist, verifier test status, and an inline "Merge into main" button with confirmation state.
- [x] Guard merge actions: disable merge button while PR is in `Draft` state or while an assembly line job is actively executing; display a `Conflict` badge with a link to GitHub if conflicts exist.
- [x] In `factory/ui/frontend/src/components/IssueDrawer.tsx`, display the associated Pull Request status badge on milestone headers with an external link.
- [x] Upon successful merge, invalidate PR and issue queries, update the Live Preview branch indicator to `main`, and reflect the merged state across the UI.
- [x] Comprehensive frontend test coverage in `StudioView.test.tsx` and component test suites validating status badging, popover interactions, merge confirmation flow, and preview branch updates.
