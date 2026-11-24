export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  error?: {
    code: string;
    message: string;
  };
}

export interface HealthCheckResponse {
  status: "ok" | "degraded" | "error";
  uptime: number;
  timestamp: string;
  environment: string;
}
