import { createNeonMcpServer } from "../mcp/server";
import { extractBearerToken, validateAdminToken } from "../services/admin-token";
import { handleMcpRequest } from "../utils/mcp-handler";

export async function handleAuthenticatedMcpRequest(
	request: Request,
): Promise<Response> {
	const authHeader = request.headers.get("authorization");
	const token = extractBearerToken(authHeader);

	if (!token || !(await validateAdminToken(token))) {
		return Response.json(
			{
				jsonrpc: "2.0",
				error: {
					code: -32000,
					message: "Unauthorized: Invalid or missing Admin Token",
				},
				id: null,
			},
			{
				status: 401,
				headers: {
					"Content-Type": "application/json",
				},
			},
		);
	}

	const server = createNeonMcpServer();
	return handleMcpRequest(request, server);
}

export const Route = {
	options: {
		server: {
			handlers: {
				POST: async ({ request }: { request: Request }) =>
					handleAuthenticatedMcpRequest(request),
			},
		},
	},
};
