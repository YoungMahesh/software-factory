import { describe, expect, it } from "vitest";
import type { FreshLaunchStreamEvent } from "@dashboard/types";
import {
  consumeSseStream,
  extractApiError,
  getLaunchSshCommand,
  getLaunchSshConfig,
  getSandboxCopyTarget,
  previewScratchpadTargetPath,
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
});
