# 02: Frontend Studio Turn Rollback UI and Confirmation

**What to build:**
Implement the frontend user interface and reactive state management for Turn Rollback in Factory Studio:
- TypeScript interfaces in `factory/ui/frontend/src/types.ts`: `TurnRollbackData`, `RollbackTurnParams`, `RollbackTurnResponse`.
- API client function in `factory/ui/frontend/src/api.ts`: `rollbackTurn` with React Query mutation hook.
- Dedicated `TurnRollbackCard` component or card renderer in `StudioView.tsx` for `turn_data.type === "turn_rollback"`, displaying commit SHA reversal and restored status.
- `Reverted` status badge on superseded assistant cards in Studio Chat History, visually greying/marking them and disabling approval/merge buttons.
- Inline "Undo Turn" button on `DeliveryGateCard` (disabled when active job is running or PR is merged).
- "Undo Last Turn" action button in `LivePreview.tsx` toolbar (adjacent to branch selector and sync button) and `PromptComposer.tsx` shortcut.
- Accessible confirmation modal dialog detailing issue number, title, target commit SHA, and branch before executing the rollback.
- Visual loading states with disabled buttons and spinners while rollback is in flight, followed by toast notification feedback upon completion.
- Component integration tests in `StudioView.test.tsx`, `LivePreview.test.tsx`, and `DeliveryGateCard.test.tsx`.

**Blocked by:** 01 (needs backend rollback endpoint)

**Status:** resolved
**Triage:** ready-for-agent

- [x] Define `TurnRollbackData`, `RollbackTurnParams`, and `RollbackTurnResponse` in `types.ts`.
- [x] Implement `rollbackTurn` API client method in `api.ts` with React Query mutation.
- [x] Add `TurnRollbackCard` rendering in `StudioView.tsx` for messages with `turn_data.type === "turn_rollback"`.
- [x] Render visual `Reverted` badge on superseded assistant cards and disable duplicate approval/merge buttons when `turn_data.reverted === true`.
- [x] Add inline "Undo Turn" button in `DeliveryGateCard.tsx` with appropriate disabled guards.
- [x] Add "Undo Last Turn" button in `LivePreview.tsx` toolbar and `PromptComposer.tsx`.
- [x] Implement confirmation modal dialog displaying issue title, commit SHA, and branch before confirmation.
- [x] Handle in-flight loading states and display success/error toast notifications.
- [x] Add unit and component integration tests in `StudioView.test.tsx`, `LivePreview.test.tsx`, and `DeliveryGateCard.test.tsx`.
