import { describe, expect, it } from "vitest";
import type { FreshLaunchStreamEvent } from "@dashboard/types";
import {
  consumeSseStream,
  extractApiError,
  formatCostBreakdown,
  formatDurationCompact,
  formatUsdCost,
  getLaunchSshCommand,
  getLaunchSshConfig,
  getSandboxCopyTarget,
  previewScratchpadTargetPath,
  summarizeSandboxCosts,
} from "@/lib/format";

describe("format and SSE stream utilities", () => {
  it("parses chunked SSE stream events cleanly", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('data: {"type":"log","mess'));
        controller.enqueue(
          encoder.encode('age":"Step 1"}\n\ndata: {"type":"done","response":{"sandbox_id":"sb-1","app_name":"app","sandbox_name":"app-1"}}\n\n'),
        );
        controller.close();
      },
    });
    const events: FreshLaunchStreamEvent[] = [];
    await consumeSseStream(new Response(stream), (evt) => events.push(evt));
    expect(events).toHaveLength(2);
    expect(events[0]).toEqual({ type: "log", message: "Step 1" });
    expect(events[1].type).toBe("done");
  });

  it("computes collision-free Scratchpad target paths", () => {
    const path = previewScratchpadTargetPath(
      "Habit Tracker",
      [
        {
          section: "ideas",
          filename: "habit-tracker.md",
          slug: "habit-tracker",
          path: "scratchpad/habit-tracker.md",
          title: "Habit Tracker",
          sha: "1",
          size: 10,
        },
      ],
      "sFactory0/config",
    );
    expect(path).toBe("sFactory0/config/scratchpad/habit-tracker-2.md");
  });

  it("builds SSH command and config snippets from LaunchResponse and SandboxSummary", () => {
    const res = {
      sandbox_id: "sb-1",
      app_name: "my-app",
      sandbox_name: "my-app-1234",
      ssh_info: ["r123.modal.host", 36000] as [string, number],
      t3_persist: false,
      cloudflare_enabled: true,
      sops_enabled: false,
      is_vm: false,
    };
    expect(getLaunchSshCommand(res)).toContain("-p 36000 root@r123.modal.host");
    expect(getLaunchSshConfig(res)).toContain("Host my-app-1234");
    expect(
      getSandboxCopyTarget({ id: "sb-1", name: "box", running: true }),
    ).toEqual({
      text: "ssh box",
      toast: "SSH command copied: ssh box",
    });
  });

  it("extracts both string and structured FastAPI error details", async () => {
    const strErr = await extractApiError(
      Response.json({ detail: "Bad request" }, { status: 400 }),
    );
    expect(strErr).toEqual({ message: "Bad request" });

    const objErr = await extractApiError(
      Response.json(
        { detail: { code: "sandbox_stopped", message: "Sandbox stopped" } },
        { status: 409 },
      ),
    );
    expect(objErr).toEqual({
      code: "sandbox_stopped",
      message: "Sandbox stopped",
    });
  });

  it("formats sandbox USD costs, resource breakdowns, durations, and summaries", () => {
    expect(formatUsdCost(null)).toBe("—");
    expect(formatUsdCost(0)).toBe("$0.00");
    expect(formatUsdCost(0.00004)).toBe("<$0.0001");
    expect(formatUsdCost(0.00419)).toBe("$0.0042");
    expect(formatUsdCost(0.929423)).toBe("$0.93");

    expect(
      formatCostBreakdown({ Memory: 0.6203, H100: 1.5, CPU: 0.3091, Zero: 0 }),
    ).toBe("CPU $0.31 · Mem $0.62 · H100 $1.50");
    expect(formatCostBreakdown({})).toBe("");

    expect(formatDurationCompact(30)).toBe("<1m");
    expect(formatDurationCompact(900)).toBe("15m");
    expect(formatDurationCompact(7200)).toBe("2h");
    expect(formatDurationCompact(35412)).toBe("9h 50m");

    const summary = summarizeSandboxCosts(
      [{ id: "sb-1" }, { id: "sb-2" }],
      {
        "sb-1": {
          sandbox_id: "sb-1",
          cost_usd: 0.83,
          cost_by_resource_usd: {},
          source: "sandbox_stats",
          cached: false,
        },
        "sb-2": {
          sandbox_id: "sb-2",
          cost_usd: null,
          cost_by_resource_usd: {},
          source: "sandbox_stats",
          cached: false,
        },
        "sb-stale": {
          sandbox_id: "sb-stale",
          cost_usd: 99,
          cost_by_resource_usd: {},
          source: "sandbox_stats",
          cached: false,
        },
      },
    );
    expect(summary).toEqual({ totalUsd: 0.83, knownCount: 1, pendingCount: 1 });
  });
});
