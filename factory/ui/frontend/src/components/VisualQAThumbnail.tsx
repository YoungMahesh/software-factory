import React from "react";
import { Monitor, Smartphone, ExternalLink, Image as ImageIcon } from "lucide-react";
import { VisualQaTelemetry } from "../types";

export interface VisualQAThumbnailProps {
  telemetry?: VisualQaTelemetry | null;
  onInspect: (viewport?: "desktop" | "mobile") => void;
  className?: string;
}

export const VisualQAThumbnail: React.FC<VisualQAThumbnailProps> = ({
  telemetry,
  onInspect,
  className = "",
}) => {
  const hasDesktop = Boolean(telemetry?.desktop_url);
  const hasMobile = Boolean(telemetry?.mobile_url);
  const thumbnailUrl = telemetry?.desktop_url || telemetry?.mobile_url;

  return (
    <div
      data-testid="delivery-gate-screenshot-thumbnail"
      className={`group rounded-lg border border-white/10 bg-cohere-black/50 p-2.5 flex items-center justify-between gap-3 hover:border-white/25 transition-all cursor-pointer ${className}`}
      onClick={() => onInspect(hasDesktop ? "desktop" : "mobile")}
      title="Click to inspect visual verification screenshots"
    >
      <div className="flex items-center space-x-3 min-w-0">
        {thumbnailUrl ? (
          <img
            src={thumbnailUrl}
            alt="Visual QA preview thumbnail"
            className="w-16 h-10 object-cover rounded border border-white/10 shrink-0 group-hover:scale-105 transition-transform"
          />
        ) : (
          <div className="w-16 h-10 rounded border border-white/10 bg-white/5 flex items-center justify-center shrink-0 text-slate-500">
            <ImageIcon className="w-4 h-4" />
          </div>
        )}
        <div className="space-y-0.5 truncate">
          <div className="text-xs font-medium text-slate-200 flex items-center space-x-1.5">
            <span>Visual Verification Preview</span>
            <ExternalLink className="w-3 h-3 text-slate-400 group-hover:text-white transition-colors" />
          </div>
          <div className="text-[11px] text-slate-400">
            {thumbnailUrl
              ? "Click thumbnail to inspect full-page viewports"
              : "Headless Chrome viewport capture pending"}
          </div>
        </div>
      </div>

      {/* Desktop and Mobile capture indicators */}
      <div className="flex items-center space-x-1.5 shrink-0 text-[11px] font-mono">
        <span
          data-testid="vqa-desktop-status"
          className={`flex items-center space-x-1 px-1.5 py-0.5 rounded border ${
            hasDesktop
              ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
              : "bg-white/5 border-white/10 text-slate-500"
          }`}
        >
          <Monitor className="w-3 h-3" />
          <span>Desktop {hasDesktop ? "✓" : "—"}</span>
        </span>
        <span
          data-testid="vqa-mobile-status"
          className={`flex items-center space-x-1 px-1.5 py-0.5 rounded border ${
            hasMobile
              ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
              : "bg-white/5 border-white/10 text-slate-500"
          }`}
        >
          <Smartphone className="w-3 h-3" />
          <span>Mobile {hasMobile ? "✓" : "—"}</span>
        </span>
      </div>
    </div>
  );
};
