import { getCaCertificate } from "../../services/certs";

export async function GET(request?: Request): Promise<Response> {
	const caCertificate = getCaCertificate();
	return new Response(caCertificate, {
		status: 200,
		headers: {
			"Content-Type": "application/x-x509-ca-cert",
			"Content-Disposition": "inline; filename=\"ca.crt\"",
		},
	});
}

export const Route = {
	options: {
		server: {
			handlers: {
				GET: async ({ request }: { request?: Request } = {}) => GET(request),
			},
		},
	},
};
