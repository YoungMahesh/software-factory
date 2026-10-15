import React, { useState, useEffect, useMemo, useRef } from "react";
import {
  Monitor,
  Tablet,
  Smartphone,
  RotateCw,
  ExternalLink,
  Globe,
  GitBranch,
  Square,
  Loader2,
  Terminal,
  ChevronDown,
  Check,
  RefreshCw,
  Lock,
  RotateCcw,
} from "lucide-react";
import { ViewportMode, PreviewStatus } from "../../types";

export interface LivePreviewToolbarProps {
  viewport: ViewportMode;
  onViewportChange: (viewport: ViewportMode) => void;
  previewUrl?: string | null;
  status?: PreviewStatus;
  branch?: string | null;
  branches?: string[];
  availableBranchesProp?: string[];
  onSelectBranch?: (branch: string) => Promise<void> | void;
  onSwitchBranch?: (branch: string) => Promise<void> | void;
  isSwitchingBranch?: boolean;
  isConcurrencyLocked?: boolean;
  isJobActive?: boolean;
  lockTooltip?: string;
  onReload: () => void;
  onRefresh?: () => void;
  isSyncing?: boolean;
  onSync?: () => void;
  onRollbackLastTurn?: () => void;
  isRollingBack?: boolean;
  isRollbackDisabled?: boolean;
  rollbackDisabledReason?: string;
  isLogsDrawerOpen: boolean;
  onToggleLogsDrawer: () => void;
  logsCount: number;
  onStopPreview?: () => void;
}

export const LivePreviewToolbar: React.FC<LivePreviewToolbarProps> = ({
  viewport,
  onViewportChange,
  previewUrl,
  status = "IDLE",
  branch = null,
  branches = [],
  availableBranchesProp,
  onSelectBranch,
  onSwitchBranch,
  isSwitchingBranch = false,
  isConcurrencyLocked = false,
  isJobActive = false,
  lockTooltip,
  onReload,
  isSyncing = false,
  onSync,
  onRollbackLastTurn,
  isRollingBack = false,
  isRollbackDisabled = false,
  rollbackDisabledReason,
  isLogsDrawerOpen,
  onToggleLogsDrawer,
  logsCount,
  onStopPreview,
}) => {
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
      onReload();
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

  return (
    <div className="flex items-center justify-between px-4 py-2.5 bg-slate-900 border-b border-slate-800 shrink-0">
      {/* Responsive viewport controls */}
      <div className="flex items-center space-x-1 bg-slate-950 p-1 rounded-lg border border-slate-800">
        <button
          data-testid="viewport-desktop"
          id="btn-viewport-desktop"
          type="button"
          onClick={() => onViewportChange("desktop")}
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
          onClick={() => onViewportChange("tablet")}
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
          onClick={() => onViewportChange("mobile")}
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
          onClick={onToggleLogsDrawer}
          className={`p-1.5 rounded-md text-xs transition-colors flex items-center space-x-1 ${
            isLogsDrawerOpen
              ? "bg-indigo-600 text-white shadow-sm"
              : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
          }`}
          title="Toggle Dev Server Logs Drawer"
        >
          <Terminal className="w-3.5 h-3.5" />
          {logsCount > 0 && (
            <span className="text-[10px] font-mono opacity-80">{logsCount}</span>
          )}
        </button>

        <button
          data-testid="reload-preview-btn"
          id="btn-preview-reload"
          type="button"
          onClick={onReload}
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
  );
};
