import { describe, expect, it } from "vitest";
import {
  constantTimeEqual,
  extractBasicAuth,
  isExemptFromBasicAuth,
} from "../lib/auth";
import {
  fetchLiveDashboardHealth,
  gatherDeployerStatus,
  isSubdomainOf,
  normalizeBaseDomain,
  proxyControlPlaneRequest,
  resolveControlPlaneAuthHeader,
  resolveControlPlaneOrigin,
} from "../lib/control-plane";
import {
  DashboardDeployRecordSchema,
  isActiveDashboardDeploy,
} from "../lib/deploy-types";

describe("dashboard-deployer", () => {
  it("validates Basic Auth exemptions and extraction", () => {
    expect(isExemptFromBasicAuth("/api/health")).toBe(true);
    expect(isExemptFromBasicAuth("/_next/static/chunk.js")).toBe(true);
    expect(isExemptFromBasicAuth("/")).toBe(false);
    expect(isExemptFromBasicAuth("/api/deploy")).toBe(false);

    const token = Buffer.from("admin:s3cr3t").toString("base64");
    expect(extractBasicAuth(`Basic ${token}`)).toEqual({ user: "admin", pass: "s3cr3t" });
    expect(extractBasicAuth("Bearer foo")).toBeNull();
    expect(constantTimeEqual("abc", "abc")).toBe(true);
    expect(constantTimeEqual("abc", "abd")).toBe(false);
  });

  it("enforces Control Plane origin validation and loop guard", () => {
    expect(normalizeBaseDomain("https://Deploy.Apps.Example.com/")).toBe("deploy.apps.example.com");
    expect(isSubdomainOf("deploy.apps.example.com", "apps.example.com")).toBe(true);
    expect(isSubdomainOf("apps.example.com", "apps.example.com")).toBe(true);

    expect(
      resolveControlPlaneOrigin({
        NODE_ENV: "test",
        SANDBOX_CONTROL_PLANE_URL: "https://ws--sandbox-control-plane-fastapi-app.modal.run",
        APPS_BASE_DOMAIN: "apps.example.com",
      }),
    ).toBe("https://ws--sandbox-control-plane-fastapi-app.modal.run");

    expect(() =>
      resolveControlPlaneOrigin({
        NODE_ENV: "test",
        SANDBOX_CONTROL_PLANE_URL: "https://apps.example.com",
        APPS_BASE_DOMAIN: "apps.example.com",
      }),
    ).toThrow(/loop guard/i);

    expect(
      resolveControlPlaneAuthHeader({
        NODE_ENV: "test",
        WEB_UI_USERNAME: "admin",
        WEB_UI_PASSWORD: "secret",
      }),
    ).toBe(`Basic ${Buffer.from("admin:secret").toString("base64")}`);
  });

  it("proxies deploy trigger and gathers status with live health", async () => {
    const mockFetch: typeof fetch = async (input, init) => {
      const url = String(input);
      if (url === "https://cp.modal.run/api/version") {
        return Response.json({
          commit: "1234567890abcdef",
          commit_short: "1234567",
          ref: "main",
          dirty: false,
        });
      }
      if (url === "https://cp.modal.run/api/dashboard/deploy" && (!init?.method || init.method === "GET")) {
        return Response.json({
          deploy: {
            deploy_id: "dash-1",
            target: "apex",
            status: "ready",
            current_label: "Live at https://apps.example.com",
            target_url: "https://apps.example.com",
            commit_short: "1234567",
            logs: ["Deployed"],
            created_at: "2026-11-27T12:00:00Z",
            updated_at: "2026-11-27T12:01:00Z",
          },
        });
      }
      if (url === "https://cp.modal.run/api/dashboard/deploy" && init?.method === "POST") {
        return Response.json(
          {
            deploy_id: "dash-2",
            target: "apex",
            status: "queued",
            current_label: "Queued production deploy (App Base Domain)",
            created_at: "2026-11-27T12:05:00Z",
            updated_at: "2026-11-27T12:05:00Z",
          },
          { status: 202 },
        );
      }
      if (url === "https://apps.example.com/api/health") {
        return Response.json({ status: "ok", dashboard_commit: "deadbee" });
      }
      return new Response("Not Found", { status: 404 });
    };

    const env: NodeJS.ProcessEnv = {
      NODE_ENV: "test",
      SANDBOX_CONTROL_PLANE_URL: "https://cp.modal.run",
      APPS_BASE_DOMAIN: "apps.example.com",
      WEB_UI_USERNAME: "admin",
      WEB_UI_PASSWORD: "secret",
      NEXT_PUBLIC_DASHBOARD_COMMIT: "faceb00",
    };

    const status = await gatherDeployerStatus({ fetchImpl: mockFetch, env });
    expect(status.target_url).toBe("https://apps.example.com");
    expect(status.control_plane_version?.commit_short).toBe("1234567");
    expect(status.live_dashboard_commit).toBe("deadbee");
    expect(status.live_dashboard_reachable).toBe(true);
    expect(status.latest_deploy?.deploy_id).toBe("dash-1");
    expect(status.deployer_commit).toBe("faceb00");

    const postRes = await proxyControlPlaneRequest("/api/dashboard/deploy", {
      method: "POST",
      body: JSON.stringify({ target: "apex" }),
      fetchImpl: mockFetch,
      env,
    });
    expect(postRes.status).toBe(202);
    const created = DashboardDeployRecordSchema.parse(await postRes.json());
    expect(isActiveDashboardDeploy(created)).toBe(true);

    const unreachable = await fetchLiveDashboardHealth("https://apps.example.com", async () => {
      throw new Error("timeout");
    });
    expect(unreachable).toEqual({ commit: null, reachable: false });
  });
});
