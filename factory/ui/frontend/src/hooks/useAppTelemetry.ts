import { useEffect } from "react";
import { Job, ChatMessage } from "../types";
import { useJobStream } from "./useJobStream";
import { foldTelemetryEvents } from "../utils/telemetryEvents";

export interface UseAppTelemetryParams {
  activeJobId: string | null;
  activeJob: Job | null;
  setActiveJob: React.Dispatch<React.SetStateAction<Job | null>>;
  setJobs: React.Dispatch<React.SetStateAction<Job[]>>;
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  onPreviewRefresh?: () => void;
}

export function useAppTelemetry({
  activeJobId,
  activeJob,
  setActiveJob,
  setJobs,
  setMessages,
  onPreviewRefresh,
}: UseAppTelemetryParams) {
  const { job: streamedJob, logs, events, clearLogs, previewRefreshCount } = useJobStream(activeJobId);

  useEffect(() => {
    if (previewRefreshCount > 0 && onPreviewRefresh) {
      onPreviewRefresh();
    }
  }, [previewRefreshCount, onPreviewRefresh]);

  // Sync streamed job state to activeJob and jobs list
  useEffect(() => {
    if (streamedJob) {
      setActiveJob(streamedJob);
      setJobs((prev) => {
        const idx = prev.findIndex((j) => j.id === streamedJob.id);
        if (idx >= 0) {
          const next = [...prev];
          next[idx] = streamedJob;
          return next;
        }
        return [streamedJob, ...prev];
      });
    }
  }, [streamedJob, setActiveJob, setJobs]);

  // Rehydrate & sync assistant turn in chat history from telemetry events
  useEffect(() => {
    if (events.length === 0 || !activeJobId) return;
    setMessages((prev) => foldTelemetryEvents(prev, events, activeJobId, activeJob));
  }, [events, activeJobId, activeJob, setMessages]);

  return {
    streamedJob,
    logs,
    events,
    clearLogs,
    previewRefreshCount,
  };
}
