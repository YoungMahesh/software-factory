import React from "react";
import { Boxes, Sparkles, Terminal, GitBranch } from "lucide-react";
import { Job } from "../types";

export interface AppNavigationProps {
  activeTab: "studio" | "console";
  onTabChange: (tab: "studio" | "console") => void;
  activeJob: Job | null;
  selectedRepo: string;
}

export const AppNavigation: React.FC<AppNavigationProps> = ({
  activeTab,
  onTabChange,
  activeJob,
  selectedRepo,
}) => {
  return (
    <header className="h-14 border-b border-hairline bg-white px-6 flex items-center justify-between z-30 shrink-0">
      <div className="flex items-center space-x-6">
        {/* Logo & Product Title */}
        <div className="flex items-center space-x-2.5">
          <div className="w-7 h-7 rounded-lg bg-primary flex items-center justify-center text-white shadow-sm">
            <Boxes className="w-4 h-4" />
          </div>
          <div className="flex flex-col">
            <span className="font-display font-semibold text-sm text-ink tracking-tight leading-none">
              Software Factory
            </span>
            <span className="text-[10px] text-muted font-mono">v0.9.0-modal</span>
          </div>
        </div>

        {/* Navigation Switcher Tabs */}
        <nav className="flex items-center space-x-1 bg-soft-stone p-1 rounded-pill border border-hairline">
          <button
            id="nav-tab-studio"
            onClick={() => onTabChange("studio")}
            className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-pill text-xs font-medium transition-all ${
              activeTab === "studio"
                ? "bg-primary text-white shadow-sm"
                : "text-muted hover:text-ink hover:bg-white/60"
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Factory Studio</span>
          </button>
          <button
            id="nav-tab-console"
            onClick={() => onTabChange("console")}
            className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-pill text-xs font-medium transition-all ${
              activeTab === "console"
                ? "bg-primary text-white shadow-sm"
                : "text-muted hover:text-ink hover:bg-white/60"
            }`}
          >
            <Terminal className="w-3.5 h-3.5" />
            <span>Factory Testing Console</span>
          </button>
        </nav>
      </div>

      {/* Header Right Status Indicator */}
      <div className="flex items-center space-x-3 text-xs">
        {activeJob && (
          <div className="flex items-center space-x-2 bg-primary px-3 py-1 rounded-pill border border-hairline/40 text-white shadow-xs">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-white font-mono text-[11px]">{activeJob.stage}</span>
            <span className="text-white/40">•</span>
            <span className="text-slate-300 truncate max-w-[120px]">
              {activeJob.feature || activeJob.repo}
            </span>
          </div>
        )}
        <div className="flex items-center space-x-1.5 text-muted font-mono text-[11px] bg-soft-stone px-2.5 py-1 rounded-pill border border-hairline">
          <GitBranch className="w-3 h-3 text-slate-500" />
          <span className="text-ink">{selectedRepo || "no-repo"}</span>
        </div>
      </div>
    </header>
  );
};
