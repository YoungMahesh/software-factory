import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useJobStream } from "./useJobStream";

class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  close() {
    this.closed = true;
  }
}

describe("useJobStream hook", () => {
  const originalEventSource = global.EventSource;

  beforeEach(() => {
    MockEventSource.instances = [];
    (global as any).EventSource = MockEventSource;
  });

  afterEach(() => {
    global.EventSource = originalEventSource;
  });

  it("increments previewRefreshCount when preview_refresh event arrives", () => {
    const { result } = renderHook(() => useJobStream("job-123"));

    expect(MockEventSource.instances.length).toBe(1);
    const es = MockEventSource.instances[0];

    expect(result.current.previewRefreshCount).toBe(0);

    // Simulate preview_refresh event from telemetry stream
    act(() => {
      es.onmessage?.({
        data: JSON.stringify({
          event: "preview_refresh",
          repo: "my-app",
          job_id: "job-123",
        }),
      });
    });

    expect(result.current.previewRefreshCount).toBe(1);
  });
});
