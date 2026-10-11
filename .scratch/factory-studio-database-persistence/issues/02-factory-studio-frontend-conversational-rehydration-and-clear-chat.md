# 02: Factory Studio Frontend Conversational Rehydration and Clear Chat Controls

**What to build:**
Rehydrate the Factory Studio chat timeline directly from the database using TanStack Query so that conversation turns, question frontiers, user answers, and approved plan cards survive browser page refreshes and automatically switch when selecting different target repositories in the header. Add a "Clear Chat" action in the prompt composer toolbar to allow developers to clear conversational context when starting a new feature while preserving all past jobs.

**Blocked by:** 01: Studio Database Engine, Chat Persistence, and Registry Write-Through

**Status:** ready-for-agent

- [ ] API client functions `fetchChatMessages(repo)` and `clearChatMessages(repo)` are implemented in `factory/ui/frontend/src/api.ts`.
- [ ] TanStack Query hooks `useChatMessagesQuery(repo)` and `useClearChatMessagesMutation()` are defined under `studioQueryKeys.messages(repo)` in `factory/ui/frontend/src/hooks/useStudioQueries.ts`.
- [ ] When Factory Studio loads or when the developer switches repositories in the header, the chat timeline (`AppContent` / `StudioView`) automatically hydrates the historical messages from the database.
- [ ] Optimistic state updates and query cache synchronization ensure new user prompts and assistant interview responses render immediately and persist.
- [ ] A "Clear Chat" button in the `PromptComposer` toolbar invokes the clear mutation, wiping the active repository's chat timeline with visual confirmation.
- [ ] React Testing Library tests in `factory/ui/frontend/src/App.test.tsx` verify initial timeline hydration on repository selection, optimistic rendering of submitted prompts, and successful chat clearing.
