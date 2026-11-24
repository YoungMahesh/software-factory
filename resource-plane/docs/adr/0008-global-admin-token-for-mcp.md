# Global Admin Token for MCP Authentication

Agent invocations to the MCP server require a single secret Admin Token configured in the server's `.env.local` (or generated on first bootstrap and displayed in the dashboard settings). AI clients provide this token via `Authorization: Bearer <token>` (for HTTP) or via an environment variable / flag (for stdio). This provides protection against unauthorized agent actions while avoiding the overhead of multi-key management.
