#!/usr/bin/env node
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { validateAdminToken } from "../services/admin-token";
import { ensureSystemReady } from "../services/bootstrap";
import { createNeonMcpServer } from "./server";

/**
 * Parses the admin token from command line arguments or environment variables.
 * Supported:
 * --token <token>
 * --token=<token>
 * ADMIN_TOKEN env var
 * NEON_ADMIN_TOKEN env var
 */
export function parseCliToken(): string | null {
	const args = process.argv.slice(2);
	for (let i = 0; i < args.length; i++) {
		if (args[i] === "--token" && i + 1 < args.length) {
			return args[i + 1];
		}
		if (args[i].startsWith("--token=")) {
			return args[i].slice("--token=".length);
		}
	}
	return process.env.ADMIN_TOKEN || process.env.NEON_ADMIN_TOKEN || null;
}

export async function runStdioServer() {
	const token = parseCliToken();

	if (!token || !(await validateAdminToken(token))) {
		console.error(
			"Error: Unauthorized. Valid Admin Token required via --token <token> or ADMIN_TOKEN environment variable.",
		);
		process.exit(1);
	}

	await ensureSystemReady().catch(() => {});

	const server = createNeonMcpServer();
	const transport = new StdioServerTransport();

	await server.connect(transport);
}

// Auto-run when executed as main CLI script
const isMainModule =
	import.meta.url === `file://${process.argv[1]}` ||
	process.argv[1]?.endsWith("stdio.ts") ||
	process.argv[1]?.endsWith("stdio.js");

if (isMainModule) {
	runStdioServer().catch((err) => {
		console.error("Fatal MCP stdio error:", err);
		process.exit(1);
	});
}
