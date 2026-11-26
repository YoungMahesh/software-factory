import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { middleware } from "@/middleware";
import {
  constantTimeEqual,
  extractBasicAuth,
  isExemptFromBasicAuth,
} from "@/lib/auth";
import {
  buildUpstreamApiUrl,
  proxyToControlPlane,
  resolveControlPlaneOrigin,
} from "@/lib/control-plane";

describe("Basic Auth middleware and helpers", () => {
  it("exempts /api/health, /_next/*, /favicon.ico, and /icon.svg", () => {
    expect(isExemptFromBasicAuth("/api/health")).toBe(true);
    expect(isExemptFromBasicAuth("/_next/static/chunk.js")).toBe(true);
    expect(isExemptFromBasicAuth("/favicon.ico")).toBe(true);
    expect(isExemptFromBasicAuth("/icon.svg")).toBe(true);
    expect(isExemptFromBasicAuth("/")).toBe(false);
    expect(isExemptFromBasicAuth("/api/apps")).toBe(false);
  });

  it("extracts credentials including passwords containing colons", () => {
    const token = Buffer.from("admin:p@ss:word:123").toString("base64");
    expect(extractBasicAuth(`Basic ${token}`)).toEqual({
      user: "admin",
      pass: "p@ss:word:123",
    });
    expect(extractBasicAuth("Bearer xyz")).toBeNull();
    expect(extractBasicAuth(null)).toBeNull();
  });

  it("compares strings in constant time", () => {
    expect(constantTimeEqual("secret-1", "secret-1")).toBe(true);
    expect(constantTimeEqual("secret-1", "secret-2")).toBe(false);
    expect(constantTimeEqual("short", "longer-string")).toBe(false);
  });

  it("enforces Basic Auth when WEB_UI_USERNAME and WEB_UI_PASSWORD are set", async () => {
    const prevUser = process.env.WEB_UI_USERNAME;
    const prevPass = process.env.WEB_UI_PASSWORD;
    process.env.WEB_UI_USERNAME = "admin";
    process.env.WEB_UI_PASSWORD = "pw";

    try {
      const unauth = middleware(new NextRequest("http://localhost:3000/"));
      expect(unauth.status).toBe(401);

      const health = middleware(new NextRequest("http://localhost:3000/api/health"));
      expect(health.status).toBe(200);

      const creds = Buffer.from("admin:pw").toString("base64");
      const ok = middleware(
        new NextRequest("http://localhost:3000/api/apps", {
          headers: { Authorization: `Basic ${creds}` },
        }),
      );
      expect(ok.status).toBe(200);
    } finally {
      if (prevUser === undefined) delete process.env.WEB_UI_USERNAME;
      else process.env.WEB_UI_USERNAME = prevUser;
      if (prevPass === undefined) delete process.env.WEB_UI_PASSWORD;
      else process.env.WEB_UI_PASSWORD = prevPass;
    }
  });
});

describe("Control Plane BFF proxy", () => {
  it("resolves valid control plane origins and blocks self-proxy loops", () => {
    expect(
      resolveControlPlaneOrigin({
        SANDBOX_CONTROL_PLANE_URL: "https://ws--sandbox-control-plane-fastapi-app.modal.run/",
        APPS_BASE_DOMAIN: "apps.example.com",
      } as unknown as NodeJS.ProcessEnv),
    ).toBe("https://ws--sandbox-control-plane-fastapi-app.modal.run");

    expect(() =>
      resolveControlPlaneOrigin({
        SANDBOX_CONTROL_PLANE_URL: "https://apps.example.com",
        APPS_BASE_DOMAIN: "apps.example.com",
      } as unknown as NodeJS.ProcessEnv),
    ).toThrow(/proxy loop guard/);

    expect(() =>
      resolveControlPlaneOrigin({
        SANDBOX_CONTROL_PLANE_URL: "https://dashboard.apps.example.com",
        APPS_BASE_DOMAIN: "apps.example.com",
      } as unknown as NodeJS.ProcessEnv),
    ).toThrow(/proxy loop guard/);

    expect(() =>
      resolveControlPlaneOrigin({
        SANDBOX_CONTROL_PLANE_URL: "https://ws.modal.run/extra",
      } as unknown as NodeJS.ProcessEnv),
    ).toThrow(/origin without path/);
  });

  it("rejects path traversal segments", () => {
    expect(() => buildUpstreamApiUrl("https://ws.modal.run", ["..", "secret"], "")).toThrow();
  });

  it("injects server-side Basic Auth and forwards queries/errors", async () => {
    let capturedUrl = "";
    let capturedAuth = "";
    const env = {
      SANDBOX_CONTROL_PLANE_URL: "https://ws.modal.run",
      WEB_UI_USERNAME: "operator",
      WEB_UI_PASSWORD: "secret",
    } as unknown as NodeJS.ProcessEnv;

    const res = await proxyToControlPlane(
      new Request("http://localhost:3000/api/apps?profile=work"),
      ["apps"],
      {
        env,
        fetchImpl: async (input, init) => {
          capturedUrl = String(input);
          capturedAuth = new Headers(init?.headers).get("Authorization") ?? "";
          return Response.json(
            { detail: { code: "sandbox_stopped", message: "Stopped" } },
            { status: 409 },
          );
        },
      },
    );

    expect(capturedUrl).toBe("https://ws.modal.run/api/apps?profile=work");
    expect(capturedAuth).toBe(
      `Basic ${Buffer.from("operator:secret").toString("base64")}`,
    );
    expect(res.status).toBe(409);
    const json = (await res.json()) as { detail: { code: string } };
    expect(json.detail.code).toBe("sandbox_stopped");
  });

  it("streams text/event-stream responses unbuffered", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('data: {"type":"log","message":"ok"}\n\n'));
        controller.close();
      },
    });

    const res = await proxyToControlPlane(
      new Request("http://localhost:3000/api/sandboxes/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "repo", repo: "software-factory" }),
      }),
      ["sandboxes", "stream"],
      {
        env: {
          SANDBOX_CONTROL_PLANE_URL: "https://ws.modal.run",
          WEB_UI_USERNAME: "admin",
          WEB_UI_PASSWORD: "pw",
        } as unknown as NodeJS.ProcessEnv,
        fetchImpl: async () =>
          new Response(stream, {
            status: 200,
            headers: { "Content-Type": "text/event-stream" },
          }),
      },
    );

    expect(res.headers.get("content-type")).toContain("text/event-stream");
    expect(res.headers.get("x-accel-buffering")).toBe("no");
    expect(await res.text()).toContain('"type":"log"');
  });

  it("returns 502 if upstream fetch throws", async () => {
    const res = await proxyToControlPlane(
      new Request("http://localhost:3000/api/apps"),
      ["apps"],
      {
        env: {
          SANDBOX_CONTROL_PLANE_URL: "https://ws.modal.run",
          WEB_UI_USERNAME: "admin",
          WEB_UI_PASSWORD: "pw",
        } as unknown as NodeJS.ProcessEnv,
        fetchImpl: async () => {
          throw new Error("ECONNREFUSED");
        },
      },
    );
    expect(res.status).toBe(502);
    const body = (await res.json()) as { detail: string };
    expect(body.detail).toContain("ECONNREFUSED");
  });
});
