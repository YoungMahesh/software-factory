# 01: OpenCode Go Endpoint Configuration and Transparent Error Turns

**What to build:** Reconfigure the Grilling Assistant inference service to target the canonical OpenCode Go base URL, and replace the silent fallback to mock data with explicit, structured error turns. When remote inference fails due to network, SSL, or authentication issues, developers in Factory Studio see a clear error callout banner in the chat timeline with diagnostic details and retry guidance, rather than being confused by synthetic mock questions. Mock execution is restricted strictly to explicit opt-in for testing.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Live inference requests in the grilling service target the canonical OpenCode Go URL (`https://opencode.ai/zen/go/v1`) with authenticated headers.
- [ ] Remote inference failures (network timeouts, SSL mismatches, HTTP errors) return a structured error turn (`type="error"`) instead of silently executing `_handle_mock_turn()`.
- [ ] Error turns are saved into the Studio Chat History database table.
- [ ] Factory Studio chat interface renders an error callout banner in the conversation timeline displaying the failure reason and providing a retry action.
- [ ] Mock mode is restricted strictly to explicit opt-in (`mock=True`), eliminating accidental fallback during normal studio usage.
