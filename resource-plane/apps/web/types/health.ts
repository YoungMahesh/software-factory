export interface ServiceHealth {
	name: string;
	status: "healthy" | "unhealthy" | "stopped" | "starting";
	port?: number;
	containerRunning: boolean;
	message?: string;
}

export interface ServicesHealth {
	postgres: ServiceHealth;
	seaweedfs: ServiceHealth;
}
