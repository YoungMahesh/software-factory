import type { LaunchStatusResponse } from "@dashboard/types";

export interface LaunchObserverRequestResult {
  ok: boolean;
  status: number;
  json(): Promise<LaunchStatusResponse>;
}

export interface LaunchObserverDeps {
  request: (requestId: string, signal: AbortSignal) => Promise<LaunchObserverRequestResult>;
  publish: (data: LaunchStatusResponse | null) => void;
  refresh: () => Promise<void>;
  setRequestId: (requestId: string | null) => void;
  navigate: (url: string) => void;
  schedule?: (fn: () => void, ms: number) => ReturnType<typeof setTimeout>;
  cancel?: (timerId: ReturnType<typeof setTimeout>) => void;
  reportError?: (error: unknown) => void;
  interval?: number;
}

export interface LaunchObserver {
  track(requestId: string | null | undefined): Promise<void>;
  dismiss(): void;
  destroy(): void;
}

interface ActiveSession {
  id: string;
  controller: AbortController;
  timer: ReturnType<typeof setTimeout> | null;
}

export function createLaunchObserver({
  request,
  publish,
  refresh,
  setRequestId,
  navigate,
  schedule = setTimeout,
  cancel = clearTimeout,
  reportError = console.error,
  interval = 1500,
}: LaunchObserverDeps): LaunchObserver {
  let active: ActiveSession | null = null;
  const handedOff = new Set<string>();

  function stop(): void {
    const previous = active;
    active = null;
    if (previous) {
      previous.controller.abort();
      if (previous.timer !== null) {
        cancel(previous.timer);
      }
    }
  }

  async function poll(session: ActiveSession): Promise<void> {
    if (active !== session) return;
    let terminal = false;
    try {
      const response = await request(session.id, session.controller.signal);
      if (active !== session) return;
      if (response.status === 404) {
        terminal = true;
        publish(null);
        setRequestId(null);
        return;
      }
      if (!response.ok) {
        throw new Error(`Launch status request failed (${response.status})`);
      }
      const data = await response.json();
      if (active !== session) return;
      publish(data);
      const status = data.request?.status;
      terminal = status === "ready" || status === "failed";
      if (terminal) {
        await refresh();
        if (active !== session) return;
        if (
          data.request.status === "ready" &&
          data.request.handoff_url &&
          !handedOff.has(session.id)
        ) {
          handedOff.add(session.id);
          setRequestId(null);
          navigate(data.request.handoff_url);
        }
      }
    } catch (error) {
      const isAbort = error instanceof Error && error.name === "AbortError";
      if (active === session && !isAbort) {
        reportError(error);
      }
    } finally {
      if (active === session && !terminal) {
        session.timer = schedule(() => {
          void poll(session);
        }, interval);
      }
    }
  }

  return {
    track(requestId) {
      if (!requestId) return Promise.resolve();
      stop();
      publish(null);
      const session: ActiveSession = {
        id: requestId,
        controller: new AbortController(),
        timer: null,
      };
      active = session;
      setRequestId(requestId);
      return poll(session);
    },
    dismiss() {
      stop();
      publish(null);
      setRequestId(null);
    },
    destroy: stop,
  };
}
