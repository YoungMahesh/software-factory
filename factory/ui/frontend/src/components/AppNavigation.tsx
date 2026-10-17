import React from "react";
import { Boxes, GitBranch, Activity } from "lucide-react";
import { Job } from "../types";
import { StudioContext } from "../context/StudioContext";

export interface AppNavigationProps {
  activeJob: Job | null;
  selectedRepo: string;
  onOpenDrawer?: (
    targetToolCallId?: string,
    tab?: "timeline" | "logs" | "history" | "failed-commands" | "failed_commands"
  ) => void;
  failedCommandCount?: number;
}

export const AppNavigation: React.FC<AppNavigationProps> = ({
  activeJob,
  selectedRepo,
  onOpenDrawer: propsOnOpenDrawer,
  failedCommandCount: propsFailedCount,
}) => {
  const studioContext = React.useContext(StudioContext);
  const onOpenDrawer = propsOnOpenDrawer || studioContext?.onOpenDrawer;
  const rawCount = propsFailedCount !== undefined ? propsFailedCount : (studioContext?.failedCommandCount || 0);
  const failedCommandCount = Math.max(0, rawCount);
  const hasFailedCommands = Boolean(activeJob && failedCommandCount > 0);

  const handleOpenActivity = () => {
    if (onOpenDrawer) {
      onOpenDrawer(undefined, hasFailedCommands ? "failed-commands" : "timeline");
    }
  };

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
      </div>

      {/* Header Right Status Indicator */}
      <div className="flex items-center space-x-3 text-xs">
        {onOpenDrawer && (
          <button
            id="btn-nav-activity"
            data-testid="nav-activity-drawer-btn"
            type="button"
            onClick={handleOpenActivity}
            className="flex items-center space-x-1.5 px-3 py-1 rounded-pill border border-hairline bg-soft-stone hover:bg-hairline/50 text-ink transition-colors cursor-pointer text-xs font-medium focus:outline-none"
            title={hasFailedCommands ? `Open Activity Drawer (${failedCommandCount} failed commands)` : "Open Activity Drawer"}
          >
            <Activity className="w-3.5 h-3.5 text-muted" />
            <span>Activity</span>
            {hasFailedCommands && (
              <span
                id="nav-failed-commands-badge"
                data-testid="nav-failed-commands-badge"
                onClick={(e) => {
                  e.stopPropagation();
                  onOpenDrawer(undefined, "failed-commands");
                }}
                className="ml-1 px-1.5 py-0.2 rounded-full text-[10px] font-mono font-bold bg-coral text-white"
              >
                {failedCommandCount}
              </span>
            )}
          </button>
        )}
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

