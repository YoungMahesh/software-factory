import { describe, expect, it } from "vitest";
import type { LaunchStatusResponse } from "@dashboard/types";
import {
  createLaunchObserver,
  type LaunchObserverRequestResult,
} from "@/lib/launch-observer";

function deferred<T>() {
  let resolve!: (val: T) => void;
  let reject!: (err: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function reply(
  status: LaunchStatusResponse["request"]["status"] = "queued",
  extra: Partial<LaunchStatusResponse["request"]> = {},
): LaunchObserverRequestResult {
  return {
    ok: true,
    status: 200,
    json: async () => ({
      request: {
        request_id: "req-1",
        app_id: "app-1",
        kind: "create",
        status,
        current_label: status,
        steps: [],
        logs: [],
        created_at: "2026-11-26T00:00:00Z",
        updated_at: "2026-11-26T00:00:00Z",
        ...extra,
      },
      app: null,
    }),
  };
}

function harness() {
  const calls: Array<
    { id: string; signal: AbortSignal } & ReturnType<
      typeof deferred<LaunchObserverRequestResult>
    >
  > = [];
  const published: Array<LaunchStatusResponse | null> = [];
  const urls: Array<string | null> = [];
  const redirects: string[] = [];
  const errors: unknown[] = [];
  const timers = new Map<number, () => void>();
  let seq = 0;

  const observer = createLaunchObserver({
    request(id, signal) {
      const task = deferred<LaunchObserverRequestResult>();
      calls.push({ id, signal, ...task });
      return task.promise;
    },
    publish: (val) => published.push(val),
    setRequestId: (id) => urls.push(id),
    navigate: (url) => redirects.push(url),
    refresh: () => Promise.resolve(),
    reportError: (err) => errors.push(err),
    schedule: (fn) => {
      const key = ++seq;
      timers.set(key, fn);
      return key as unknown as ReturnType<typeof setTimeout>;
    },
    cancel: (key) => {
      timers.delete(key as unknown as number);
    },
  });

  function tick() {
    const first = timers.entries().next().value;
    if (!first) throw new Error("No scheduled timer");
    const [key, fn] = first;
    timers.delete(key);
    return fn();
  }

  return { observer, calls, published, urls, redirects, errors, timers, tick };
}

describe("createLaunchObserver", () => {
  it("dismissal rejects a late ready response even if transport ignores abort", async () => {
    const h = harness();
    const pending = h.observer.track("old");
    h.observer.dismiss();
    expect(h.calls[0].signal.aborted).toBe(true);
    h.calls[0].resolve(reply("ready", { handoff_url: "old-thread" }));
    await pending;
    expect(h.published.at(-1)).toBeNull();
    expect(h.redirects).toEqual([]);
    expect(h.urls.at(-1)).toBeNull();
    expect(h.timers.size).toBe(0);
  });

  it("switching requests ignores old replies and preserves the new lifetime", async () => {
    const h = harness();
    const oldTask = h.observer.track("old");
    const newTask = h.observer.track("new");
    h.calls[1].resolve(reply());
    await newTask;
    h.calls[0].resolve(reply("ready", { handoff_url: "old-thread" }));
    await oldTask;
    expect(h.published.at(-1)?.request.status).toBe("queued");
    expect(h.urls.at(-1)).toBe("new");
    expect(h.timers.size).toBe(1);
    expect(h.redirects).toEqual([]);
    h.observer.destroy();
  });

  it("switching while reading JSON also rejects the old response", async () => {
    const h = harness();
    const jsonDef = deferred<LaunchStatusResponse>();
    const oldTask = h.observer.track("old");
    h.calls[0].resolve({
      ok: true,
      status: 200,
      json: () => jsonDef.promise,
    });
    await Promise.resolve();
    const newTask = h.observer.track("new");
    jsonDef.resolve({
      request: {
        request_id: "old",
        app_id: "app-1",
        kind: "create",
        status: "ready",
        current_label: "ready",
        steps: [],
        logs: [],
        handoff_url: "old-thread",
        created_at: "2026-11-26T00:00:00Z",
        updated_at: "2026-11-26T00:00:00Z",
      },
      app: null,
    });
    h.calls[1].resolve(reply("failed"));
    await Promise.all([oldTask, newTask]);
    expect(h.published.at(-1)?.request.status).toBe("failed");
    expect(h.redirects).toEqual([]);
  });

  it("polls sequentially, retries transient failures, and stops on terminal failure", async () => {
    const h = harness();
    const initial = h.observer.track("one");
    expect(h.timers.size).toBe(0);
    h.calls[0].reject(new Error("offline"));
    await initial;
    expect(h.errors).toHaveLength(1);
    h.tick();
    expect(h.timers.size).toBe(0);
    h.calls[1].resolve(reply("failed"));
    await Promise.resolve();
    await Promise.resolve();
    expect(h.timers.size).toBe(0);
  });

  it("clears progress and URL on 404 and stops polling", async () => {
    const h = harness();
    const task = h.observer.track("gone");
    h.calls[0].resolve({
      ok: false,
      status: 404,
      json: async () => {
        throw new Error("not found");
      },
    });
    await task;
    expect(h.published.at(-1)).toBeNull();
    expect(h.urls.at(-1)).toBeNull();
    expect(h.timers.size).toBe(0);
  });

  it("hands off once per request even if tracked again", async () => {
    const h = harness();
    for (let i = 0; i < 2; i += 1) {
      const task = h.observer.track("one");
      h.calls[i].resolve(reply("ready", { handoff_url: "thread-url" }));
      await task;
    }
    expect(h.redirects).toEqual(["thread-url"]);
    expect(h.timers.size).toBe(0);
  });

  it("dismissal during refresh prevents navigation", async () => {
    const refreshDef = deferred<void>();
    const responseDef = deferred<LaunchObserverRequestResult>();
    const redirects: string[] = [];
    const observer = createLaunchObserver({
      request: () => responseDef.promise,
      publish() {},
      setRequestId() {},
      refresh: () => refreshDef.promise,
      navigate: (url) => redirects.push(url),
    });
    const task = observer.track("one");
    responseDef.resolve(reply("ready", { handoff_url: "thread-url" }));
    await Promise.resolve();
    await Promise.resolve();
    observer.dismiss();
    refreshDef.resolve();
    await task;
    expect(redirects).toEqual([]);
  });

  it("destroy cancels polling while preserving URL for reload restoration", async () => {
    const h = harness();
    const task = h.observer.track("one");
    h.calls[0].resolve(reply());
    await task;
    h.observer.destroy();
    expect(h.timers.size).toBe(0);
    expect(h.urls.at(-1)).toBe("one");
  });
});
