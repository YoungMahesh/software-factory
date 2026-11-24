# Dual MCP Transport: HTTP and Stdio

To accommodate different AI agent environments, the MCP server supports two transport mechanisms: an HTTP route at `/mcp` (for network/remote agents and web-hooked agent workflows) and a standalone CLI stdio process executable via `pnpm run mcp` (for local desktop AI assistants like Cursor, Claude Desktop, and Antigravity). Both transports share the identical underlying tool registry and control plane actions.
