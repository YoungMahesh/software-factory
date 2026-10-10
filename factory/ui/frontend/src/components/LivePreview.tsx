import React, { useState } from "react";
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
} from "lucide-react";
import { ViewportMode, PreviewStatus } from "../types";

interface LivePreviewProps {
  previewUrl?: string | null;
  status?: PreviewStatus;
  branch?: string | null;
  onLaunchPreview?: () => void;
  onStopPreview?: () => void;
  isLaunching?: boolean;
}

export const LivePreview: React.FC<LivePreviewProps> = ({
  previewUrl,
  status = "IDLE",
  branch = null,
  onLaunchPreview,
  onStopPreview,
  isLaunching = false,
}) => {
  const [viewport, setViewport] = useState<ViewportMode>("desktop");
  const [reloadKey, setReloadKey] = useState<number>(0);

  const handleReload = () => {
    setReloadKey((prev) => prev + 1);
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
      <div className="flex items-center justify-between px-4 py-2.5 bg-slate-900 border-b border-slate-800">
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

        {/* Active Branch Badge */}
        {branch && (
          <div
            data-testid="preview-branch-badge"
            id="preview-branch-badge"
            className="flex items-center space-x-1.5 px-2.5 py-1 bg-slate-950 rounded-lg border border-slate-800 text-[11px] font-mono text-indigo-300 shrink-0"
          >
            <GitBranch className="w-3 h-3 text-indigo-400 shrink-0" />
            <span className="truncate max-w-[140px]">{branch}</span>
          </div>
        )}

        {/* URL Address Bar */}
        <div className="flex-1 max-w-md mx-3">
          <div className="flex items-center px-3 py-1 bg-slate-950 rounded-lg border border-slate-800/80 text-xs font-mono text-slate-300 truncate">
            <Globe className="w-3 h-3 text-slate-500 mr-2 shrink-0" />
            <span id="preview-url-display" className="truncate text-[11px] text-slate-300">
              {previewUrl || (status === "PROVISIONING" ? "Provisioning sandbox tunnel..." : "Waiting for live preview...")}
            </span>
          </div>
        </div>

        {/* Actions: Reload, External & Stop */}
        <div className="flex items-center space-x-1.5">
          <button
            data-testid="reload-preview-btn"
            id="btn-preview-reload"
            type="button"
            onClick={handleReload}
            disabled={!previewUrl}
            className="p-1.5 rounded-md text-slate-400 hover:text-slate-200 hover:bg-slate-800 disabled:opacity-40 disabled:pointer-events-none transition-colors"
            title="Reload preview"
          >
            <RotateCw className="w-3.5 h-3.5" />
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

          {onStopPreview && (status === "SERVING" || status === "PROVISIONING" || previewUrl) && (
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
        className="flex-1 flex items-center justify-center bg-slate-950 p-2 overflow-auto"
      >
        {previewUrl ? (
          <div
            className="preview-viewport-wrapper h-full transition-all duration-300 rounded-lg border border-slate-800 shadow-2xl bg-white overflow-hidden flex flex-col"
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
          <div className="flex flex-col items-center justify-center text-center p-8 max-w-sm">
            <div className="w-12 h-12 rounded-full bg-indigo-950/50 border border-indigo-800 flex items-center justify-center text-indigo-400 mb-4">
              <Loader2 className="w-6 h-6 animate-spin" />
            </div>
            <h3 className="text-sm font-semibold text-slate-200 mb-1">
              Provisioning Preview Sandbox...
            </h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Launching Modal Standard Sandbox with encrypted tunnel on port 3000.
            </p>
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
    </div>
  );
};
