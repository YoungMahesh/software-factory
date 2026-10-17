import { useEffect } from "react";
import { Job } from "../types";
import * as api from "../api";

export interface UseConsoleJobsParams {
  setActiveJobId: React.Dispatch<React.SetStateAction<string | null>>;
  setActiveJob: React.Dispatch<React.SetStateAction<Job | null>>;
  activeJob: Job | null;
  setJobs: React.Dispatch<React.SetStateAction<Job[]>>;
  clearLogs: () => void;
}

export function useConsoleJobs({
  setActiveJobId,
  setActiveJob,
  activeJob,
  setJobs,
  clearLogs,
}: UseConsoleJobsParams) {
  const loadJobs = async () => {
    try {
      const data = await api.listJobs();
      setJobs(data.jobs || []);
    } catch (err) {
      console.error("Failed to list jobs:", err);
    }
  };

  useEffect(() => {
    loadJobs();
  }, []);

  const handleCancelJob = async (jobId: string) => {
    try {
      await api.cancelJob(jobId);
      if (activeJob && activeJob.id === jobId) {
        setActiveJob({ ...activeJob, status: "CANCELLED" });
      }
      loadJobs();
    } catch (err) {
      console.error("Failed to cancel job:", err);
    }
  };

  const handleSelectJob = (job: Job) => {
    clearLogs();
    setActiveJobId(job.id);
    setActiveJob(job);
  };

  return {
    handleCancelJob,
    handleSelectJob,
    loadJobs,
  };
}
