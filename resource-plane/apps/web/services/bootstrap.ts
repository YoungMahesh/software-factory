import fs from "node:fs";
import http from "node:http";
import net from "node:net";
import path from "node:path";
import { migrate } from "drizzle-orm/node-postgres/migrator";
import pg from "pg";
import { getDb } from "../db/index";
import {
	type CreateContainerOptions,
	createContainer,
	inspectContainer,
	isContainerRunning,
	killContainer,
	pingDocker,
	pullImage,
	removeContainer,
	startContainer,
	stopContainer,
} from "./docker";

export const POSTGRES_CONTAINER_NAME = "neon-postgres";
export const SEAWEEDFS_CONTAINER_NAME = "neon-seaweedfs";
export const DEFAULT_POSTGRES_PORT = 5432;
export const FALLBACK_POSTGRES_PORT = 54320;
export const SEAWEEDFS_S3_PORT = 8333;
/**
 * SeaweedFS Filer internal port inside container (isolated from host).
 */
export const SEAWEEDFS_FILER_PORT = 8888;
export const HOST_BIND_IP = process.env.HOST_BIND_IP || "127.0.0.1";

import {
	type CertificatePaths,
	type EnsureTlsCertificatesOptions,
	type EnsureTlsCertificatesResult,
	ensureTlsCertificates,
	getCaCertificate,
	getCertificatePaths,
	getPublicPostgresHost,
	CA_DOWNLOAD_PATH,
} from "./certs";

export {
	getPublicPostgresHost,
	getCertificatePaths,
	getCaCertificate,
	ensureTlsCertificates,
	CA_DOWNLOAD_PATH,
	type CertificatePaths,
	type EnsureTlsCertificatesOptions,
	type EnsureTlsCertificatesResult,
};

import type { ServiceHealth, ServicesHealth } from "../types/health";
import {
	getMasterDatabaseCredentials,
	getStorageAdminCredentials,
} from "./master-credentials";
export type { ServiceHealth, ServicesHealth };

export function isPortAvailable(port: number): Promise<boolean> {
	return new Promise((resolve) => {
		const server = net.createServer();
		server.once("error", () => {
			resolve(false);
		});
		server.once("listening", () => {
			server.close(() => resolve(true));
		});
		server.listen(port, "0.0.0.0");
	});
}

export async function resolvePostgresPort(): Promise<number> {
	if (process.env.POSTGRES_PORT) {
		return Number.parseInt(process.env.POSTGRES_PORT, 10);
	}
	const inspect = await inspectContainer(POSTGRES_CONTAINER_NAME);
	if (inspect) {
		const portBinding =
			inspect.HostConfig?.PortBindings?.["5432/tcp"]?.[0]?.HostPort ||
			inspect.NetworkSettings?.Ports?.["5432/tcp"]?.[0]?.HostPort;
		if (portBinding) {
			return Number.parseInt(portBinding, 10);
		}
	}

	const free5432 = await isPortAvailable(DEFAULT_POSTGRES_PORT);
	if (free5432) {
		return DEFAULT_POSTGRES_PORT;
	}
	return FALLBACK_POSTGRES_PORT;
}

/**
 * Helper to create a container, pulling the image if missing (404) and retrying once.
 */
export async function createContainerWithPullRetry(
	options: CreateContainerOptions,
	imageRepo: string,
	imageTag: string,
): Promise<{ id: string; warnings?: string[] }> {
	try {
		return await createContainer(options);
	} catch (err: any) {
		if (err.message && err.message.includes("404")) {
			await pullImage(imageRepo, imageTag);
			return await createContainer(options);
		}
		throw err;
	}
}

/**
 * Ensures pg_hba.conf enforces hostssl for remote connections while keeping loopback unencrypted.
 */
export async function ensurePostgresHbaConfig(
	postgresDataDir: string,
	client?: pg.Client,
	gatewayIp?: string,
): Promise<void> {
	const hbaPath = path.resolve(postgresDataDir, "pg_hba.conf");
	if (!fs.existsSync(hbaPath)) return;
	const content = fs.readFileSync(hbaPath, "utf8");
	const lines = content.split("\n");
	const hasHostssl = lines.some((l) => {
		const trimmed = l.trim();
		if (!trimmed || trimmed.startsWith("#")) return false;
		const tokens = trimmed.split(/\s+/);
		return (
			tokens[0] === "hostssl" &&
			(tokens[3] === "0.0.0.0/0" ||
				tokens[3] === "all" ||
				(tokens[3] === "0.0.0.0" && tokens[4] === "0.0.0.0"))
		);
	});
	const hasInsecureHostAll = lines.some((l) => {
		const trimmed = l.trim();
		if (!trimmed || trimmed.startsWith("#")) return false;
		const tokens = trimmed.split(/\s+/);
		if (tokens[0] !== "host") return false;
		const address = tokens[3];
		if (address === "all" || address === "0.0.0.0/0" || address === "::/0") {
			return true;
		}
		if (address === "0.0.0.0" && tokens[4] === "0.0.0.0") {
			return true;
		}
		return false;
	});

	if (!hasHostssl || hasInsecureHostAll) {
		const extraGateway =
			gatewayIp && gatewayIp !== "172.17.0.1"
				? `host    all             all             ${gatewayIp}/32            scram-sha-256\n`
				: "";
		const hardened = `# PostgreSQL Client Authentication Configuration File
# Managed by Neon Auto-Bootstrapper

# "local" is for Unix domain socket connections only
local   all             all                                     trust
# IPv4 local loopback connections:
host    all             all             127.0.0.1/32            scram-sha-256
# IPv6 local loopback connections:
host    all             all             ::1/128                 scram-sha-256
# Local control-plane host loopback via Docker bridge gateway:
host    all             all             172.17.0.1/32           scram-sha-256
${extraGateway}# Allow replication connections from localhost
local   replication     all                                     trust
host    replication     all             127.0.0.1/32            scram-sha-256
host    replication     all             ::1/128                 scram-sha-256

# Enforce TLS for all remote network connections
hostssl all             all             0.0.0.0/0               scram-sha-256
hostssl all             all             ::/0                    scram-sha-256
`;
		fs.writeFileSync(hbaPath, hardened, "utf8");
		fs.chmodSync(hbaPath, 0o600);
		try {
			fs.chownSync(hbaPath, 70, 70);
		} catch {}
		if (client) {
			await client.query("SELECT pg_reload_conf()").catch(() => {});
		}
	}
}

export async function bootstrapContainers(): Promise<{
	postgresPort: number;
	seaweedfsS3Port: number;
}> {
	const masterDb = getMasterDatabaseCredentials();
	const storageAdmin = getStorageAdminCredentials();
	const hostBindIp = process.env.HOST_BIND_IP || HOST_BIND_IP || "127.0.0.1";

	const rootDir = process.cwd();
	const dataDir = process.env.DATA_DIR || path.resolve(rootDir, ".data");
	const hostDataDir = process.env.HOST_DATA_DIR || dataDir;
	const postgresDataDir = path.resolve(dataDir, "postgres");
	const seaweedfsDataDir = path.resolve(dataDir, "seaweedfs");

	if (!fs.existsSync(postgresDataDir)) {
		fs.mkdirSync(postgresDataDir, { recursive: true });
	}
	if (!fs.existsSync(seaweedfsDataDir)) {
		fs.mkdirSync(seaweedfsDataDir, { recursive: true });
	}

	const certs = await ensureTlsCertificates({ baseDataDir: dataDir });
	const initialPgInspect = await inspectContainer(POSTGRES_CONTAINER_NAME);
	const initialGatewayIp = (initialPgInspect as any)?.NetworkSettings?.Networks
		?.bridge?.Gateway;
	await ensurePostgresHbaConfig(postgresDataDir, undefined, initialGatewayIp);

	const s3ConfigPath = path.resolve(seaweedfsDataDir, "s3.json");
	if (!fs.existsSync(s3ConfigPath)) {
		fs.writeFileSync(
			s3ConfigPath,
			JSON.stringify(
				{
					identities: [
						{
							name: "admin",
							credentials: [
								{
									accessKey: storageAdmin.accessKeyId,
									secretKey: storageAdmin.secretAccessKey,
								},
							],
							actions: ["Admin", "Read", "List", "Tagging", "Write"],
						},
					],
				},
				null,
				2,
			),
		);
	}

	// 1. PostgreSQL container
	const pgPort = await resolvePostgresPort();
	let pgInspect = await inspectContainer(POSTGRES_CONTAINER_NAME);

	// Detect and migrate legacy PostgreSQL container bound to 0.0.0.0 when not requested,
	// or missing SSL configuration / cert mounts
	if (pgInspect) {
		const portBindings =
			pgInspect.HostConfig?.PortBindings?.["5432/tcp"] ||
			pgInspect.NetworkSettings?.Ports?.["5432/tcp"];
		const isWildcardBound = portBindings?.some(
			(b: any) => b.HostIp === "0.0.0.0" || b.HostIp === "",
		);
		const isLegacyWildcard = hostBindIp !== "0.0.0.0" && isWildcardBound;

		const binds: string[] = pgInspect.HostConfig?.Binds || [];
		const hasCertBinds =
			binds.some(
				(b: string) =>
					b.startsWith(`${certs.serverCertPath}:`) ||
					b.includes(":/var/lib/postgresql/certs/server.crt"),
			) &&
			binds.some(
				(b: string) =>
					b.startsWith(`${certs.serverKeyPath}:`) ||
					b.includes(":/var/lib/postgresql/certs/server.key"),
			);
		const hasDataBind = binds.some(
			(b: string) =>
				b.startsWith(`${postgresDataDir}:`) ||
				b.includes(":/var/lib/postgresql/data"),
		);
		const cmd = pgInspect.Config?.Cmd || [];
		const hasSslCmd = cmd.includes("ssl=on");

		if (isLegacyWildcard || !hasCertBinds || !hasDataBind || !hasSslCmd) {
			await stopContainer(POSTGRES_CONTAINER_NAME, 2).catch(() => {});
			await removeContainer(POSTGRES_CONTAINER_NAME, true).catch(() => {});
			pgInspect = null;
		} else if (certs.regenerated && pgInspect.State.Running) {
			await killContainer(POSTGRES_CONTAINER_NAME, "SIGHUP").catch(() => {});
		}
	}

	if (!pgInspect) {
		await createContainerWithPullRetry(
			{
				name: POSTGRES_CONTAINER_NAME,
				Image: "postgres:16-alpine",
				Cmd: [
					"postgres",
					"-c",
					"ssl=on",
					"-c",
					"ssl_cert_file=/var/lib/postgresql/certs/server.crt",
					"-c",
					"ssl_key_file=/var/lib/postgresql/certs/server.key",
				],
				Env: [`POSTGRES_PASSWORD=${masterDb.password}`],
				ExposedPorts: { "5432/tcp": {} },
				HostConfig: {
					PortBindings: {
						"5432/tcp": [{ HostIp: hostBindIp, HostPort: String(pgPort) }],
					},
					Binds: [
						`${path.resolve(hostDataDir, "postgres")}:/var/lib/postgresql/data`,
						`${certs.serverCertPath}:/var/lib/postgresql/certs/server.crt:ro`,
						`${certs.serverKeyPath}:/var/lib/postgresql/certs/server.key:ro`,
					],
					RestartPolicy: { Name: "unless-stopped" },
				},
			},
			"postgres",
			"16-alpine",
		);
		await startContainer(POSTGRES_CONTAINER_NAME);
	} else if (!pgInspect.State.Running) {
		await startContainer(POSTGRES_CONTAINER_NAME);
	}

	// 2. SeaweedFS container
	let swInspect = await inspectContainer(SEAWEEDFS_CONTAINER_NAME);

	if (swInspect) {
		const filerPortBindings =
			swInspect.HostConfig?.PortBindings?.["8888/tcp"] ||
			swInspect.NetworkSettings?.Ports?.["8888/tcp"];
		const s3PortBindings =
			swInspect.HostConfig?.PortBindings?.["8333/tcp"] ||
			swInspect.NetworkSettings?.Ports?.["8333/tcp"];
		const isWildcardBound = s3PortBindings?.some(
			(b: any) => b.HostIp === "0.0.0.0" || b.HostIp === "",
		);
		const isLegacyWildcard = hostBindIp !== "0.0.0.0" && isWildcardBound;
		if (
			(filerPortBindings && filerPortBindings.length > 0) ||
			isLegacyWildcard
		) {
			await stopContainer(SEAWEEDFS_CONTAINER_NAME, 2).catch(() => {});
			await removeContainer(SEAWEEDFS_CONTAINER_NAME, true).catch(() => {});
			swInspect = null;
		}
	}

	if (!swInspect) {
		await createContainerWithPullRetry(
			{
				name: SEAWEEDFS_CONTAINER_NAME,
				Image: "chrislusf/seaweedfs:latest",
				Cmd: [
					"server",
					"-s3",
					"-filer",
					"-dir=/data",
					"-s3.config=/data/s3.json",
				],
				ExposedPorts: {
					"8333/tcp": {},
				},
				HostConfig: {
					PortBindings: {
						"8333/tcp": [{ HostIp: hostBindIp, HostPort: "8333" }],
					},
					Binds: [`${path.resolve(hostDataDir, "seaweedfs")}:/data`],
					RestartPolicy: { Name: "unless-stopped" },
				},
			},
			"chrislusf/seaweedfs",
			"latest",
		);
		await startContainer(SEAWEEDFS_CONTAINER_NAME);
	} else if (!swInspect.State.Running) {
		await startContainer(SEAWEEDFS_CONTAINER_NAME);
	}

	const postgresHost = process.env.POSTGRES_HOST || "localhost";
	const pgInternalPort = postgresHost === "postgres" ? 5432 : pgPort;
	process.env.POSTGRES_PORT = String(pgPort);
	if (!process.env.DATABASE_URL) {
		process.env.DATABASE_URL = `postgresql://${masterDb.username}:${masterDb.password}@${postgresHost}:${pgInternalPort}/neon_control_plane`;
	}

	return {
		postgresPort: pgPort,
		seaweedfsS3Port: SEAWEEDFS_S3_PORT,
	};
}

export async function waitForPostgresReady(
	port: number,
	timeoutMs = 30000,
): Promise<boolean> {
	const { username, password } = getMasterDatabaseCredentials();
	const postgresHost = process.env.POSTGRES_HOST || "localhost";
	const effectivePort = postgresHost === "postgres" ? 5432 : port;
	const rootDir = process.cwd();
	const dataDir = process.env.DATA_DIR || path.resolve(rootDir, ".data");
	const postgresDataDir = path.resolve(dataDir, "postgres");
	const start = Date.now();
	while (Date.now() - start < timeoutMs) {
		let client: pg.Client | null = null;
		try {
			client = new pg.Client({
				host: postgresHost,
				port: effectivePort,
				user: username,
				password,
				database: "postgres",
				connectionTimeoutMillis: 1000,
			});
			await client.connect();
			await client.query("SELECT 1;");
			const hbaPath = path.resolve(postgresDataDir, "pg_hba.conf");
			if (fs.existsSync(hbaPath)) {
				await ensurePostgresHbaConfig(postgresDataDir, client);
			}
			await client.end();
			return true;
		} catch (err: any) {
			if (client) {
				client.end().catch(() => {});
			}

			// Handle seamless migration: if authentication failed on an existing cluster
			// initialized with legacy password 'postgres', rotate it in place.
			const isAuthFailure =
				err?.code === "28P01" ||
				(typeof err?.message === "string" &&
					err.message.includes("password authentication failed"));

			if (isAuthFailure && password !== "postgres") {
				let legacyClient: pg.Client | null = null;
				try {
					legacyClient = new pg.Client({
						host: postgresHost,
						port: effectivePort,
						user: "postgres",
						password: "postgres",
						database: "postgres",
						connectionTimeoutMillis: 1500,
					});
					await legacyClient.connect();
					const escapedPassword = password.replace(/'/g, "''");
					await legacyClient.query(
						`ALTER USER "${username}" WITH PASSWORD '${escapedPassword}';`,
					);
					await legacyClient.end();
					// Now retry connection with active configured password immediately
					continue;
				} catch {
					if (legacyClient) {
						legacyClient.end().catch(() => {});
					}
				}
			}

			await new Promise((r) => setTimeout(r, 400));
		}
	}
	throw new Error(`PostgreSQL not ready on port ${port} within ${timeoutMs}ms`);
}

export async function initSystemDatabase(port: number): Promise<void> {
	const { username, password } = getMasterDatabaseCredentials();
	const postgresHost = process.env.POSTGRES_HOST || "localhost";
	const effectivePort = postgresHost === "postgres" ? 5432 : port;
	const client = new pg.Client({
		host: postgresHost,
		port: effectivePort,
		user: username,
		password,
		database: "postgres",
	});
	await client.connect();
	try {
		const res = await client.query(
			"SELECT 1 FROM pg_database WHERE datname = 'neon_control_plane'",
		);
		if (res.rowCount === 0) {
			await client.query("CREATE DATABASE neon_control_plane;");
			await client.query(
				"REVOKE CONNECT ON DATABASE neon_control_plane FROM PUBLIC;",
			);
			await client.query("REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;");
		}
	} finally {
		await client.end();
	}
}

export async function runMigrations(connectionString?: string): Promise<void> {
	const { username, password } = getMasterDatabaseCredentials();
	const defaultPort = process.env.POSTGRES_PORT || 5432;
	const defaultHost = process.env.POSTGRES_HOST || "localhost";
	const url =
		connectionString ||
		process.env.DATABASE_URL ||
		`postgresql://${username}:${password}@${defaultHost}:${defaultPort}/neon_control_plane`;
	const database = getDb(url);
	let migrationsFolder =
		process.env.DRIZZLE_MIGRATIONS_DIR || path.resolve(process.cwd(), "drizzle");
	if (!fs.existsSync(migrationsFolder)) {
		const altFolder = path.resolve(process.cwd(), "apps", "web", "drizzle");
		if (fs.existsSync(altFolder)) {
			migrationsFolder = altFolder;
		}
	}
	await migrate(database, { migrationsFolder });
}

export async function checkSeaweedFSReady(
	port = SEAWEEDFS_S3_PORT,
	timeoutMs = 1500,
): Promise<boolean> {
	const seaweedfsHost = process.env.SEAWEEDFS_HOST || "localhost";
	return new Promise((resolve) => {
		const req = http.request(
			{
				host: seaweedfsHost,
				port,
				path: "/",
				method: "GET",
				timeout: timeoutMs,
			},
			() => {
				resolve(true);
			},
		);
		req.on("error", () => resolve(false));
		req.on("timeout", () => {
			req.destroy();
			resolve(false);
		});
		req.end();
	});
}

export async function getServicesHealth(): Promise<ServicesHealth> {
	const dockerLive = await pingDocker();
	if (!dockerLive) {
		return {
			postgres: {
				name: "PostgreSQL",
				status: "unhealthy",
				containerRunning: false,
				message: "Docker daemon not reachable via socket",
			},
			seaweedfs: {
				name: "SeaweedFS",
				status: "unhealthy",
				containerRunning: false,
				message: "Docker daemon not reachable via socket",
			},
		};
	}

	// Check Postgres
	const pgRunning = await isContainerRunning(POSTGRES_CONTAINER_NAME);
	const pgPort = await resolvePostgresPort();
	let pgStatus: ServiceHealth["status"] = "stopped";
	let pgMessage: string | undefined;

	if (pgRunning) {
		try {
			const { username, password } = getMasterDatabaseCredentials();
			const postgresHost = process.env.POSTGRES_HOST || "localhost";
			const effectivePort = postgresHost === "postgres" ? 5432 : pgPort;
			const client = new pg.Client({
				host: postgresHost,
				port: effectivePort,
				user: username,
				password,
				database: "postgres",
				connectionTimeoutMillis: 1500,
			});
			await client.connect();
			await client.query("SELECT 1");
			await client.end();
			pgStatus = "healthy";
		} catch (err: any) {
			pgStatus = "starting";
			pgMessage = err.message;
		}
	}

	// Check SeaweedFS
	const swRunning = await isContainerRunning(SEAWEEDFS_CONTAINER_NAME);
	let swStatus: ServiceHealth["status"] = "stopped";
	let swMessage: string | undefined;

	if (swRunning) {
		const ready = await checkSeaweedFSReady(SEAWEEDFS_S3_PORT);
		if (ready) {
			swStatus = "healthy";
		} else {
			swStatus = "starting";
			swMessage = "S3 API not yet responding";
		}
	}

	return {
		postgres: {
			name: "PostgreSQL",
			status: pgStatus,
			port: pgPort,
			containerRunning: pgRunning,
			message: pgMessage,
		},
		seaweedfs: {
			name: "SeaweedFS",
			status: swStatus,
			port: SEAWEEDFS_S3_PORT,
			containerRunning: swRunning,
			message: swMessage,
		},
	};
}

export async function waitForSeaweedFSReady(
	port = SEAWEEDFS_S3_PORT,
	timeoutMs = 15000,
): Promise<boolean> {
	const start = Date.now();
	while (Date.now() - start < timeoutMs) {
		const ready = await checkSeaweedFSReady(port, 1000);
		if (ready) {
			return true;
		}
		await new Promise((r) => setTimeout(r, 400));
	}
	throw new Error(`SeaweedFS not ready on port ${port} within ${timeoutMs}ms`);
}

let bootstrapPromise: Promise<{
	postgresPort: number;
	status: "ready";
}> | null = null;

export async function runAutoBootstrap(): Promise<{
	postgresPort: number;
	status: "ready";
}> {
	const { postgresPort } = await bootstrapContainers();
	await Promise.all([
		waitForPostgresReady(postgresPort),
		waitForSeaweedFSReady(),
	]);
	await initSystemDatabase(postgresPort);
	const { username, password } = getMasterDatabaseCredentials();
	const postgresHost = process.env.POSTGRES_HOST || "localhost";
	const effectivePort = postgresHost === "postgres" ? 5432 : postgresPort;
	await runMigrations(
		process.env.DATABASE_URL ||
			`postgresql://${username}:${password}@${postgresHost}:${effectivePort}/neon_control_plane`,
	);
	return { postgresPort, status: "ready" };
}

export function ensureSystemReady(): Promise<{
	postgresPort: number;
	status: "ready";
}> {
	if (!bootstrapPromise) {
		bootstrapPromise = runAutoBootstrap().catch((err) => {
			bootstrapPromise = null;
			throw err;
		});
	}
	return bootstrapPromise;
}
