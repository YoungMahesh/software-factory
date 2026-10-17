import React, { useState, useMemo } from "react";
import { Loader2, Terminal, BrainCircuit, ShieldAlert, CheckCircle2 } from "lucide-react";
import { AgentEvent } from "../types";

export interface BottlenecksViewerProps {
  events?: AgentEvent[];
}

export interface BottleneckItem {
  id: string;
  type: "command" | "thinking";
  title: string;
  durationMs: number;
  stage?: string;
  exitCode?: number;
  isError?: boolean;
  output?: string;
  cwd?: string;
}

export const BottlenecksViewer: React.FC<BottlenecksViewerProps> = ({ events = [] }) => {
  const [hideMicroCommands, setHideMicroCommands] = useState<boolean>(false);

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
    const toolStartMap = new Map<string, AgentEvent>();
    events.forEach((evt) => {
      if (evt.type === "tool_start" && evt.data?.toolCallId) {
        toolStartMap.set(evt.data.toolCallId, evt);
      }
    });

    // 1. Fold thinking events by stage until marked done
    const thinkingBlocks: { stage?: string; text: string; durationMs?: number; done?: boolean }[] =
      [];
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
            cwd:
              evt.data?.cwd ||
              evt.data?.args?.cwd ||
              startEvt?.data?.cwd ||
              startEvt?.data?.args?.cwd,
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

  const displayedItems = useMemo(() => {
    if (!hideMicroCommands) return items;
    return items.filter((item) => item.type !== "command" || item.durationMs >= 100);
  }, [items, hideMicroCommands]);

  const formatDurationDisplay = (ms: number): string => {
    return `${(ms / 1000).toFixed(2)}s (${ms}ms)`;
  };

  return (
    <div id="bottlenecks-viewer" className="space-y-4">
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

      {/* Controls & Filter Bar */}
      <div className="flex items-center justify-between px-1 text-xs">
        <span className="font-sans font-semibold text-ink">
          Ranked Operations ({displayedItems.length})
        </span>
        <label
          htmlFor="toggle-hide-micro-commands"
          className="flex items-center space-x-2 text-muted hover:text-ink cursor-pointer select-none text-[11px] font-mono"
        >
          <input
            id="toggle-hide-micro-commands"
            type="checkbox"
            checked={hideMicroCommands}
            onChange={(e) => setHideMicroCommands(e.target.checked)}
            className="rounded border-hairline text-primary focus:ring-primary h-3.5 w-3.5 cursor-pointer"
          />
          <span>Hide micro-commands (&lt;100ms)</span>
        </label>
      </div>

      {/* Empty State */}
      {displayedItems.length === 0 ? (
        <div className="text-center py-12 text-slate-500 text-xs font-mono bg-white rounded-xl border border-hairline p-6">
          {items.length === 0
            ? "No bottlenecks recorded yet."
            : "No operations matched filter (all commands executed under 100ms)."}
        </div>
      ) : (
        /* Ranked Bottlenecks List */
        <div className="space-y-2.5">
          {displayedItems.map((item, index) => {
            const rank = index + 1;
            const percentage = Math.max(
              2,
              Math.min(100, Math.round((item.durationMs / maxDurationMs) * 100))
            );
            const isFailure =
              item.isError || (item.exitCode !== undefined && item.exitCode !== 0);

            return (
              <div
                key={item.id}
                data-testid="bottleneck-row"
                className="bg-white border border-hairline rounded-xl p-3 shadow-2xs hover:border-slate-300 transition-colors space-y-2"
              >
                {/* Header: Rank, Title, Stage, Duration */}
                <div className="flex items-center justify-between text-xs">
                  <div className="flex items-center space-x-2 truncate">
                    <span
                      data-testid="bottleneck-rank"
                      className="font-mono font-bold text-muted text-[11px] shrink-0"
                    >
                      #{rank}
                    </span>
                    {item.type === "thinking" ? (
                      <BrainCircuit className="w-3.5 h-3.5 text-purple-500 shrink-0" />
                    ) : (
                      <Terminal className="w-3.5 h-3.5 text-muted shrink-0" />
                    )}
                    <span
                      data-testid="bottleneck-title"
                      className="font-mono font-semibold text-ink truncate text-xs"
                      title={item.title}
                    >
                      {item.title}
                    </span>
                    {item.stage && (
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-soft-stone text-muted shrink-0">
                        {item.stage}
                      </span>
                    )}
                  </div>

                  <div className="flex items-center space-x-2 shrink-0">
                    {item.exitCode !== undefined && (
                      <span
                        className={`inline-flex items-center space-x-1 px-1.5 py-0.5 rounded text-[10px] font-mono ${
                          isFailure
                            ? "bg-coral/10 text-coral border border-coral/30"
                            : "bg-pale-green text-deep-green border border-deep-green/30"
                        }`}
                      >
                        {isFailure ? (
                          <ShieldAlert className="w-2.5 h-2.5 text-coral" />
                        ) : (
                          <CheckCircle2 className="w-2.5 h-2.5 text-deep-green" />
                        )}
                        <span>exit {item.exitCode}</span>
                      </span>
                    )}
                    <span
                      data-testid="bottleneck-duration"
                      className="font-mono text-xs font-semibold text-primary"
                    >
                      {formatDurationDisplay(item.durationMs)}
                    </span>
                  </div>
                </div>

                {/* Relative Duration Bar */}
                <div className="w-full bg-soft-stone/70 h-2 rounded-full overflow-hidden border border-hairline/60">
                  <div
                    data-testid="bottleneck-duration-bar"
                    className={`h-full rounded-full transition-all duration-300 ${
                      item.type === "thinking"
                        ? "bg-purple-500"
                        : isFailure
                        ? "bg-coral"
                        : "bg-primary"
                    }`}
                    style={{ width: `${percentage}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
