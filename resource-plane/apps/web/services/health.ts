import type { ServicesHealth } from "../types/health";

export async function fetchHealth(): Promise<ServicesHealth> {
	const { ensureSystemReady, getServicesHealth } = await import(
		"./bootstrap"
	);
	ensureSystemReady().catch(() => {});
	return await getServicesHealth();
}

export async function getHealthStatus(): Promise<ServicesHealth> {
	return fetchHealth();
}
(getHealthStatus as any).url = "/api/health";
