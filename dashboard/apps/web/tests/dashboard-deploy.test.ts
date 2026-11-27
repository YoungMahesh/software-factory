import { describe, expect, it } from "vitest";
import type { DashboardDeployRecord } from "@dashboard/types";
import { GET as getHealth } from "@/app/api/health/route";
import {
  isActiveDashboardDeploy,
  normalizeDeployHost,
  resolveDashboardDeployActions,
} from "@/lib/dashboard-deploy";

describe("dashboard self-deploy helpers", () => {
  it("normalizes hostnames cleanly across schemes, wildcards, ports, and case", () => {
    expect(normalizeDeployHost("https://Example.COM:8443/path")).toBe("example.com");
    expect(normalizeDeployHost("*.Example.com.")).toBe("example.com");
    expect(normalizeDeployHost("   ")).toBeNull();
    expect(normalizeDeployHost(null)).toBeNull();
  });

  it("shows only subdomain deploy button when served from the app base domain", () => {
    const actions = resolveDashboardDeployActions("factory.example.com", "factory.example.com");
    expect(actions).toEqual([
      {
        target: "subdomain",
        label: "Deploy dashboard.factory.example.com",
        targetDomain: "dashboard.factory.example.com",
        targetUrl: "https://dashboard.factory.example.com",
      },
    ]);
  });

  it("shows only apex deploy button when served from the dashboard subdomain", () => {
    const actions = resolveDashboardDeployActions(
      "dashboard.factory.example.com",
      "factory.example.com",
    );
    expect(actions).toEqual([
      {
        target: "apex",
        label: "Deploy factory.example.com",
        targetDomain: "factory.example.com",
        targetUrl: "https://factory.example.com",
      },
    ]);
  });

  it("shows both buttons on localhost or when base domain is unset", () => {
    const localActions = resolveDashboardDeployActions("localhost", "factory.example.com");
    expect(localActions.map((a) => a.target)).toEqual(["subdomain", "apex"]);

    const fallbackActions = resolveDashboardDeployActions("localhost", null);
    expect(fallbackActions).toEqual([
      {
        target: "subdomain",
        label: "Deploy dashboard subdomain",
        targetDomain: "dashboard subdomain",
        targetUrl: null,
      },
      {
        target: "apex",
        label: "Deploy app base domain",
        targetDomain: "app base domain",
        targetUrl: null,
      },
    ]);
  });

  it("detects active deploy statuses accurately", () => {
    const makeRecord = (status: DashboardDeployRecord["status"]): DashboardDeployRecord => ({
      deploy_id: "dep-1",
      target: "subdomain",
      status,
      current_label: status,
      target_url: null,
      commit_short: null,
      control_plane_url: null,
      logs: [],
      error: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });

    expect(isActiveDashboardDeploy(makeRecord("queued"))).toBe(true);
    expect(isActiveDashboardDeploy(makeRecord("cloning"))).toBe(true);
    expect(isActiveDashboardDeploy(makeRecord("deploying"))).toBe(true);
    expect(isActiveDashboardDeploy(makeRecord("ready"))).toBe(false);
    expect(isActiveDashboardDeploy(makeRecord("failed"))).toBe(false);
    expect(isActiveDashboardDeploy(null)).toBe(false);
  });

  it("exposes apps_base_domain and dashboard_commit via /api/health", async () => {
    const prevBase = process.env.APPS_BASE_DOMAIN;
    const prevCommit = process.env.NEXT_PUBLIC_DASHBOARD_COMMIT;
    process.env.APPS_BASE_DOMAIN = "factory.example.com";
    process.env.NEXT_PUBLIC_DASHBOARD_COMMIT = "deadbee";
    try {
      const res = await getHealth();
      expect(res.status).toBe(200);
      const data = await res.json();
      expect(data.apps_base_domain).toBe("factory.example.com");
      expect(data.dashboard_commit).toBe("deadbee");
    } finally {
      if (prevBase === undefined) delete process.env.APPS_BASE_DOMAIN;
      else process.env.APPS_BASE_DOMAIN = prevBase;
      if (prevCommit === undefined) delete process.env.NEXT_PUBLIC_DASHBOARD_COMMIT;
      else process.env.NEXT_PUBLIC_DASHBOARD_COMMIT = prevCommit;
    }
  });
});
