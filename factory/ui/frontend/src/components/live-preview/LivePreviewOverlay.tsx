import React from "react";
import {
  AlertTriangle,
  Globe,
  Loader2,
  Play,
  RotateCw,
} from "lucide-react";
import { PreviewStatus, PreviewStage } from "../../types";
import { PreviewProgressStepper } from "../PreviewProgressStepper";

export interface LivePreviewOverlayProps {
  status: PreviewStatus;
  stage?: PreviewStage;
  errorMessage?: string | null;
  onRetry: () => void;
  onReconnectPreview?: () => void;
  onLaunchPreview?: () => void;
  isLaunching?: boolean;
}

export const LivePreviewOverlay: React.FC<LivePreviewOverlayProps> = ({
  status,
  stage = "IDLE",
  errorMessage = null,
  onRetry,
  onReconnectPreview,
  onLaunchPreview,
  isLaunching = false,
}) => {
  if (status === "PROVISIONING") {
    return (
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
    );
  }

  if (status === "FAILED") {
    return (
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
            onClick={onRetry}
            className="flex items-center space-x-1.5 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-lg shadow-indigo-600/20 transition-all hover:scale-[1.02]"
          >
            <RotateCw className="w-3.5 h-3.5" />
            <span>Retry Startup</span>
          </button>
        </div>
      </div>
    );
  }

  if (status === "STOPPED") {
    return (
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
    );
  }

  return (
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
  );
};
