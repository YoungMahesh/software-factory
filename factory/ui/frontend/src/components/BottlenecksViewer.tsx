import React, { useState, useMemo, useCallback, useEffect } from "react";
import { Loader2, Copy, Check } from "lucide-react";
import { fetchRepoBottlenecks } from "../api";
import { copyToClipboard } from "../utils";
import { RepoBottleneck } from "../types";
import {
  BottlenecksViewerProps,
  BottleneckItem,
  StageFilter,
  CategoryFilter,
  classifyBottleneck,
  BottleneckCard,
  RepoBottlenecksTable,
  formatBottlenecksMarkdown,
} from "./bottlenecks";

export type { BottlenecksViewerProps, BottleneckItem };

const STAGE_FILTERS: StageFilter[] = ["All", "Planner", "Coder", "Verifier", "Reviewer"];
const CATEGORY_FILTERS: CategoryFilter[] = ["All", "Commands", "Thinking"];

export const BottlenecksViewer: React.FC<BottlenecksViewerProps> = ({
  events = [],
  repo,
  initialScope = "current",
}) => {
  const [scope, setScope] = useState<"current" | "repo">(initialScope);
  const [repoBottlenecks, setRepoBottlenecks] = useState<RepoBottleneck[]>([]);
  const [isLoadingRepo, setIsLoadingRepo] = useState<boolean>(false);
  const [repoError, setRepoError] = useState<string | null>(null);

  const loadRepoBottlenecks = useCallback(async (targetRepo?: string) => {
    const clean = (targetRepo || "").trim();
    if (!clean) {
      setRepoBottlenecks([]);
      return;
    }
    setIsLoadingRepo(true);
    setRepoError(null);
    try {
      const res = await fetchRepoBottlenecks(clean);
      setRepoBottlenecks(res.bottlenecks || []);
    } catch (err: any) {
      setRepoError(err?.message || "Failed to load repository bottlenecks.");
    } finally {
      setIsLoadingRepo(false);
    }
  }, []);

  useEffect(() => {
    if (scope === "repo" && repo) {
      loadRepoBottlenecks(repo);
    }
  }, [scope, repo, loadRepoBottlenecks]);

  const [hideMicroCommands, setHideMicroCommands] = useState<boolean>(false);
  const [selectedStage, setSelectedStage] = useState<StageFilter>("All");
  const [selectedCategory, setSelectedCategory] = useState<CategoryFilter>("All");
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [copied, setCopied] = useState<boolean>(false);

  const handleToggleExpand = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  // Detect actively executing command or tool
  const activeTool = useMemo(() => {
    const completedToolIds = new Set<string>();
    let lastResultIndex = -1;

    for (let i = 0; i < events.length; i++) {
      if (events[i].type === "tool_result") {
        lastResultIndex = i;
        if (events[i].data?.toolCallId) {
          completedToolIds.add(events[i].data.toolCallId);
        }
      }
    }

    for (let i = events.length - 1; i >= 0; i--) {
      const evt = events[i];
      if (evt.type === "tool_start") {
        const callId = evt.data?.toolCallId;
        const isRunning = callId ? !completedToolIds.has(callId) : i > lastResultIndex;
        if (isRunning) {
          return {
            command:
              evt.data?.command ||
              evt.data?.args?.command ||
              evt.data?.toolName ||
              "Running operation",
            stage: evt.stage,
          };
        }
      }
    }
    return null;
  }, [events]);

  // Extract completed operations and thinking sessions
  const items = useMemo(() => {
    const extracted: BottleneckItem[] = [];

    // Map tool_start events for command and argument lookups
    const toolStartMap = new Map<string, (typeof events)[number]>();
    events.forEach((evt) => {
      if (evt.type === "tool_start" && evt.data?.toolCallId) {
        toolStartMap.set(evt.data.toolCallId, evt);
      }
    });

    // 1. Fold thinking events by stage until marked done
    const thinkingBlocks: {
      stage?: string;
      text: string;
      durationMs?: number;
      done?: boolean;
    }[] = [];

    events.forEach((evt) => {
      if (evt.type === "thinking") {
        const last = thinkingBlocks[thinkingBlocks.length - 1];
        if (last && last.stage === evt.stage && !last.done) {
          const delta = evt.data?.delta || "";
          last.text = delta ? last.text + delta : evt.data?.text || last.text;
          if (evt.data?.durationMs !== undefined) last.durationMs = evt.data.durationMs;
          if (evt.data?.done !== undefined) last.done = Boolean(evt.data.done);
        } else {
          thinkingBlocks.push({
            stage: evt.stage,
            text: evt.data?.delta || evt.data?.text || "",
            durationMs: evt.data?.durationMs,
            done: Boolean(evt.data?.done),
          });
        }
      }
    });

    thinkingBlocks.forEach((thinkingBlock, idx) => {
      if (thinkingBlock.durationMs !== undefined && thinkingBlock.durationMs >= 0) {
        extracted.push({
          id: `thinking-${idx}-${thinkingBlock.stage || "unknown"}`,
          type: "thinking",
          title: `LLM Thinking (${thinkingBlock.stage || "Agent"})`,
          durationMs: thinkingBlock.durationMs,
          stage: thinkingBlock.stage,
          output: thinkingBlock.text,
          category: "LLM Thinking",
        });
      }
    });

    // 2. Extract completed bash commands and verifier test runs
    events.forEach((evt, idx) => {
      if (evt.type === "tool_result") {
        const startEvt = evt.data?.toolCallId ? toolStartMap.get(evt.data.toolCallId) : undefined;
        const toolName = (evt.data?.toolName || startEvt?.data?.toolName || "").toLowerCase();
        const stage = evt.stage || startEvt?.stage;
        const isBash = toolName === "bash";
        const isVerifier = stage === "VERIFIER";

        if (isBash || isVerifier) {
          const cmd =
            evt.data?.command ||
            evt.data?.args?.command ||
            startEvt?.data?.command ||
            startEvt?.data?.args?.command ||
            toolName ||
            "bash";
          extracted.push({
            id: evt.data?.toolCallId || `tool-res-${idx}`,
            type: "command",
            title: cmd,
            durationMs: evt.data?.durationMs ?? 0,
            stage,
            exitCode: evt.data?.exitCode,
            isError: Boolean(evt.data?.isError),
            output: evt.data?.output || evt.data?.stdout || "",
            stderr: evt.data?.stderr || startEvt?.data?.stderr,
            cwd:
              evt.data?.cwd ||
              evt.data?.args?.cwd ||
              startEvt?.data?.cwd ||
              startEvt?.data?.args?.cwd,
            category: classifyBottleneck({
              type: "command",
              command: cmd,
              stage,
            }),
          });
        }
      }
    });

    // Sort strictly in descending order of durationMs
    extracted.sort((a, b) => b.durationMs - a.durationMs);
    return extracted;
  }, [events]);

  const maxDurationMs = useMemo(() => {
    if (items.length === 0) return 1;
    return Math.max(...items.map((i) => i.durationMs), 1);
  }, [items]);

  // Apply stage, category, and micro-command filters
  const displayedItems = useMemo(() => {
    return items.filter((item) => {
      // Micro-command threshold filter
      if (hideMicroCommands && item.type === "command" && item.durationMs < 100) {
        return false;
      }

      // Stage pill filter
      if (
        selectedStage !== "All" &&
        item.stage?.toUpperCase() !== selectedStage.toUpperCase()
      ) {
        return false;
      }

      // Category toggle filter
      if (selectedCategory === "Commands" && item.type !== "command") {
        return false;
      }
      if (selectedCategory === "Thinking" && item.type !== "thinking") {
        return false;
      }

      return true;
    });
  }, [items, hideMicroCommands, selectedStage, selectedCategory]);

  const handleCopySummary = useCallback(async () => {
    const md = formatBottlenecksMarkdown(displayedItems);
    const ok = await copyToClipboard(md);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [displayedItems]);

  return (
    <div id="bottlenecks-viewer" className="space-y-4">
      {/* Scope Toggle: Current Run vs. Repository Aggregates */}
      <div className="flex items-center justify-between p-1 bg-soft-stone/60 rounded-xl border border-hairline/80">
        <div className="flex items-center space-x-1 w-full" data-testid="scope-toggles">
          <button
            type="button"
            data-testid="scope-toggle-current-run"
            onClick={() => setScope("current")}
            className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-mono font-medium transition-colors cursor-pointer text-center ${
              scope === "current"
                ? "bg-white text-ink shadow-xs font-semibold"
                : "text-muted hover:text-ink hover:bg-white/50"
            }`}
          >
            Current Run
          </button>
          <button
            type="button"
            data-testid="scope-toggle-repo-aggregates"
            onClick={() => setScope("repo")}
            className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-mono font-medium transition-colors cursor-pointer text-center ${
              scope === "repo"
                ? "bg-white text-ink shadow-xs font-semibold"
                : "text-muted hover:text-ink hover:bg-white/50"
            }`}
          >
            Repository Aggregates
          </button>
        </div>
      </div>

      {scope === "repo" ? (
        <RepoBottlenecksTable
          repo={repo}
          bottlenecks={repoBottlenecks}
          isLoading={isLoadingRepo}
          error={repoError}
          onRetry={() => loadRepoBottlenecks(repo)}
        />
      ) : (
        <>
          {/* Active Running Banner */}
      {activeTool && (
        <div
          data-testid="active-execution-banner"
          id="active-execution-banner"
          className="flex items-center justify-between p-3 rounded-xl bg-primary text-white border border-white/10 shadow-sm"
        >
          <div className="flex items-center space-x-2.5 truncate">
            <Loader2
              data-testid="active-running-spinner"
              className="w-4 h-4 text-emerald-400 animate-spin shrink-0"
            />
            <div className="truncate">
              <span className="text-[10px] font-mono uppercase tracking-wider text-slate-300 block">
                Actively Running {activeTool.stage ? `[${activeTool.stage}]` : ""}
              </span>
              <span className="text-xs font-mono font-semibold text-white truncate block">
                {activeTool.command}
              </span>
            </div>
          </div>
          <span className="px-2 py-0.5 rounded-pill text-[10px] font-mono bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shrink-0">
            Running
          </span>
        </div>
      )}

      {/* Filter and Exploration Controls */}
      <div className="space-y-2 bg-soft-stone/30 p-2.5 rounded-xl border border-hairline/60">
        {/* Stage Filter Pills */}
        <div className="flex items-center justify-between gap-2">
          <span className="text-[10px] font-mono uppercase tracking-wider text-muted font-bold shrink-0">
            Stage
          </span>
          <div className="flex items-center space-x-1 overflow-x-auto" data-testid="stage-filter-pills">
            {STAGE_FILTERS.map((stage) => {
              const isSelected = selectedStage === stage;
              return (
                <button
                  key={stage}
                  type="button"
                  data-testid={`stage-filter-${stage.toLowerCase()}`}
                  onClick={() => setSelectedStage(stage)}
                  className={`px-2 py-0.5 rounded-pill text-[10px] font-mono transition-colors cursor-pointer ${
                    isSelected
                      ? "bg-primary text-white font-semibold shadow-xs"
                      : "bg-white text-slate-600 hover:text-ink hover:bg-soft-stone border border-hairline/80"
                  }`}
                >
                  {stage}
                </button>
              );
            })}
          </div>
        </div>

        {/* Category Toggles & Micro-command Threshold */}
        <div className="flex items-center justify-between gap-2 pt-1 border-t border-hairline/40">
          <div className="flex items-center space-x-1.5" data-testid="category-toggles">
            <span className="text-[10px] font-mono uppercase tracking-wider text-muted font-bold shrink-0">
              Category
            </span>
            {CATEGORY_FILTERS.map((cat) => {
              const isSelected = selectedCategory === cat;
              return (
                <button
                  key={cat}
                  type="button"
                  data-testid={`category-toggle-${cat.toLowerCase()}`}
                  onClick={() => setSelectedCategory(cat)}
                  className={`px-2 py-0.5 rounded-pill text-[10px] font-mono transition-colors cursor-pointer ${
                    isSelected
                      ? "bg-primary text-white font-semibold shadow-xs"
                      : "bg-white text-slate-600 hover:text-ink hover:bg-soft-stone border border-hairline/80"
                  }`}
                >
                  {cat}
                </button>
              );
            })}
          </div>

          <label
            htmlFor="toggle-hide-micro-commands"
            className="flex items-center space-x-1.5 text-muted hover:text-ink cursor-pointer select-none text-[10px] font-mono shrink-0"
          >
            <input
              id="toggle-hide-micro-commands"
              type="checkbox"
              checked={hideMicroCommands}
              onChange={(e) => setHideMicroCommands(e.target.checked)}
              className="rounded border-hairline text-primary focus:ring-primary h-3 w-3 cursor-pointer"
            />
            <span>Hide micro-commands (&lt;100ms)</span>
          </label>
        </div>
      </div>

      {/* Header bar displaying count and export control */}
      <div className="flex items-center justify-between px-1 text-xs">
        <span className="font-sans font-semibold text-ink">
          Ranked Operations ({displayedItems.length})
        </span>
        <button
          id="btn-copy-bottlenecks-summary"
          data-testid="btn-copy-bottlenecks-summary"
          type="button"
          onClick={handleCopySummary}
          className="flex items-center space-x-1 px-2.5 py-1 rounded-pill text-xs font-mono font-medium text-slate-600 hover:text-ink bg-white border border-hairline hover:bg-soft-stone transition-colors cursor-pointer shadow-2xs"
          title="Copy markdown summary to clipboard"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-emerald-500" />
              <span>Copied</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5 text-muted" />
              <span>Copy Summary</span>
            </>
          )}
        </button>
      </div>

      {/* Empty State */}
      {displayedItems.length === 0 ? (
        <div className="text-center py-12 text-slate-500 text-xs font-mono bg-white rounded-xl border border-hairline p-6">
          {items.length === 0
            ? "No bottlenecks recorded yet."
            : hideMicroCommands &&
              items.every((it) => it.type === "command" && it.durationMs < 100)
            ? "No operations matched filter (all commands executed under 100ms)."
            : "No operations match the selected stage and category filters."}
        </div>
      ) : (
        /* Ranked Bottlenecks List */
        <div className="space-y-2.5">
          {displayedItems.map((item, index) => {
            const rank = index + 1;
            const isExpanded = expandedIds.has(item.id);

            return (
              <BottleneckCard
                key={item.id}
                item={item}
                rank={rank}
                maxDurationMs={maxDurationMs}
                isExpanded={isExpanded}
                onToggleExpand={() => handleToggleExpand(item.id)}
              />
            );
          })}
        </div>
      )}
    </>
  )}
</div>
);
};
