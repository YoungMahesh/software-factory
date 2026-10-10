import React, { useState, useEffect } from "react";
import {
  Boxes,
  Sparkles,
  Terminal,
  GitBranch,
} from "lucide-react";
import { Repo, Job, ChatMessage, LaunchJobParams } from "./types";
import { formatToolLabel } from "./utils";
import { StudioView } from "./views/StudioView";
import { TestingConsoleView } from "./views/TestingConsoleView";
import { ActivityDrawer } from "./components/ActivityDrawer";
import { useJobStream } from "./hooks/useJobStream";
import * as api from "./api";

const getInitialTab = (): "studio" | "console" => {
  if (typeof window !== "undefined" && window.location.pathname.includes("/console")) {
    return "console";
  }
  return "studio";
};

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<"studio" | "console">(getInitialTab);
  const [repos, setRepos] = useState<Repo[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<string>("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isSendingPrompt, setIsSendingPrompt] = useState<boolean>(false);
  const [isDrawerOpen, setIsDrawerOpen] = useState<boolean>(false);

  // Synchronize activeTab with URL history
  const switchTab = (tab: "studio" | "console") => {
    setActiveTab(tab);
    if (typeof window !== "undefined") {
      const targetPath = tab === "console" ? "/console" : "/";
      if (window.location.pathname !== targetPath) {
        window.history.pushState(null, "", targetPath);
      }
    }
  };

  useEffect(() => {
    const onPopState = () => {
      setActiveTab(getInitialTab());
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  // Real-time telemetry & logs stream
  const { job: streamedJob, logs, events, clearLogs } = useJobStream(activeJobId);

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
  }, [streamedJob]);

  // Rehydrate & sync assistant turn in chat history from telemetry events
  useEffect(() => {
    if (events.length === 0 || !activeJobId) return;

    setMessages((prev) => {
      let targetMsg = prev.find((m) => m.role === "assistant" && m.jobId === activeJobId);
      let isNew = false;
      if (!targetMsg) {
        isNew = true;
        targetMsg = {
          id: `assistant-${activeJobId}`,
          role: "assistant",
          timestamp: Date.now(),
          jobId: activeJobId,
          text: `Assembly line execution for ${activeJob?.feature || activeJob?.repo || activeJobId}`,
          stepChips: [],
        };
      }

      const updated: ChatMessage = {
        ...targetMsg,
        stepChips: [...(targetMsg.stepChips || [])],
      };

      // Process telemetry events to update thinking and step chips
      events.forEach((evt) => {
        if (evt.type === "thinking") {
          const delta = evt.data?.delta || "";
          const prevText = updated.thinking?.text || "";
          const newText = delta ? prevText + delta : prevText;
          updated.thinking = {
            text: newText,
            durationMs: evt.data?.durationMs || updated.thinking?.durationMs,
            done: Boolean(evt.data?.done) || Boolean(updated.thinking?.done),
          };
        }

        if (evt.type === "tool_result") {
          const chipId = evt.data?.toolCallId || `chip-${evt.data?.toolName}-${evt.timestamp || Date.now()}`;
          if (!updated.stepChips!.some((c) => c.id === chipId)) {
            const toolName = evt.data?.toolName || "tool";
            const label = `[${formatToolLabel(toolName, evt.data)}]`;

            updated.stepChips!.push({
              id: chipId,
              toolName,
              label,
              data: evt.data,
              stage: evt.stage,
              toolCallId: evt.data?.toolCallId,
            });
          }
        }
      });

      if (isNew) {
        return [...prev, updated];
      }
      return prev.map((m) => (m.id === updated.id ? updated : m));
    });
  }, [events, activeJobId, activeJob]);

  // Load repositories & jobs on mount
  const loadRepos = async () => {
    try {
      const data = await api.fetchStudioRepos();
      setRepos(data.repos || []);
      if (!selectedRepo && data.repos?.length > 0) {
        setSelectedRepo(data.repos[0].name);
      }
    } catch (err) {
      console.error("Failed to fetch repositories:", err);
    }
  };

  const loadJobs = async () => {
    try {
      const data = await api.listJobs();
      setJobs(data.jobs || []);
    } catch (err) {
      console.error("Failed to list jobs:", err);
    }
  };

  useEffect(() => {
    loadRepos();
    loadJobs();
  }, []);

  // Handle Create Repo
  const handleCreateRepo = async (params: { name: string; description?: string }) => {
    const newRepo = await api.createRepo(params);
    await loadRepos();
    setSelectedRepo(newRepo.name);
  };

  // Handle Launch Job from Testing Console
  const handleLaunchJob = async (params: LaunchJobParams) => {
    clearLogs();
    const createdJob = await api.launchJob(params);
    setActiveJobId(createdJob.id);
    setActiveJob(createdJob);
    setJobs((prev) => [createdJob, ...prev]);
  };

  // Handle Cancel Job
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

  // Handle Select Job from History
  const handleSelectJob = (job: Job) => {
    clearLogs();
    setActiveJobId(job.id);
    setActiveJob(job);
  };

  // Handle Prompt Submission from Factory Studio
  const handleSendPrompt = async (promptText: string) => {
    if (!selectedRepo || isSendingPrompt) return;

    // 1. Append user prompt
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      text: promptText,
      timestamp: Date.now(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsSendingPrompt(true);

    try {
      const res = await api.sendStudioPrompt({
        repo: selectedRepo,
        prompt: promptText,
        model: "deepseek-v4.1-flash",
        vm: false,
      });

      if (!res.accepted) {
        // Refusal
        const refusalMessage: ChatMessage = {
          id: `assistant-refusal-${Date.now()}`,
          role: "assistant",
          timestamp: Date.now(),
          refusal: {
            message: res.refusal || "Prompt was not accepted by Intent Guard.",
            reason: res.reason || undefined,
            category: res.category || undefined,
          },
        };
        setMessages((prev) => [...prev, refusalMessage]);
      } else {
        // Accepted & job created
        if (res.job) {
          clearLogs();
          setActiveJobId(res.job.id);
          setActiveJob(res.job);
          setJobs((prev) => [res.job!, ...prev]);

          const assistantMessage: ChatMessage = {
            id: `assistant-${res.job.id}`,
            role: "assistant",
            timestamp: Date.now(),
            jobId: res.job.id,
            stage: res.job.stage,
            text: `Dispatched assembly line targeting ${res.job.feature || res.job.repo}`,
            thinking: {
              text: "Initializing autonomous agent harness...",
              done: false,
            },
            stepChips: [],
          };
          setMessages((prev) => [...prev, assistantMessage]);
        }
      }
    } catch (err: any) {
      const errorMessage: ChatMessage = {
        id: `assistant-err-${Date.now()}`,
        role: "assistant",
        timestamp: Date.now(),
        text: `Error submitting prompt: ${err.message}`,
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsSendingPrompt(false);
    }
  };

  return (
    <div className="flex flex-col min-h-screen bg-slate-950 text-slate-100 font-sans">
      {/* Top Application Header */}
      <header className="h-14 border-b border-slate-800 bg-slate-900/90 backdrop-blur-md px-6 flex items-center justify-between z-30 shrink-0">
        <div className="flex items-center space-x-6">
          {/* Logo & Product Title */}
          <div className="flex items-center space-x-2.5">
            <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow-md">
              <Boxes className="w-4 h-4" />
            </div>
            <div className="flex items-center space-x-2">
              <span className="font-bold text-sm tracking-tight text-slate-100">
                Software Factory
              </span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-indigo-950 text-indigo-300 border border-indigo-800">
                v2
              </span>
            </div>
          </div>

          {/* Navigation View Switcher */}
          <nav className="flex items-center space-x-1 bg-slate-950 p-1 rounded-lg border border-slate-800">
            <button
              id="nav-tab-studio"
              type="button"
              onClick={() => switchTab("studio")}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
                activeTab === "studio"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
              }`}
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Factory Studio</span>
            </button>

            <button
              id="nav-tab-console"
              type="button"
              onClick={() => switchTab("console")}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
                activeTab === "console"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
              }`}
            >
              <Terminal className="w-3.5 h-3.5" />
              <span>Factory Testing Console</span>
            </button>
          </nav>
        </div>

        {/* Right Header Status / Links */}
        <div className="flex items-center space-x-3 text-xs text-slate-400">
          <a
            href="https://github.com/software-factory-09-test"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center space-x-1.5 hover:text-slate-200 transition-colors"
          >
            <GitBranch className="w-4 h-4" />
            <span className="hidden sm:inline">software-factory-09-test</span>
          </a>
        </div>
      </header>

      {/* Main Active View */}
      <main className="flex-1 overflow-auto">
        {activeTab === "studio" ? (
          <StudioView
            repos={repos}
            selectedRepo={selectedRepo}
            onSelectRepo={setSelectedRepo}
            onCreateRepo={handleCreateRepo}
            activeJob={activeJob}
            messages={messages}
            onSendPrompt={handleSendPrompt}
            onCancelJob={handleCancelJob}
            onSwitchToConsole={() => setActiveTab("console")}
            onOpenDrawer={() => setIsDrawerOpen(true)}
            isSending={isSendingPrompt}
          />
        ) : (
          <TestingConsoleView
            repos={repos}
            selectedRepo={selectedRepo}
            onSelectRepo={setSelectedRepo}
            onRefreshRepos={loadRepos}
            activeJob={activeJob}
            logs={logs}
            jobs={jobs}
            onLaunch={handleLaunchJob}
            onCancel={handleCancelJob}
            onSelectJob={handleSelectJob}
            onClearLogs={clearLogs}
          />
        )}
      </main>

      {/* Slide-over Agent Activity Drawer */}
      <ActivityDrawer
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        jobId={activeJob?.id}
        stage={activeJob?.stage}
        events={events}
        logs={logs}
      />
    </div>
  );
};

export default App;
