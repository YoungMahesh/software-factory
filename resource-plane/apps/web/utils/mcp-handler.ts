import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";

import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { JSONRPCMessage } from "@modelcontextprotocol/sdk/types.js";

export async function handleMcpRequest(
	request: Request,
	server: McpServer,
): Promise<Response> {
	try {
		const jsonRpcRequest = (await request.json()) as JSONRPCMessage;

		const [clientTransport, serverTransport] =
			InMemoryTransport.createLinkedPair();

		let responseData: JSONRPCMessage | null = null;

		const hasId =
			jsonRpcRequest &&
			"id" in jsonRpcRequest &&
			typeof jsonRpcRequest.id !== "undefined";

		const responsePromise = hasId
			? new Promise<JSONRPCMessage>((resolve) => {
					clientTransport.onmessage = (message: JSONRPCMessage) => {
						responseData = message;
						resolve(message);
					};
				})
			: null;

		await server.connect(serverTransport);

		await clientTransport.start();
		await serverTransport.start();

		await clientTransport.send(jsonRpcRequest);

		if (responsePromise) {
			await Promise.race([
				responsePromise,
				new Promise((_, reject) =>
					setTimeout(() => reject(new Error("MCP request timed out")), 30000),
				),
			]);
		} else {
			await new Promise((resolve) => setTimeout(resolve, 20));
		}

		await clientTransport.close();
		await serverTransport.close();

		return Response.json(responseData, {
			headers: {
				"Content-Type": "application/json",
			},
		});
	} catch (error) {
		console.error("MCP handler error:", error);

		// Return a JSON-RPC error response
		return Response.json(
			{
				jsonrpc: "2.0",
				error: {
					code: -32603,
					message: "Internal server error",
					data: error instanceof Error ? error.message : String(error),
				},
				id: null,
			},
			{
				status: 500,
				headers: {
					"Content-Type": "application/json",
				},
			},
		);
	}
}
