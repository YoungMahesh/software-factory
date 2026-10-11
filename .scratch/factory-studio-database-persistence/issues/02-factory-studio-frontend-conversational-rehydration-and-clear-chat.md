# 02: Factory Studio Frontend Conversational Rehydration and Clear Chat Controls

**What to build:**
Rehydrate the Factory Studio chat timeline directly from the database using TanStack Query so that conversation turns, question frontiers, user answers, and approved plan cards survive browser page refreshes and automatically switch when selecting different target repositories in the header. Add a "Clear Chat" action in the prompt composer toolbar to allow developers to clear conversational context when starting a new feature while preserving all past jobs.

**Blocked by:** 01: Studio Database Engine, Chat Persistence, and Registry Write-Through

**Status:** resolved

- [x] API client functions `fetchChatMessages(repo)` and `clearChatMessages(repo)` are implemented in `factory/ui/frontend/src/api.ts`.
- [x] TanStack Query hooks `useChatMessagesQuery(repo)` and `useClearChatMessagesMutation()` are defined under `studioQueryKeys.messages(repo)` in `factory/ui/frontend/src/hooks/useStudioQueries.ts`.
- [x] When Factory Studio loads or when the developer switches repositories in the header, the chat timeline (`AppContent` / `StudioView`) automatically hydrates the historical messages from the database.
- [x] Optimistic state updates and query cache synchronization ensure new user prompts and assistant interview responses render immediately and persist.
- [x] A "Clear Chat" button in the `PromptComposer` toolbar invokes the clear mutation, wiping the active repository's chat timeline with visual confirmation.
- [x] React Testing Library tests in `factory/ui/frontend/src/App.test.tsx` verify initial timeline hydration on repository selection, optimistic rendering of submitted prompts, and successful chat clearing.

## Answer

Implemented Factory Studio frontend conversational rehydration and Clear Chat controls using TanStack Query and SQLite REST persistence:

1. **API Client & Type Definitions (`factory/ui/frontend/src/api.ts`, `types.ts`)**:
   - Added `DbChatMessage` interface matching backend SQLite schema.
   - Implemented `fetchChatMessages(repo)` (`GET /api/studio/repos/{repo}/messages`) and `clearChatMessages(repo)` (`DELETE /api/studio/repos/{repo}/messages`).

2. **TanStack Query Hooks (`factory/ui/frontend/src/hooks/useStudioQueries.ts`)**:
   - Extended `studioQueryKeys` with `messages: (repo: string) => ["studio", "messages", repo]`.
   - Implemented `useChatMessagesQuery(repo)` for durable cached timeline loading.
   - Implemented `useClearChatMessagesMutation()` with cache resetting and invalidation under `studioQueryKeys.messages(repo)`.

3. **Message Hydration & Model Transformation (`factory/ui/frontend/src/utils.ts`)**:
   - Implemented `convertDbMessageToChatMessage` converting raw database records (user prompts, intent refusals, grilling rounds, approved plan cards, and dispatched jobs) into typed frontend `ChatMessage` representations with milliseconds timestamps and structured turn data.

4. **Timeline Rehydration & Optimistic Sync (`factory/ui/frontend/src/App.tsx`, `StudioView.tsx`)**:
   - Chat timeline automatically hydrates from the database upon application load or switching repositories in the header.
   - Optimistic state updates render submitted prompts immediately in the chat timeline while synchronizing TanStack Query cache (`queryClient.setQueryData`).
   - Responses (refusals, grilling interview turns, approved plan cards, and dispatched jobs) update both UI state and query cache.

5. **Prompt Composer Toolbar & Clear Chat Controls (`factory/ui/frontend/src/components/PromptComposer.tsx`)**:
   - Added "Clear Chat" button with trash icon and disabled states when input is locked or clearing.
   - Integrated visual confirmation badges (`data-testid="clear-chat-confirmation"` in PromptComposer and `data-testid="chat-cleared-banner"` in StudioView).

6. **Comprehensive Test Verification**:
   - Added tests in `src/hooks/useStudioQueries.test.tsx` verifying query key and hooks.
   - Added tests in `src/utils.test.ts` verifying DB record conversion across all message types.
   - Added tests in `src/components/ModalsAndComposer.test.tsx` and `src/views/StudioView.test.tsx` verifying Clear Chat UI and visual confirmations.
   - Added integration tests in `src/App.test.tsx` verifying initial timeline hydration on repository selection, optimistic rendering of submitted prompts, and successful chat clearing with visual confirmation.
   - All 21 frontend test suites (108 tests) and 238 python tests pass with 100% success.

