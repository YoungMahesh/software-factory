export interface DatabaseCredentials {
	id: string;
	projectId: string;
	name: string;
	username: string;
	password: string;
	host: string;
	port: number;
	createdAt: Date;
	connectionString: string;
	envSnippet: string;
	psqlCommand: string;
	psqlCommandRaw: string;
	prismaSnippet: string;
	drizzleSnippet: string;
	caCertificatePath?: string;
}
