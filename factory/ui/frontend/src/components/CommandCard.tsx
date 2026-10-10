import React, { useState } from "react";
import { Terminal, Loader2, CheckCircle2, AlertCircle } from "lucide-react";

interface CommandCardProps {
  id?: string;
  command: string;
  cwd?: string;
  stage?: string;
  exitCode?: number | null;
  isError?: boolean;
  running?: boolean;
  durationMs?: number;
  output?: string;
  stderr?: string;
}

export const CommandCard: React.FC<CommandCardProps> = ({
  id,
  command,
  cwd,
  stage,
  exitCode,
  isError = false,
  running = false,
  durationMs,
  output = "",
  stderr,
}) => {
  const code = exitCode !== undefined && exitCode !== null ? exitCode : isError ? 1 : 0;
  const isFailure = !running && (code !== 0 || isError);

  const [showFullOutput, setShowFullOutput] = useState<boolean>(false);

  // Split lines
  const lines = output ? output.split(/\r?\n/) : [];
  if (lines.length > 0 && lines[lines.length - 1] === "") {
    lines.pop();
  }

  const totalLines = lines.length;
  const displayLines = totalLines > 100 && !showFullOutput ? lines.slice(-100) : lines;

  // Stderr detector
  const stderrSet = stderr
    ? new Set(
        stderr
          .split(/\r?\n/)
          .map((l) => l.trim())
          .filter(Boolean)
      )
    : null;

  const isStderrLine = (line: string): boolean => {
    if (!line.trim()) return false;
    const trimmed = line.trim();
    if (stderrSet && stderrSet.has(trimmed)) return true;
    return /^(FAIL|FAILED|Error:|Exception:|AssertionError|Traceback|STDERR:)/i.test(trimmed);
  };

  const formattedDuration = durationMs ? `${(durationMs / 1000).toFixed(2)}s` : null;

  return (
    <div
      id={id}
      className={`command-card my-2 rounded-lg border text-xs overflow-hidden transition-all duration-200 ${
        isFailure
          ? "border-red-800/60 bg-red-950/20"
          : running
          ? "border-amber-700/60 bg-amber-950/10"
          : "border-slate-800 bg-slate-900/40"
      }`}
    >
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-800/60 bg-slate-900/60">
        <div className="flex items-center space-x-2 truncate">
          <Terminal className="w-3.5 h-3.5 text-slate-400 shrink-0" />
          <span className="font-mono font-semibold text-slate-200 truncate">
            {command}
          </span>
          {cwd && (
            <span className="text-[10px] text-slate-400 font-mono hidden sm:inline">
              {cwd}
            </span>
          )}
          {stage && (
            <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300 font-mono">
              {stage}
            </span>
          )}
        </div>

        <div className="flex items-center space-x-2 shrink-0">
          {running && (
            <div className="flex items-center space-x-1.5 text-amber-400">
              <Loader2
                data-testid="running-spinner"
                className="w-3.5 h-3.5 animate-spin"
              />
              <span className="text-[11px] font-mono">Running...</span>
            </div>
          )}

          {!running && (
            <>
              {formattedDuration && (
                <span className="text-[11px] text-slate-400 font-mono">
                  {formattedDuration}
                </span>
              )}
              {code === 0 ? (
                <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-medium bg-emerald-950/60 border border-emerald-500/40 text-emerald-300">
                  <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                  <span>Exit code 0</span>
                </span>
              ) : (
                <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-medium bg-red-950/60 border border-red-500/40 text-red-300">
                  <AlertCircle className="w-3 h-3 text-red-400" />
                  <span>Exit code {code}</span>
                </span>
              )}
            </>
          )}
        </div>
      </div>

      {totalLines > 100 && (
        <div className="flex items-center justify-between px-3 py-1 bg-slate-900/90 border-b border-slate-800 text-[10px] text-slate-400">
          <span>
            Showing last 100 of {totalLines} lines
          </span>
          <button
            type="button"
            onClick={() => setShowFullOutput(!showFullOutput)}
            className="text-indigo-400 hover:text-indigo-300 hover:underline font-mono"
          >
            {showFullOutput ? "[Show last 100 lines]" : "[View full output]"}
          </button>
        </div>
      )}

      {totalLines > 0 && (
        <div className="p-3 font-mono text-[11px] leading-relaxed max-h-80 overflow-y-auto bg-slate-950/90 text-slate-300">
          {displayLines.map((line, idx) => {
            const isStderr = isStderrLine(line);
            return (
              <div
                key={idx}
                className={
                  isStderr
                    ? "stderr-line text-red-400 font-semibold bg-red-950/30 px-1 rounded my-0.5"
                    : "text-slate-300"
                }
              >
                {line || "\u00A0"}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
