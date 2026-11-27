import { describe, it, expect } from "vitest";
import {
  CreateAppPayloadSchema,
  FactoryAppViewSchema,
  FreshLaunchStreamEventSchema,
  FreshSandboxLaunchPayloadSchema,
  LaunchStatusResponseSchema,
  PrimeSandboxViewSchema,
  RepositoryCatalogCacheSchema,
  SandboxCostSchema,
  SandboxCostsResponseSchema,
  SandboxSummarySchema,
  ScratchpadCatalogResponseSchema,
  ScratchpadDeleteResponseSchema,
  ScratchpadNoteDetailViewSchema,
  SnapshotSummarySchema,
} from "../src/index";

describe("@dashboard/types Zod contracts", () => {
  it("parses FactoryAppView, PrimeSandboxView, and LaunchStatusResponse", () => {
    const app = FactoryAppViewSchema.parse({
      app_id: "app-1",
      slug: "habit-tracker",
      title: "Habit Tracker",
      prompt: "Build a habit tracker",
      status: "ready",
      runtime_status: "running",
      created_at: "2026-11-26T10:00:00Z",
      updated_at: "2026-11-26T10:01:00Z",
    });
    expect(app.template).toBe("nextjs");
    expect(app.runtime_status).toBe("running");

    const prime = PrimeSandboxViewSchema.parse({
      prime_key: "default__vm-0__mob-0",
      status: "ready",
      runtime_status: "running",
      app_count: 2,
      app_ids: ["app-1", "app-2"],
      created_at: "2026-11-26T10:00:00Z",
      updated_at: "2026-11-26T10:01:00Z",
    });
    expect(prime.app_count).toBe(2);

    const status = LaunchStatusResponseSchema.parse({
      request: {
        request_id: "req-1",
        app_id: "app-1",
        status: "waiting_t3",
        current_label: "Waiting for T3 Code Server",
        steps: [
          { key: "launching_sandbox", label: "Provisioning Modal sandbox", status: "done" },
          { key: "waiting_t3", label: "Waiting for T3 Code Server", status: "active" },
        ],
        logs: ["Booted sandbox"],
        created_at: "2026-11-26T10:00:00Z",
        updated_at: "2026-11-26T10:00:30Z",
      },
      app: null,
    });
    expect(status.request.status).toBe("waiting_t3");
  });

  it("parses RepositoryCatalogCache and Scratchpad ADR 0095 payloads", () => {
    const repos = RepositoryCatalogCacheSchema.parse({
      org: "sFactory0",
      refreshed_at: "2026-11-26T10:00:00Z",
      repos: [
        { full_name: "sFactory0/demo", name: "demo", owner: "sFactory0", private: true },
      ],
    });
    expect(repos.repos[0].default_branch).toBe("main");

    const catalog = ScratchpadCatalogResponseSchema.parse({
      config_repo: "sFactory0/config",
      ideas_directory: "scratchpad",
      raw_directory: "raw",
      ideas: [
        {
          section: "ideas",
          filename: "my-idea.md",
          slug: "my-idea",
          path: "scratchpad/my-idea.md",
          title: "My Idea",
          sha: "abc123",
          size: 42,
        },
      ],
      raw: [],
    });
    expect(catalog.ideas[0].section).toBe("ideas");

    const detail = ScratchpadNoteDetailViewSchema.parse({
      section: "raw",
      filename: "dump.md",
      slug: "dump",
      path: "raw/dump.md",
      title: "dump",
      content: "verbatim text",
      sha: "def456",
    });
    expect(detail.section).toBe("raw");
  });

  it("parses SandboxSummary, SnapshotSummary, and SSE launch stream events", () => {
    const sb = SandboxSummarySchema.parse({
      id: "sb-1",
      name: "demo-box",
      running: true,
      exit_code: null,
      profile: "work",
    });
    expect(sb.running).toBe(true);

    const snap = SnapshotSummarySchema.parse({
      image_id: "im-123",
      name: "snap-1",
      ttl_days: 30,
      is_vm: true,
      rootfs_bytes: 1073741824,
    });
    expect(snap.is_vm).toBe(true);
    expect(snap.rootfs_bytes).toBe(1073741824);

    const createDefaults = CreateAppPayloadSchema.parse({ prompt: "Build CRM" });
    expect(createDefaults.vm).toBe(true);
    expect(createDefaults.memory).toBe(1);
    expect(createDefaults.t3).toBe(true);
    expect(createDefaults.modal).toBe(true);
    expect(createDefaults.sops).toBe(true);
    expect(createDefaults.no_cloudflare).toBe(true);

    const freshDefaults = FreshSandboxLaunchPayloadSchema.parse({});
    expect(freshDefaults.vm).toBe(true);
    expect(freshDefaults.t3).toBe(true);
    expect(freshDefaults.modal).toBe(true);
    expect(freshDefaults.sops).toBe(true);

    const deleted = ScratchpadDeleteResponseSchema.parse({
      section: "ideas",
      filename: "my-idea.md",
      path: "scratchpad/my-idea.md",
      deleted: true,
    });
    expect(deleted.deleted).toBe(true);

    const logEvt = FreshLaunchStreamEventSchema.parse({ type: "log", message: "Starting..." });
    const errEvt = FreshLaunchStreamEventSchema.parse({ type: "error", detail: "Boom" });
    const doneEvt = FreshLaunchStreamEventSchema.parse({
      type: "done",
      response: {
        sandbox_id: "sb-1",
        app_name: "software-factory",
        sandbox_name: "software-factory-1",
      },
    });
    expect(logEvt.type).toBe("log");
    expect(errEvt.type).toBe("error");
    expect(doneEvt.type).toBe("done");
    expect(() => FreshLaunchStreamEventSchema.parse({ type: "unknown" })).toThrow();

    const cost = SandboxCostSchema.parse({
      sandbox_id: "sb-1",
      profile: "maheshghamand",
      cost_usd: 0.929423,
      cost_by_resource_usd: { CPU: 0.3091, Memory: 0.6203 },
      duration_seconds: 35412,
      source: "sandbox_stats",
    });
    expect(cost.cost_usd).toBeCloseTo(0.929423);
    expect(cost.cached).toBe(false);

    const costsResponse = SandboxCostsResponseSchema.parse({
      fetched_at: "2026-11-26T13:02:00Z",
      costs: {
        "sb-1": cost,
        "sb-2": { sandbox_id: "sb-2", cost_usd: null, source: "sandbox_stats" },
      },
    });
    expect(costsResponse.costs["sb-2"].cost_usd).toBeNull();
    expect(costsResponse.costs["sb-2"].cost_by_resource_usd).toEqual({});
  });
});
