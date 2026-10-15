import { useEffect } from "react";
import { PreviewState } from "../types";
import { createStoppedPreviewState } from "./useStudioQueries";
import * as api from "../api";

export interface UsePreviewStreamParams {
  selectedRepo: string;
  previewState: PreviewState | null;
  setPreviewState: React.Dispatch<React.SetStateAction<PreviewState | null>>;
  onPreviewRefresh?: () => void;
}

export function usePreviewStream({
  selectedRepo,
  previewState,
  setPreviewState,
  onPreviewRefresh,
}: UsePreviewStreamParams) {
  useEffect(() => {
    if (!selectedRepo) return;
    if (
      !previewState ||
      (previewState.status !== "PROVISIONING" && previewState.status !== "SERVING")
    ) {
      return;
    }

    const streamUrl = api.getPreviewStreamUrl(selectedRepo);
    let es: EventSource | null = null;
    try {
      es = new EventSource(streamUrl);
    } catch (err) {
      return;
    }

    es.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.event === "init") {
          setPreviewState((prev) => {
            if (!prev) return prev;
            return {
              ...prev,
              ...payload.preview,
              status: payload.status || prev.status,
              preview_url: payload.preview_url !== undefined ? payload.preview_url : prev.preview_url,
              logs: payload.backlog || prev.logs || [],
            } as PreviewState;
          });
        } else if (payload.event === "log") {
          setPreviewState((prev) => {
            if (!prev) return prev;
            return {
              ...prev,
              logs: [...(prev.logs || []), payload.data],
            } as PreviewState;
          });
        } else if (payload.event === "stage") {
          setPreviewState((prev) => {
            if (!prev) return prev;
            if (prev.status === "PROVISIONING") {
              return {
                ...prev,
                stage: payload.stage,
              };
            }
            return prev;
          });
        } else if (payload.event === "status") {
          setPreviewState((prev) => {
            if (!prev) return prev;
            if (payload.status === "SERVING") {
              return {
                status: "SERVING",
                branch: prev.branch || "main",
                preview_url: payload.preview_url || (prev.status === "SERVING" ? prev.preview_url : ""),
                logs: prev.logs || [],
                error_message: null,
              };
            } else if (payload.status === "STOPPED") {
              return createStoppedPreviewState(prev);
            } else if (payload.status === "FAILED") {
              return {
                status: "FAILED",
                branch: prev.branch,
                preview_url: null,
                logs: prev.logs || [],
                error_message: payload.error || "Preview failed",
              };
            } else if (payload.status === "PROVISIONING") {
              return {
                status: "PROVISIONING",
                stage: "PROVISIONING",
                branch: prev.branch || "main",
                preview_url: null,
                logs: prev.logs || [],
                error_message: null,
              };
            }
            return prev;
          });
          if (payload.status === "STOPPED" || payload.status === "FAILED") {
            es?.close();
          }
        } else if (payload.event === "preview_refresh") {
          if (onPreviewRefresh) {
            onPreviewRefresh();
          }
        }
      } catch (e) {
        // ignore parse error or ping
      }
    };

    es.onerror = () => {
      // Reconnects automatically unless closed
    };

    return () => {
      es?.close();
    };
  }, [selectedRepo, previewState?.status === "PROVISIONING" || previewState?.status === "SERVING"]);
}
