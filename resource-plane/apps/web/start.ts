import {
	createBasicAuthChallengeResponse,
	extractBasicAuthCredentials,
	isExemptFromBasicAuth,
	validateControlPlaneCredentials,
} from "./services/basic-auth";

export const basicAuthMiddleware = {
	options: {
		server: async ({
			request,
			next,
		}: { request: Request; next: () => Promise<any> }) => {
			if (isExemptFromBasicAuth(request.url)) {
				return next();
			}
			const authHeader = request.headers.get("authorization");
			const credentials = extractBasicAuthCredentials(authHeader);
			if (
				!credentials ||
				!(await validateControlPlaneCredentials(credentials))
			) {
				return createBasicAuthChallengeResponse();
			}
			return next();
		},
	},
};
