"use client";

import { useCallback, useEffect, useRef } from "react";
import type { LaunchStatusResponse } from "@dashboard/types";
import { createLaunchObserver, type LaunchObserver } from "@/lib/launch-observer";

export interface UseLaunchObserverOptions {
  onStatus: (data: LaunchStatusResponse | null) => void;
  onRefresh: () => Promise<void>;
}

export function useLaunchObserver({ onStatus, onRefresh }: UseLaunchObserverOptions) {
  const onStatusRef = useRef(onStatus);
  const onRefreshRef = useRef(onRefresh);
  const observerRef = useRef<LaunchObserver | null>(null);

  useEffect(() => {
    onStatusRef.current = onStatus;
    onRefreshRef.current = onRefresh;
  }, [onStatus, onRefresh]);

  useEffect(() => {
    return () => {
      observerRef.current?.destroy();
    };
  }, []);

  const getObserver = useCallback((): LaunchObserver => {
    if (observerRef.current === null) {
      observerRef.current = createLaunchObserver({
        request: async (id, signal) => {
          const res = await fetch(`/api/launches/${encodeURIComponent(id)}`, {
            signal,
            cache: "no-store",
          });
          return {
            ok: res.ok,
            status: res.status,
            json: () => res.json() as Promise<LaunchStatusResponse>,
          };
        },
        publish: (data) => onStatusRef.current(data),
        refresh: () => onRefreshRef.current(),
        setRequestId: (id) => {
          if (typeof window === "undefined") return;
          const url = new URL(window.location.href);
          if (id) {
            url.searchParams.set("launch", id);
          } else {
            url.searchParams.delete("launch");
          }
          window.history.replaceState({}, "", url.toString());
        },
        navigate: (url) => {
          if (typeof window !== "undefined") {
            window.location.assign(url);
          }
        },
      });
    }
    return observerRef.current;
  }, []);

  const track = useCallback(
    (requestId: string) => getObserver().track(requestId),
    [getObserver],
  );

  const dismiss = useCallback(() => {
    observerRef.current?.dismiss();
  }, []);

  return { track, dismiss };
}
