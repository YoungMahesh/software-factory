import React, { useState, useEffect, useMemo, useRef } from "react";
import {
  Monitor,
  Tablet,
  Smartphone,
  RotateCw,
  ExternalLink,
  Globe,
  GitBranch,
  Play,
  Square,
  Loader2,
  Terminal,
  ChevronDown,
  AlertTriangle,
  Check,
  RefreshCw,
  Lock,
  RotateCcw,
} from "lucide-react";
import { ViewportMode, PreviewStatus, PreviewStage } from "../types";
import { PreviewProgressStepper } from "./PreviewProgressStepper";
import { TerminalLogViewer } from "./TerminalLogViewer";

interface LivePreviewProps {
  previewUrl?: string | null;
  status?: PreviewStatus;
  stage?: PreviewStage;
  branch?: string | null;
  branches?: string[];
  availableBranches?: string[];
  onSelectBranch?: (branch: string) => Promise<void> | void;
  onSwitchBranch?: (branch: string) => Promise<void> | void;
  isSwitchingBranch?: boolean;
  isConcurrencyLocked?: boolean;
  isJobActive?: boolean;
  lockTooltip?: string;
  logs?: string[];
  errorMessage?: string | null;
  onLaunchPreview?: () => void;
  onStopPreview?: () => void;
  onRetryPreview?: () => void;
  onReconnectPreview?: () => void;
  onRefresh?: () => void;
  refreshKey?: number;
  isLaunching?: boolean;
  isSyncing?: boolean;
  onSync?: () => void;
  onRollbackLastTurn?: () => void;
  isRollingBack?: boolean;
  isRollbackDisabled?: boolean;
  rollbackDisabledReason?: string;
}

export const LivePreview: React.FC<LivePreviewProps> = ({
  previewUrl,
  status = "IDLE",
  stage = "IDLE",
  branch = null,
  branches = [],
  availableBranches: availableBranchesProp,
  onSelectBranch,
  onSwitchBranch,
  isSwitchingBranch = false,
  isConcurrencyLocked = false,
  isJobActive = false,
  lockTooltip,
  logs = [],
  errorMessage = null,
  onLaunchPreview,
  onStopPreview,
  onRetryPreview,
  onReconnectPreview,
  onRefresh,
  refreshKey,
  isLaunching = false,
  isSyncing = false,
  onSync,
  onRollbackLastTurn,
  isRollingBack = false,
  isRollbackDisabled = false,
  rollbackDisabledReason,
}) => {
  const [viewport, setViewport] = useState<ViewportMode>("desktop");
  const [reloadKey, setReloadKey] = useState<number>(0);
  const [isLogsDrawerOpen, setIsLogsDrawerOpen] = useState<boolean>(false);
  const [isDropdownOpen, setIsDropdownOpen] = useState<boolean>(false);
  const [isLocalSwitching, setIsLocalSwitching] = useState<boolean>(false);
  const [highlightedIndex, setHighlightedIndex] = useState<number>(-1);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const switchBranchFn = onSwitchBranch || onSelectBranch;
  const isLocked = Boolean(isJobActive || isConcurrencyLocked);
  const candidateBranches = availableBranchesProp && availableBranchesProp.length > 0
    ? availableBranchesProp
    : branches;
  const currentBranch = branch || (candidateBranches.length > 0 ? candidateBranches[0] : null);
  const isSwitching = isSwitchingBranch || isLocalSwitching;
  const isInteractive = Boolean(
    switchBranchFn ||
    candidateBranches.length > 0 ||
    isSwitching ||
    isLocked
  );

  // Build sorted branch list: active branch first, then main, then others alphabetically
  const availableBranches = useMemo(() => {
    const list = Array.from(
      new Set(candidateBranches.length > 0 ? candidateBranches : currentBranch ? [currentBranch] : [])
    );
    return list.sort((a, b) => {
      if (a === currentBranch) return -1;
      if (b === currentBranch) return 1;
      if (a === "main") return -1;
      if (b === "main") return 1;
      return a.localeCompare(b);
    });
  }, [candidateBranches, currentBranch]);

  // Click-away listener to close dropdown
  useEffect(() => {
    if (!isDropdownOpen) return;
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isDropdownOpen]);

  const handleBranchSelect = async (targetBranch: string) => {
    setIsDropdownOpen(false);
    setHighlightedIndex(-1);
    if (targetBranch === currentBranch && !isSwitching) return;

    setIsLocalSwitching(true);
    try {
      if (switchBranchFn) {
        await switchBranchFn(targetBranch);
      }
      setReloadKey((prev) => prev + 1);
      if (onRefresh) {
        onRefresh();
      }
    } finally {
      setIsLocalSwitching(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (isConcurrencyLocked || isSwitching) return;

    if (!isDropdownOpen) {
      if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        setIsDropdownOpen(true);
        setHighlightedIndex(0);
      }
      return;
    }

    if (e.key === "Escape") {
      e.preventDefault();
      setIsDropdownOpen(false);
      setHighlightedIndex(-1);
      triggerRef.current?.focus();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightedIndex((prev) => (prev + 1) % availableBranches.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightedIndex((prev) => (prev - 1 + availableBranches.length) % availableBranches.length);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (highlightedIndex >= 0 && highlightedIndex < availableBranches.length) {
        handleBranchSelect(availableBranches[highlightedIndex]);
      }
    }
  };

  // Auto-expand logs drawer on failure
  useEffect(() => {
    if (status === "FAILED") {
      setIsLogsDrawerOpen(true);
    }
  }, [status]);

  // Synchronize external refreshKey signal (e.g. from SSE preview_refresh)
  useEffect(() => {
    if (refreshKey !== undefined && refreshKey > 0) {
      setReloadKey((prev) => prev + 1);
    }
  }, [refreshKey]);

  const handleReload = () => {
    setReloadKey((prev) => prev + 1);
    if (onRefresh) {
      onRefresh();
    }
  };

  const handleRetry = () => {
    if (onRetryPreview) {
      onRetryPreview();
    } else if (onLaunchPreview) {
      onLaunchPreview();
    }
  };

  const getViewportWidth = (): string => {
    switch (viewport) {
      case "mobile":
        return "375px";
      case "tablet":
        return "768px";
      case "desktop":
      default:
        return "100%";
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-950 rounded-xl border border-slate-800 overflow-hidden shadow-xl">
      {/* Top control bar */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-slate-900 border-b border-slate-800 shrink-0">
        {/* Responsive viewport controls */}
        <div className="flex items-center space-x-1 bg-slate-950 p-1 rounded-lg border border-slate-800">
          <button
            data-testid="viewport-desktop"
            id="btn-viewport-desktop"
            type="button"
            onClick={() => setViewport("desktop")}
            className={`p-1.5 rounded-md text-xs transition-colors ${
              viewport === "desktop"
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
            }`}
            title="Desktop view"
          >
            <Monitor className="w-3.5 h-3.5" />
          </button>
          <button
            data-testid="viewport-tablet"
            id="btn-viewport-tablet"
            type="button"
            onClick={() => setViewport("tablet")}
            className={`p-1.5 rounded-md text-xs transition-colors ${
              viewport === "tablet"
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
            }`}
            title="Tablet view (768px)"
          >
            <Tablet className="w-3.5 h-3.5" />
          </button>
          <button
            data-testid="viewport-mobile"
            id="btn-viewport-mobile"
            type="button"
            onClick={() => setViewport("mobile")}
            className={`p-1.5 rounded-md text-xs transition-colors ${
              viewport === "mobile"
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
            }`}
            title="Mobile view (375px)"
          >
            <Smartphone className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Active Branch Badge / Dropdown & Trunk Synchronization Button */}
        <div className="flex items-center space-x-1.5 shrink-0">
          {/* Static Branch Pill (when no switch handler and no candidate branches are provided) */}
          {currentBranch && !isInteractive && (
            <div
              data-testid="preview-branch-badge"
              id="preview-branch-badge"
              className="flex items-center space-x-1.5 px-2.5 py-1 bg-slate-950 rounded-lg border border-slate-800 text-[11px] font-mono text-indigo-300 shrink-0"
            >
              <GitBranch className="w-3 h-3 text-indigo-400 shrink-0" data-testid="preview-branch-icon" />
              <span className="truncate max-w-[140px]">{currentBranch}</span>
            </div>
          )}

          {/* Live Preview Branch Selector Dropdown */}
          {currentBranch && isInteractive && (
            <div className="relative shrink-0" ref={dropdownRef} onKeyDown={handleKeyDown}>
              <button
                ref={triggerRef}
                data-testid="preview-branch-badge"
                id="preview-branch-badge"
                type="button"
                onClick={() => {
                  if (!isLocked && !isSwitching && availableBranches.length > 0) {
                    setIsDropdownOpen((prev) => !prev);
                    setHighlightedIndex(-1);
                  }
                }}
                disabled={isLocked || isSwitching}
                title={
                  isLocked
                    ? (lockTooltip || "Branch switching is disabled while an Assembly Line Pipeline job is active")
                    : isSwitching
                    ? "Switching branch..."
                    : "Switch preview branch"
                }
                aria-haspopup="listbox"
                aria-expanded={isDropdownOpen}
                className={`flex items-center space-x-1.5 px-2.5 py-1 bg-slate-950 rounded-lg border text-[11px] font-mono shrink-0 transition-all ${
                  isLocked
                    ? "border-amber-900/60 text-amber-400 bg-amber-950/20 cursor-not-allowed opacity-80"
                    : isSwitching
                    ? "border-indigo-800 text-indigo-300 bg-indigo-950/30 cursor-wait opacity-80"
                    : "border-slate-800 text-indigo-300 hover:border-indigo-600 hover:text-indigo-200 cursor-pointer focus:outline-none focus:ring-1 focus:ring-indigo-500"
                }`}
              >
                {isSwitching ? (
                  <Loader2 className="w-3 h-3 text-indigo-400 animate-spin shrink-0" data-testid="preview-branch-spinner" />
                ) : (
                  <GitBranch className="w-3 h-3 text-indigo-400 shrink-0" data-testid="preview-branch-icon" />
                )}
                <span className="truncate max-w-[140px]">{currentBranch}</span>
                {isLocked ? (
                  <Lock className="w-3 h-3 text-amber-400 shrink-0" data-testid="preview-branch-lock-icon" />
                ) : isSwitching ? null : (
                  <ChevronDown
                    className={`w-3 h-3 text-slate-400 shrink-0 transition-transform duration-150 ${
                      isDropdownOpen ? "rotate-180 text-indigo-300" : ""
                    }`}
                    data-testid="preview-branch-chevron"
                  />
                )}
              </button>

              {/* Dropdown Menu */}
              {isDropdownOpen && !isLocked && !isSwitching && (
                <div
                  role="listbox"
                  id="preview-branch-menu"
                  data-testid="preview-branch-dropdown"
                  className="absolute left-0 mt-1.5 w-64 bg-slate-900 border border-slate-700/80 rounded-lg shadow-2xl py-1 z-50 overflow-hidden"
                >
                  <div className="px-3 py-1.5 text-[10px] font-semibold tracking-wider text-slate-400 uppercase border-b border-slate-800/80">
                    Switch Branch
                  </div>
                  <div className="max-h-60 overflow-y-auto py-1">
                    {availableBranches.map((candidateBranch, idx) => {
                      const isActive = candidateBranch === currentBranch;
                      return (
                        <button
                          key={candidateBranch}
                          role="option"
                          aria-selected={isActive}
                          data-testid={`preview-branch-option-${candidateBranch}`}
                          onClick={() => handleBranchSelect(candidateBranch)}
                          onMouseEnter={() => setHighlightedIndex(idx)}
                          className={`w-full flex items-center justify-between px-3 py-1.5 text-xs font-mono text-left transition-colors ${
                            highlightedIndex === idx
                              ? "bg-slate-800 text-slate-100"
                              : "text-slate-300 hover:bg-slate-800/60"
                          } ${isActive ? "text-indigo-400 font-semibold" : ""}`}
                        >
                          <div className="flex items-center space-x-2 truncate mr-2">
                            <GitBranch className={`w-3 h-3 shrink-0 ${isActive ? "text-indigo-400" : "text-slate-500"}`} />
                            <span className="truncate">{candidateBranch}</span>
                            {candidateBranch === "main" && (
                              <span className="text-[9px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 font-sans border border-slate-700">
                                default
                              </span>
                            )}
                          </div>
                          {isActive && (
                            <Check className="w-3.5 h-3.5 text-indigo-400 shrink-0" data-testid="preview-branch-check" />
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Trunk Synchronization Action Button */}
          {onSync && (
            <button
              data-testid="sync-preview-btn"
              id="btn-preview-sync"
              type="button"
              onClick={onSync}
              disabled={isSyncing || isLocked || !onSync}
              className={`p-1.5 rounded-lg border text-xs transition-colors flex items-center justify-center shrink-0 ${
                isLocked
                  ? "bg-slate-950/80 border-slate-800/80 text-slate-500 cursor-not-allowed"
                  : isSyncing
                  ? "bg-indigo-950/40 border-indigo-800/60 text-indigo-400 cursor-wait"
                  : "bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-800"
              } disabled:opacity-50`}
              title={
                isLocked
                  ? "Cannot synchronize while an assembly line job is active"
                  : isSyncing
                  ? "Synchronizing with remote..."
                  : "Pull latest from remote"
              }
              aria-label={
                isLocked
                  ? "Cannot synchronize while an assembly line job is active"
                  : isSyncing
                  ? "Synchronizing with remote..."
                  : "Pull latest from remote"
              }
            >
              {isLocked ? (
                <Lock className="w-3 h-3 text-amber-500/80" data-testid="sync-lock-icon" />
              ) : isSyncing ? (
                <Loader2 className="w-3 h-3 animate-spin text-indigo-400" data-testid="sync-loading-spinner" />
              ) : (
                <RefreshCw className="w-3 h-3 text-indigo-400 hover:text-indigo-300" data-testid="sync-icon" />
              )}
            </button>
          )}

          {/* Undo Last Turn Action Button */}
          {onRollbackLastTurn && (
            <button
              data-testid="preview-rollback-btn"
              id="btn-preview-rollback"
              type="button"
              onClick={onRollbackLastTurn}
              disabled={isLocked || isRollingBack || isSyncing || isSwitching || isRollbackDisabled}
              className={`p-1.5 rounded-lg border text-xs transition-colors flex items-center justify-center shrink-0 ${
                isLocked || isSyncing || isSwitching || isRollbackDisabled
                  ? "bg-slate-950/80 border-slate-800/80 text-slate-500 cursor-not-allowed"
                  : isRollingBack
                  ? "bg-indigo-950/40 border-indigo-800/60 text-indigo-400 cursor-wait"
                  : "bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-800"
              } disabled:opacity-50`}
              title={
                isLocked
                  ? "Cannot roll back turn while job is active"
                  : rollbackDisabledReason ||
                    (isRollingBack ? "Rolling back last turn..." : "Roll Back Last Turn")
              }
              aria-label="Roll Back Last Turn"
            >
              {isRollingBack ? (
                <Loader2 className="w-3 h-3 animate-spin text-indigo-400" data-testid="rollback-loading-spinner" />
              ) : isLocked || isRollbackDisabled ? (
                <Lock className="w-3 h-3 text-slate-500" data-testid="rollback-lock-icon" />
              ) : (
                <RotateCcw className="w-3 h-3 text-indigo-400 hover:text-indigo-300" data-testid="rollback-icon" />
              )}
            </button>
          )}
        </div>

        {/* URL Address Bar */}
        <div className="flex-1 max-w-md mx-3">
          <div className="flex items-center px-3 py-1 bg-slate-950 rounded-lg border border-slate-800/80 text-xs font-mono text-slate-300 truncate">
            <Globe className="w-3 h-3 text-slate-500 mr-2 shrink-0" />
            <span id="preview-url-display" className="truncate text-[11px] text-slate-300">
              {previewUrl || (status === "PROVISIONING" ? "Provisioning sandbox tunnel..." : status === "FAILED" ? "Startup failed" : "Waiting for live preview...")}
            </span>
          </div>
        </div>

        {/* Actions: Dev Logs Toggle, Reload, External, Retry & Stop */}
        <div className="flex items-center space-x-1.5">
          {/* Dev Server Logs Drawer Toggle */}
          <button
            data-testid="toggle-dev-logs-btn"
            id="btn-toggle-dev-logs"
            type="button"
            onClick={() => setIsLogsDrawerOpen((prev) => !prev)}
            className={`p-1.5 rounded-md text-xs transition-colors flex items-center space-x-1 ${
              isLogsDrawerOpen
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
            }`}
            title="Toggle Dev Server Logs Drawer"
          >
            <Terminal className="w-3.5 h-3.5" />
            {logs.length > 0 && (
              <span className="text-[10px] font-mono opacity-80">{logs.length}</span>
            )}
          </button>

          <button
            data-testid="reload-preview-btn"
            id="btn-preview-reload"
            type="button"
            onClick={handleReload}
            disabled={!previewUrl}
            className="flex items-center space-x-1 px-2 py-1 rounded-md text-xs text-slate-400 hover:text-slate-200 hover:bg-slate-800 disabled:opacity-40 disabled:pointer-events-none transition-colors"
            title="Refresh preview"
            aria-label="Refresh"
          >
            <RotateCw className="w-3.5 h-3.5" />
            <span data-testid="refresh-preview-btn" className="font-medium">Refresh</span>
          </button>

          {previewUrl && (
            <a
              id="preview-open-link"
              href={previewUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1.5 rounded-md text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
              title="Open in new window"
            >
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          )}

          {onStopPreview && (status === "SERVING" || status === "PROVISIONING") && (
            <button
              data-testid="stop-preview-btn"
              id="btn-preview-stop"
              type="button"
              onClick={onStopPreview}
              className="flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-rose-600/90 hover:bg-rose-600 text-white shadow-sm transition-colors"
              title="Stop preview sandbox"
            >
              <Square className="w-3 h-3 fill-current" />
              <span>Stop</span>
            </button>
          )}
        </div>
      </div>

      {/* Frame Container */}
      <div
        id="preview-frame-wrapper"
        className="flex-1 flex flex-col items-center justify-center bg-slate-950 p-4 overflow-auto min-h-0"
      >
        {previewUrl && status !== "PROVISIONING" && status !== "FAILED" && status !== "STOPPED" ? (
          <div
            className="preview-viewport-wrapper h-full w-full transition-all duration-300 rounded-lg border border-slate-800 shadow-2xl bg-white overflow-hidden flex flex-col mx-auto"
            style={{ width: getViewportWidth() }}
          >
            <iframe
              id="preview-frame"
              key={reloadKey}
              src={previewUrl}
              title="Live Application Preview"
              className="w-full flex-1 border-0"
              sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
            />
          </div>
        ) : status === "PROVISIONING" ? (
          <div className="w-full flex flex-col items-center justify-center p-6 space-y-6">
            <PreviewProgressStepper
              currentStage={stage}
              status={status}
              errorMessage={errorMessage}
            />
            <div className="flex flex-col items-center text-center max-w-sm">
              <div className="w-10 h-10 rounded-full bg-indigo-950/60 border border-indigo-800/80 flex items-center justify-center text-indigo-400 mb-3 shadow-md">
                <Loader2 className="w-5 h-5 animate-spin" />
              </div>
              <h3 className="text-xs font-semibold text-slate-200 mb-1">
                Booting Dedicated Preview Sandbox
              </h3>
              <p className="text-[11px] text-slate-400 leading-relaxed">
                Starting Modal Standard Sandbox on port 3000, installing dependencies, and compiling Vite dev server.
              </p>
            </div>
          </div>
        ) : status === "FAILED" ? (
          <div className="w-full flex flex-col items-center justify-center p-6 space-y-6">
            <PreviewProgressStepper
              currentStage={stage}
              status={status}
              errorMessage={errorMessage}
            />
            <div className="flex flex-col items-center text-center max-w-sm">
              <p className="text-xs text-slate-400 leading-relaxed mb-4">
                Sandbox boot or Vite dev server failed to start. Review the failure diagnostics below or retry.
              </p>
              <button
                data-testid="retry-preview-btn"
                id="btn-retry-center"
                type="button"
                onClick={handleRetry}
                className="flex items-center space-x-1.5 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-lg shadow-indigo-600/20 transition-all hover:scale-[1.02]"
              >
                <RotateCw className="w-3.5 h-3.5" />
                <span>Retry Startup</span>
              </button>
            </div>
          </div>
        ) : status === "STOPPED" ? (
          <div className="flex flex-col items-center justify-center text-center p-8 max-w-sm">
            <div className="w-12 h-12 rounded-full bg-slate-900 border border-slate-800 flex items-center justify-center text-amber-400 mb-4">
              <AlertTriangle className="w-6 h-6" />
            </div>
            <h3 className="text-sm font-semibold text-slate-200 mb-1">
              Sandbox Disconnected
            </h3>
            <p className="text-xs text-slate-400 leading-relaxed mb-4">
              The Unified Studio Sandbox stopped or reached its 30-minute idle timeout.
            </p>
            {(onReconnectPreview || onLaunchPreview) && (
              <button
                data-testid="reconnect-preview-btn"
                id="btn-reconnect-preview"
                type="button"
                onClick={onReconnectPreview || onLaunchPreview}
                className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-lg shadow-indigo-600/20 transition-all hover:scale-[1.02]"
              >
                <RotateCw className="w-3.5 h-3.5" />
                <span>Reconnect Environment</span>
              </button>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center text-center p-8 max-w-sm">
            <div className="w-12 h-12 rounded-full bg-slate-900 border border-slate-800 flex items-center justify-center text-slate-500 mb-4">
              <Globe className="w-6 h-6" />
            </div>
            <h3 className="text-sm font-semibold text-slate-200 mb-1">
              No Application Preview Active
            </h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Launch a Dedicated Preview Sandbox to immediately test and interact with the live application.
            </p>
            {onLaunchPreview && (
              <button
                data-testid="launch-preview-cta-btn"
                id="btn-launch-live-preview"
                type="button"
                onClick={onLaunchPreview}
                disabled={isLaunching}
                className="mt-4 flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-lg shadow-indigo-600/20 transition-all hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50"
              >
                {isLaunching ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Play className="w-4 h-4 fill-current" />
                )}
                <span>Launch Live Preview</span>
              </button>
            )}
          </div>
        )}
      </div>

      {/* Collapsible Dev Server Logs Terminal Drawer */}
      {isLogsDrawerOpen && (
        <div
          data-testid="dev-server-logs-drawer"
          id="dev-server-logs-drawer"
          className="h-64 border-t border-slate-800 bg-slate-950 flex flex-col shrink-0 overflow-hidden"
        >
          {/* Drawer Header */}
          <div className="flex items-center justify-between px-3.5 py-2 bg-slate-900 border-b border-slate-800 text-xs shrink-0">
            <div className="flex items-center space-x-2 text-slate-300">
              <Terminal className="w-3.5 h-3.5 text-indigo-400" />
              <span className="font-semibold text-slate-200 text-xs">Dev Server Logs</span>
              <span id="dev-logs-line-count" className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-400">
                {logs.length} lines
              </span>
            </div>

            <div className="flex items-center space-x-2">
              {status === "FAILED" && (
                <button
                  data-testid="retry-preview-btn"
                  id="btn-retry-in-drawer"
                  type="button"
                  onClick={handleRetry}
                  className="flex items-center space-x-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm transition-colors"
                >
                  <RotateCw className="w-3 h-3" />
                  <span>Retry</span>
                </button>
              )}
              <button
                id="btn-close-logs-drawer"
                type="button"
                onClick={() => setIsLogsDrawerOpen(false)}
                className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
                title="Close terminal drawer"
              >
                <ChevronDown className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Drawer Body */}
          <div className="flex-1 overflow-hidden">
            <TerminalLogViewer logs={logs} />
          </div>
        </div>
      )}
    </div>
  );
};
