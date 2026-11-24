import { describe, it, expect } from "vitest";
import type { ApiResponse, HealthCheckResponse, User } from "../src";

describe("Shared Types Contract", () => {
  it("validates ApiResponse structure", () => {
    const successResponse: ApiResponse<{ message: string }> = {
      success: true,
      data: { message: "pong" },
    };
    expect(successResponse.success).toBe(true);
    expect(successResponse.data?.message).toBe("pong");
  });

  it("validates HealthCheckResponse structure", () => {
    const health: HealthCheckResponse = {
      status: "ok",
      uptime: 120,
      timestamp: new Date().toISOString(),
      environment: "test",
    };
    expect(health.status).toBe("ok");
  });
});
