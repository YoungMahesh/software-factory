import React, { useState, useEffect } from "react";
import { X, Monitor, Smartphone, AlertTriangle, ShieldCheck } from "lucide-react";
import { Button } from "./ui/Button";
import { Badge } from "./ui/Badge";
import { VisualQaTelemetry } from "../types";

export interface VisualQAModalProps {
  isOpen: boolean;
  onClose: () => void;
  repo: string;
  telemetry?: VisualQaTelemetry | null;
  initialViewport?: "desktop" | "mobile";
}

export const VisualQAModal: React.FC<VisualQAModalProps> = ({
  isOpen,
  onClose,
  repo,
  telemetry,
  initialViewport = "desktop",
}) => {
  const [viewport, setViewport] = useState<"desktop" | "mobile">(initialViewport);

  useEffect(() => {
    if (initialViewport) {
      setViewport(initialViewport);
    }
  }, [initialViewport, isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const currentUrl =
    viewport === "desktop" ? telemetry?.desktop_url : telemetry?.mobile_url;
  const isPassed =
    telemetry?.passed === true ||
    telemetry?.status === "passed" ||
    telemetry?.status === "verified";
  const errors = telemetry?.errors || [];

  return (
    <div
      data-testid="visual-qa-modal-backdrop"
      className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 sm:p-6 overflow-y-auto"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        data-testid="visual-qa-modal"
        className="bg-primary border border-white/20 rounded-xl shadow-2xl max-w-5xl w-full max-h-[90vh] flex flex-col overflow-hidden text-white animate-in fade-in zoom-in-95 duration-150"
      >
        {/* Modal Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-white/10 bg-cohere-black/50">
          <div className="flex items-center space-x-3">
            <span className="font-semibold text-sm">Visual QA Inspection</span>
            <span className="text-slate-400 font-mono text-xs">{repo}</span>
            {isPassed ? (
              <Badge variant="success" className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30 text-[10px]">
                <ShieldCheck className="w-3 h-3 mr-1" />
                Verified
              </Badge>
            ) : (
              <Badge variant="danger" className="bg-coral/15 text-coral border-coral/30 text-[10px]">
                <AlertTriangle className="w-3 h-3 mr-1" />
                Failed
              </Badge>
            )}
          </div>

          {/* Viewport switchers & Close button */}
          <div className="flex items-center space-x-2">
            <div className="flex items-center bg-white/5 rounded-lg p-0.5 border border-white/10 text-xs">
              <button
                data-testid="vqa-modal-toggle-desktop"
                type="button"
                onClick={() => setViewport("desktop")}
                className={`flex items-center space-x-1.5 px-2.5 py-1 rounded-md transition-colors ${
                  viewport === "desktop"
                    ? "bg-white/20 text-white font-medium"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Monitor className="w-3.5 h-3.5" />
                <span>Desktop (1280x800)</span>
              </button>
              <button
                data-testid="vqa-modal-toggle-mobile"
                type="button"
                onClick={() => setViewport("mobile")}
                className={`flex items-center space-x-1.5 px-2.5 py-1 rounded-md transition-colors ${
                  viewport === "mobile"
                    ? "bg-white/20 text-white font-medium"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Smartphone className="w-3.5 h-3.5" />
                <span>Mobile (390x844)</span>
              </button>
            </div>

            <button
              data-testid="visual-qa-modal-close-btn"
              type="button"
              onClick={onClose}
              className="p-1 rounded-md text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
              title="Close inspection"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Modal Content */}
        <div className="p-5 overflow-y-auto space-y-4 max-h-[calc(90vh-120px)] bg-cohere-black/20">
          {/* Screenshot container */}
          <div className="flex justify-center bg-black/40 rounded-lg p-3 border border-white/10 min-h-[300px] items-center">
            {currentUrl ? (
              <img
                data-testid="visual-qa-modal-image"
                src={currentUrl}
                alt={`${viewport} viewport capture`}
                className={`rounded border border-white/10 shadow-lg object-contain ${
                  viewport === "mobile" ? "max-w-[390px] max-h-[600px]" : "max-w-full max-h-[650px]"
                }`}
              />
            ) : (
              <div data-testid="visual-qa-modal-empty" className="text-center text-slate-400 text-xs py-12">
                No {viewport} screenshot captured for this turn.
              </div>
            )}
          </div>

          {/* Telemetry error details */}
          {errors.length > 0 && (
            <div data-testid="visual-qa-modal-errors" className="p-3.5 rounded-lg bg-coral/10 border border-coral/30 space-y-1.5 text-xs text-coral">
              <div className="font-semibold flex items-center space-x-1.5">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                <span>Console Errors &amp; Clean Canvas Violations</span>
              </div>
              <ul className="list-disc pl-5 font-mono text-[11px] text-coral/90 space-y-1">
                {errors.map((err, i) => (
                  <li key={i}>{err}</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-5 py-3 border-t border-white/10 bg-cohere-black/50 flex items-center justify-between text-xs text-slate-400">
          <div>
            {telemetry?.captured_at ? (
              <span>Captured at {new Date(telemetry.captured_at * 1000).toLocaleTimeString()}</span>
            ) : (
              <span>Clean Canvas Invariant &amp; Viewport Telemetry</span>
            )}
          </div>
          <Button
            data-testid="visual-qa-modal-close-footer"
            type="button"
            variant="secondary"
            size="sm"
            onClick={onClose}
          >
            Close Preview
          </Button>
        </div>
      </div>
    </div>
  );
};
