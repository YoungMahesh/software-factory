import React, { useEffect, useRef, useState, useCallback } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { AlertTriangle, Trash2, RefreshCw, Terminal as TerminalIcon } from "lucide-react";

export interface InteractiveTerminalTabProps {
  repo?: string;
  isPipelineRunning?: boolean;
}

export const InteractiveTerminalTab: React.FC<InteractiveTerminalTabProps> = ({
  repo = "default",
  isPipelineRunning = false,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const [connectionStatus, setConnectionStatus] = useState<"connecting" | "connected" | "disconnected">("connecting");
  const [connectAttempts, setConnectAttempts] = useState<number>(0);

  const cleanRepo = repo ? repo.replace(/^software-factory-09-test\//, "") : "default";
  const bareRepo = cleanRepo.split("/").pop() || cleanRepo;

  const handleClear = useCallback(() => {
    if (termRef.current) {
      termRef.current.clear();
    }
  }, []);

  const handleReconnect = useCallback(() => {
    setConnectAttempts((prev) => prev + 1);
  }, []);

  useEffect(() => {
    if (!containerRef.current) return;

    // Initialize xterm instance
    const term = new Terminal({
      cursorBlink: true,
      cursorStyle: "bar",
      fontSize: 13,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace',
      theme: {
        background: "#0c0d0e",
        foreground: "#d1d5db",
        cursor: "#ef4444",
        selectionBackground: "#374151",
        black: "#1e1e1e",
        red: "#f87171",
        green: "#4ade80",
        yellow: "#fbbf24",
        blue: "#60a5fa",
        magenta: "#c084fc",
        cyan: "#38bdf8",
        white: "#f9fafb",
      },
      convertEol: true,
      scrollback: 5000,
    });
    termRef.current = term;

    const fitAddon = new FitAddon();
    fitAddonRef.current = fitAddon;
    term.loadAddon(fitAddon);

    term.open(containerRef.current);

    const safeFit = () => {
      try {
        fitAddon.fit();
        const dims = fitAddon.proposeDimensions();
        if (dims && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: "resize", cols: dims.cols, rows: dims.rows }));
        }
      } catch {
        // Safe fallback in test or headless environments
      }
    };

    safeFit();

    // Resize observer to dynamically adapt to drawer dimensions
    const ObserverClass = typeof ResizeObserver !== "undefined" ? ResizeObserver : null;
    let observer: ResizeObserver | null = null;
    if (ObserverClass && containerRef.current) {
      observer = new ObserverClass(() => {
        safeFit();
      });
      observer.observe(containerRef.current);
    }

    // Build WebSocket URL
    const protocol = typeof window !== "undefined" && window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = typeof window !== "undefined" ? window.location.host || "localhost:8000" : "localhost:8000";
    const encodedRepo = encodeURIComponent(cleanRepo);
    const wsUrl = `${protocol}//${host}/api/repos/${encodedRepo}/terminal/ws`;

    setConnectionStatus("connecting");
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnectionStatus("connected");
      safeFit();
    };

    ws.onmessage = (event) => {
      term.write(event.data);
    };

    ws.onerror = () => {
      setConnectionStatus("disconnected");
    };

    ws.onclose = () => {
      setConnectionStatus("disconnected");
    };

    // Forward terminal input directly to WebSocket stdin
    const onDataDisposable = term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(data);
      }
    });

    return () => {
      onDataDisposable.dispose();
      if (observer) {
        observer.disconnect();
      }
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
      term.dispose();
      termRef.current = null;
      fitAddonRef.current = null;
      wsRef.current = null;
    };
  }, [cleanRepo, connectAttempts]);

  return (
    <div className="flex flex-col h-full bg-[#0c0d0e] text-slate-200">
      {/* Terminal Top Bar */}
      <div className="flex flex-col border-b border-white/10 bg-[#161719] px-4 py-2.5 space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <TerminalIcon className="w-4 h-4 text-slate-400" />
            <span className="text-xs font-semibold text-white tracking-wide">Interactive Terminal</span>
            <span
              data-testid="terminal-repo-badge"
              className="px-2 py-0.5 rounded text-[11px] font-mono bg-white/5 border border-white/10 text-slate-300"
            >
              /root/{bareRepo}
            </span>
          </div>

          <div className="flex items-center space-x-2">
            {/* Connection Status Indicator */}
            <div className="flex items-center space-x-1.5 px-2 py-0.5 rounded text-[10px] font-mono bg-white/5">
              <span
                data-testid="terminal-connection-dot"
                className={`w-2 h-2 rounded-full ${
                  connectionStatus === "connected"
                    ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]"
                    : connectionStatus === "connecting"
                    ? "bg-amber-400 animate-pulse"
                    : "bg-coral"
                }`}
              />
              <span className="text-slate-400 capitalize">{connectionStatus}</span>
            </div>

            {/* Clear Output Button */}
            <button
              type="button"
              data-testid="btn-terminal-clear"
              onClick={handleClear}
              title="Clear terminal canvas"
              className="p-1 rounded text-slate-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>

            {/* Reconnect Button */}
            <button
              type="button"
              data-testid="btn-terminal-reconnect"
              onClick={handleReconnect}
              title="Reconnect terminal session"
              className="p-1 rounded text-slate-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Warning badge when autonomous Assembly Line Pipeline job is actively running */}
        {isPipelineRunning && (
          <div
            data-testid="terminal-pipeline-warning-badge"
            className="flex items-center space-x-2 px-3 py-1.5 rounded bg-amber-500/10 border border-amber-500/30 text-amber-400 text-xs font-sans animate-in fade-in duration-200"
          >
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
            <span>
              <strong>Pipeline job running:</strong> An autonomous pipeline job is actively executing in this container. Concurrent filesystem modifications may conflict with pipeline tasks.
            </span>
          </div>
        )}
      </div>

      {/* Terminal Canvas Container */}
      <div
        data-testid="interactive-terminal-container"
        ref={containerRef}
        className="flex-1 w-full h-full p-2.5 overflow-hidden font-mono"
      />
    </div>
  );
};
