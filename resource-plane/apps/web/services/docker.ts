import http from "node:http";

export const DOCKER_SOCKET_PATH =
	process.env.DOCKER_SOCKET_PATH || "/var/run/docker.sock";

export interface DockerContainer {
	Id: string;
	Names: string[];
	Image: string;
	State: string;
	Status: string;
	Ports: Array<{
		IP?: string;
		PrivatePort: number;
		PublicPort?: number;
		Type: string;
	}>;
}

export interface ContainerInspectInfo {
	Id: string;
	Name: string;
	State: {
		Status: string;
		Running: boolean;
		Paused: boolean;
		Restarting: boolean;
		Dead: boolean;
		ExitCode: number;
		Error: string;
	};
	NetworkSettings: {
		Ports: Record<string, Array<{ HostIp: string; HostPort: string }> | null>;
	};
	HostConfig: {
		PortBindings?: Record<
			string,
			Array<{ HostIp: string; HostPort: string }> | null
		>;
		Binds?: string[];
	};
	Config?: {
		Cmd?: string[];
		Env?: string[];
	};
}

export interface CreateContainerOptions {
	name: string;
	Image: string;
	Cmd?: string[];
	Env?: string[];
	ExposedPorts?: Record<string, Record<string, never>>;
	HostConfig?: {
		PortBindings?: Record<string, Array<{ HostIp: string; HostPort: string }>>;
		Binds?: string[];
		RestartPolicy?: {
			Name: string;
			MaximumRetryCount?: number;
		};
	};
}

export function dockerRequest<T = any>(
	path: string,
	method = "GET",
	body?: any,
): Promise<{ status: number; data: T }> {
	return new Promise((resolve, reject) => {
		const payload = body
			? typeof body === "string"
				? body
				: JSON.stringify(body)
			: null;

		const req = http.request(
			{
				socketPath: DOCKER_SOCKET_PATH,
				path,
				method,
				headers: {
					host: "localhost",
					...(payload
						? {
								"Content-Type": "application/json",
								"Content-Length": Buffer.byteLength(payload),
							}
						: {}),
				},
			},
			(res) => {
				const chunks: Buffer[] = [];
				res.on("data", (c) => chunks.push(c));
				res.on("end", () => {
					const raw = Buffer.concat(chunks).toString("utf8");
					const status = res.statusCode || 500;
					try {
						resolve({
							status,
							data: raw ? JSON.parse(raw) : (null as unknown as T),
						});
					} catch {
						resolve({ status, data: raw as unknown as T });
					}
				});
			},
		);

		req.on("error", reject);
		if (payload) req.write(payload);
		req.end();
	});
}

export async function pingDocker(): Promise<boolean> {
	try {
		const res = await dockerRequest("/_ping", "GET");
		return res.status === 200;
	} catch {
		return false;
	}
}

export async function listContainers(all = true): Promise<DockerContainer[]> {
	const query = all ? "?all=1" : "";
	const res = await dockerRequest<DockerContainer[]>(
		`/containers/json${query}`,
		"GET",
	);
	if (res.status === 200 && Array.isArray(res.data)) {
		return res.data;
	}
	return [];
}

export async function inspectContainer(
	nameOrId: string,
): Promise<ContainerInspectInfo | null> {
	try {
		const res = await dockerRequest<ContainerInspectInfo>(
			`/containers/${encodeURIComponent(nameOrId)}/json`,
			"GET",
		);
		if (res.status === 200 && res.data) {
			return res.data;
		}
		return null;
	} catch {
		return null;
	}
}

export async function isContainerRunning(nameOrId: string): Promise<boolean> {
	const info = await inspectContainer(nameOrId);
	return Boolean(info?.State?.Running);
}

export async function pullImage(image: string, tag = "latest"): Promise<void> {
	return new Promise((resolve, reject) => {
		const path = `/images/create?fromImage=${encodeURIComponent(image)}&tag=${encodeURIComponent(tag)}`;
		const req = http.request(
			{
				socketPath: DOCKER_SOCKET_PATH,
				path,
				method: "POST",
				headers: {
					host: "localhost",
				},
			},
			(res) => {
				if (res.statusCode && res.statusCode >= 400) {
					const chunks: Buffer[] = [];
					res.on("data", (c) => chunks.push(c));
					res.on("end", () => {
						const raw = Buffer.concat(chunks).toString("utf8");
						reject(
							new Error(
								`Failed to pull image ${image}:${tag} - HTTP ${res.statusCode}: ${raw}`,
							),
						);
					});
					return;
				}
				res.on("data", () => {
					// Stream chunks can be consumed or logged if needed
				});
				res.on("end", () => resolve());
			},
		);

		req.on("error", reject);
		req.end();
	});
}

export async function createContainer(
	options: CreateContainerOptions,
): Promise<{ id: string; warnings: string[] }> {
	const { name, ...payload } = options;
	const path = `/containers/create?name=${encodeURIComponent(name)}`;
	const res = await dockerRequest<{ Id: string; Warnings: string[] }>(
		path,
		"POST",
		payload,
	);
	if (res.status === 201 && res.data?.Id) {
		return {
			id: res.data.Id,
			warnings: res.data.Warnings || [],
		};
	}
	throw new Error(
		`Failed to create container ${name}: HTTP ${res.status} - ${JSON.stringify(res.data)}`,
	);
}

export async function startContainer(nameOrId: string): Promise<void> {
	const path = `/containers/${encodeURIComponent(nameOrId)}/start`;
	const res = await dockerRequest(path, "POST");
	if (res.status === 204 || res.status === 304) {
		return;
	}
	throw new Error(
		`Failed to start container ${nameOrId}: HTTP ${res.status} - ${JSON.stringify(res.data)}`,
	);
}

export async function stopContainer(
	nameOrId: string,
	timeoutSec = 2,
): Promise<void> {
	const path = `/containers/${encodeURIComponent(nameOrId)}/stop?t=${timeoutSec}`;
	const res = await dockerRequest(path, "POST");
	if (res.status === 204 || res.status === 304) {
		return;
	}
	throw new Error(
		`Failed to stop container ${nameOrId}: HTTP ${res.status} - ${JSON.stringify(res.data)}`,
	);
}

export async function removeContainer(
	nameOrId: string,
	force = true,
): Promise<void> {
	const path = `/containers/${encodeURIComponent(nameOrId)}?force=${force}`;
	const res = await dockerRequest(path, "DELETE");
	if (res.status === 204 || res.status === 404) {
		return;
	}
	throw new Error(
		`Failed to remove container ${nameOrId}: HTTP ${res.status} - ${JSON.stringify(res.data)}`,
	);
}

export async function killContainer(
	nameOrId: string,
	signal = "SIGHUP",
): Promise<void> {
	const path = `/containers/${encodeURIComponent(nameOrId)}/kill?signal=${signal}`;
	const res = await dockerRequest(path, "POST");
	if (res.status === 204) {
		return;
	}
	throw new Error(
		`Failed to signal container ${nameOrId} with ${signal}: HTTP ${res.status} - ${JSON.stringify(res.data)}`,
	);
}
