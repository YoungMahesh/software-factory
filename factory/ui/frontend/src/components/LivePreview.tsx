import React, { useState } from "react";
import { Monitor, Tablet, Smartphone, RotateCw, ExternalLink, Globe } from "lucide-react";
import { ViewportMode } from "../types";

interface LivePreviewProps {
  previewUrl?: string | null;
}

export const LivePreview: React.FC<LivePreviewProps> = ({
  previewUrl,
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

        {/* URL Address Bar */}
        <div className="flex-1 max-w-md mx-3">
          <div className="flex items-center px-3 py-1 bg-slate-950 rounded-lg border border-slate-800/80 text-xs font-mono text-slate-300 truncate">
            <Globe className="w-3 h-3 text-slate-500 mr-2 shrink-0" />
            <span id="preview-url-display" className="truncate text-[11px] text-slate-300">
              {previewUrl || "Waiting for live preview..."}
            </span>
          </div>
        </div>

        {/* Actions: Reload & External */}
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
        ) : (
          <div className="flex flex-col items-center justify-center text-center p-8 max-w-sm">
            <div className="w-12 h-12 rounded-full bg-slate-900 border border-slate-800 flex items-center justify-center text-slate-500 mb-4">
              <Globe className="w-6 h-6" />
            </div>
            <h3 className="text-sm font-semibold text-slate-200 mb-1">
              No Application Preview Active
            </h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Launch an assembly line with preview mode enabled or enter a prompt in Factory Studio to start the live application server.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
