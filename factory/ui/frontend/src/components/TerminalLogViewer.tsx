import React, { useState, useEffect, useRef } from "react";
import { Terminal, Copy, Check, Trash2, ArrowDownToLine } from "lucide-react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { copyToClipboard } from "../utils";

interface TerminalLogViewerProps {
  logs: string[];
  onClear?: () => void;
  maxLines?: number;
}

export const TerminalLogViewer: React.FC<TerminalLogViewerProps> = ({
  logs = [],
  onClear,
}) => {
  const [autoscroll, setAutoscroll] = useState<boolean>(true);
  const [copied, setCopied] = useState<boolean>(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Flatten and normalize lines
  const lines: string[] = [];
  logs.forEach((chunk) => {
    const split = chunk.split(/\r?\n/);
    split.forEach((l, idx) => {
      if (idx === split.length - 1 && l === "") return;
      lines.push(l);
    });
  });

  const rowVirtualizer = useVirtualizer({
    count: lines.length,
    getScrollElement: () => containerRef.current,
    estimateSize: () => 20,
    overscan: 25,
    initialRect: { width: 800, height: 600 },
  });

  useEffect(() => {
    if (autoscroll && lines.length > 0) {
      rowVirtualizer.scrollToIndex(lines.length - 1);
    }
  }, [lines.length, autoscroll, rowVirtualizer]);

  const handleCopy = async () => {
    const ok = await copyToClipboard(lines.join("\n"));
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const virtualItems = rowVirtualizer.getVirtualItems();

  return (
    <div className="flex flex-col h-full bg-slate-950 rounded-xl border border-slate-800 overflow-hidden shadow-lg">
      {/* Header Toolbar */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-slate-900 border-b border-slate-800">
        <div className="flex items-center space-x-2">
          <Terminal className="w-4 h-4 text-slate-400" />
          <span className="text-xs font-semibold text-slate-200">Execution Output</span>
          <span id="log-line-count" className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-400">
            {lines.length} lines
          </span>
        </div>

        <div className="flex items-center space-x-2">
          {/* Autoscroll checkbox */}
          <label className="flex items-center space-x-1.5 text-xs text-slate-400 cursor-pointer hover:text-slate-200">
            <input
              id="check-autoscroll"
              type="checkbox"
              checked={autoscroll}
              onChange={(e) => setAutoscroll(e.target.checked)}
              className="w-3.5 h-3.5 rounded bg-slate-800 border-slate-700 text-indigo-600 focus:ring-0 focus:ring-offset-0"
            />
            <span className="flex items-center space-x-1">
              <ArrowDownToLine className="w-3 h-3" />
              <span>Autoscroll</span>
            </span>
          </label>

          {/* Copy Button */}
          <button
            id="btn-copy-log"
            type="button"
            onClick={handleCopy}
            className="flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs text-slate-300 bg-slate-800 hover:bg-slate-700 transition-colors"
          >
            {copied ? (
              <>
                <Check className="w-3 h-3 text-emerald-400" />
                <span>Copied</span>
              </>
            ) : (
              <>
                <Copy className="w-3 h-3" />
                <span>Copy</span>
              </>
            )}
          </button>

          {/* Clear Button */}
          {onClear && (
            <button
              id="btn-clear-log"
              type="button"
              onClick={onClear}
              className="flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs text-slate-400 hover:text-rose-300 hover:bg-slate-800 transition-colors"
              title="Clear terminal log"
            >
              <Trash2 className="w-3 h-3" />
              <span>Clear</span>
            </button>
          )}
        </div>
      </div>

      {/* Virtualized Terminal Body */}
      <div
        id="terminal-body"
        ref={containerRef}
        className="flex-1 p-4 font-mono text-[11px] leading-relaxed text-slate-300 overflow-y-auto bg-slate-950/90 whitespace-pre-wrap select-text"
      >
        {lines.length === 0 ? (
          <div className="text-slate-600 italic select-none">
            Awaiting sandbox logs...
          </div>
        ) : (
          <div
            style={{
              height: `${rowVirtualizer.getTotalSize()}px`,
              width: "100%",
              position: "relative",
            }}
          >
            {virtualItems.length > 0
              ? virtualItems.map((virtualRow) => (
                  <div
                    key={virtualRow.index}
                    style={{
                      position: "absolute",
                      top: 0,
                      left: 0,
                      width: "100%",
                      transform: `translateY(${virtualRow.start}px)`,
                    }}
                    className="hover:bg-slate-900/40 px-1 rounded -mx-1"
                  >
                    {lines[virtualRow.index] || "\u00A0"}
                  </div>
                ))
              : lines.map((line, idx) => (
                  <div key={idx} className="hover:bg-slate-900/40 px-1 rounded -mx-1">
                    {line || "\u00A0"}
                  </div>
                ))}
          </div>
        )}
      </div>
    </div>
  );
};
