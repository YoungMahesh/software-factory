import { useState, useEffect, useRef } from "react";
import { Job, AgentEvent, JobStage, JobStatus } from "../types";

export interface UseJobStreamResult {
  job: Job | null;
  logs: string[];
  events: AgentEvent[];
  isConnected: boolean;
  clearLogs: () => void;
}

export function useJobStream(jobId: string | null): UseJobStreamResult {
  const [job, setJob] = useState<Job | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      setLogs([]);
      setEvents([]);
      setIsConnected(false);
      return;
    }

    const es = new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/stream`);
    eventSourceRef.current = es;
    setIsConnected(true);

    es.onmessage = (e) => {
      if (!e.data || e.data === ": ping") return;
      try {
        const payload = JSON.parse(e.data);

        // 1. Initial sync snapshot
        if (payload.event === "init") {
          if (payload.job) setJob(payload.job);
          if (Array.isArray(payload.backlog)) setLogs(payload.backlog);
          if (Array.isArray(payload.events)) setEvents(payload.events);
          return;
        }

        // 2. Plain text log
        if (payload.event === "log") {
          const logData = payload.data;
          setLogs((prev) => [...prev, logData]);
          return;
        }

        // 3. Structured Agent Event
        if (payload.event === "agent_event") {
          const evt = payload.data as AgentEvent;
          setEvents((prev) => [...prev, evt]);
          return;
        }

        // 4. Stage transition
        if (payload.event === "stage") {
          const newStage = payload.stage as JobStage;
          setJob((prev) => (prev ? { ...prev, stage: newStage } : null));
          return;
        }

        // 5. Status update
        if (payload.event === "status") {
          const newStatus = payload.status as JobStatus;
          setJob((prev) => (prev ? { ...prev, status: newStatus } : null));
          return;
        }
      } catch (err) {
        console.error("Failed to parse SSE payload:", err, e.data);
      }
    };

    es.onerror = () => {
      setIsConnected(false);
    };

    return () => {
      es.close();
      eventSourceRef.current = null;
      setIsConnected(false);
    };
  }, [jobId]);

  const clearLogs = () => {
    setLogs([]);
  };

  return { job, logs, events, isConnected, clearLogs };
}
