import React, { useState, useEffect, useRef } from "react";
import { GitBranch, Loader2, Lock, ChevronDown, Check } from "lucide-react";

export interface LivePreviewBranchSelectorProps {
  currentBranch: string | null;
  availableBranches: string[];
  isInteractive: boolean;
  isLocked: boolean;
  isSwitching: boolean;
  lockTooltip?: string;
  onSelectBranch: (branch: string) => Promise<void> | void;
}

export const LivePreviewBranchSelector: React.FC<LivePreviewBranchSelectorProps> = ({
  currentBranch,
  availableBranches,
  isInteractive,
  isLocked,
  isSwitching,
  lockTooltip,
  onSelectBranch,
}) => {
  const [isDropdownOpen, setIsDropdownOpen] = useState<boolean>(false);
  const [highlightedIndex, setHighlightedIndex] = useState<number>(-1);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

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
    await onSelectBranch(targetBranch);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (isLocked || isSwitching) return;

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

  if (!currentBranch) return null;

  if (!isInteractive) {
    return (
      <div
        data-testid="preview-branch-badge"
        id="preview-branch-badge"
        className="flex items-center space-x-1.5 px-3 py-1 bg-transparent rounded-pill border border-white/20 text-[11px] font-mono text-white shrink-0"
      >
        <GitBranch className="w-3 h-3 text-white/70 shrink-0" data-testid="preview-branch-icon" />
        <span className="truncate max-w-[140px]">{currentBranch}</span>
      </div>
    );
  }

  return (
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
            ? lockTooltip || "Branch switching is disabled while an Assembly Line Pipeline job is active"
            : isSwitching
            ? "Switching branch..."
            : "Switch preview branch"
        }
        aria-haspopup="listbox"
        aria-expanded={isDropdownOpen}
        className={`flex items-center space-x-1.5 px-3 py-1 bg-transparent rounded-pill border text-[11px] font-mono shrink-0 transition-all ${
          isLocked
            ? "border-amber-700/60 text-amber-400 bg-amber-950/20 cursor-not-allowed opacity-80"
            : isSwitching
            ? "border-white/30 text-white bg-white/10 cursor-wait opacity-80"
            : "border-white/20 text-white hover:border-white/40 hover:bg-white/10 cursor-pointer focus:outline-none focus:ring-1 focus:ring-white/40"
        }`}
      >
        {isSwitching ? (
          <Loader2 className="w-3 h-3 text-white animate-spin shrink-0" data-testid="preview-branch-spinner" />
        ) : (
          <GitBranch className="w-3 h-3 text-white/80 shrink-0" data-testid="preview-branch-icon" />
        )}
        <span className="truncate max-w-[140px]">{currentBranch}</span>
        {isLocked ? (
          <Lock className="w-3 h-3 text-amber-400 shrink-0" data-testid="preview-branch-lock-icon" />
        ) : isSwitching ? null : (
          <ChevronDown
            className={`w-3 h-3 text-white/60 shrink-0 transition-transform duration-150 ${
              isDropdownOpen ? "rotate-180 text-white" : ""
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
          className="absolute left-0 mt-1.5 w-64 bg-primary border border-white/20 rounded-xl shadow-2xl py-1 z-50 overflow-hidden text-white"
        >
          <div className="px-3 py-1.5 text-[10px] font-semibold tracking-wider text-muted uppercase border-b border-white/10">
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
                  className={`w-full flex items-center justify-between px-3 py-1.5 text-xs font-mono text-left transition-colors cursor-pointer ${
                    highlightedIndex === idx
                      ? "bg-white/15 text-white"
                      : "text-slate-300 hover:bg-white/10"
                  } ${isActive ? "text-white font-semibold" : ""}`}
                >
                  <div className="flex items-center space-x-2 truncate mr-2">
                    <GitBranch className={`w-3 h-3 shrink-0 ${isActive ? "text-white" : "text-muted"}`} />
                    <span className="truncate">{candidateBranch}</span>
                    {candidateBranch === "main" && (
                      <span className="text-[9px] px-1.5 py-0.2 rounded-pill bg-white/10 text-slate-300 font-sans border border-white/10">
                        default
                      </span>
                    )}
                  </div>
                  {isActive && (
                    <Check className="w-3.5 h-3.5 text-white shrink-0" data-testid="preview-branch-check" />
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
