import React from "react";
import { ViewportMode } from "../../types";

export interface LivePreviewFrameProps {
  previewUrl: string;
  viewport: ViewportMode;
  reloadKey: number;
}

export const LivePreviewFrame: React.FC<LivePreviewFrameProps> = ({
  previewUrl,
  viewport,
  reloadKey,
}) => {
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
    <div
      className="preview-viewport-wrapper h-full w-full transition-all duration-300 rounded-[22px] border border-hairline shadow-2xl bg-white overflow-hidden flex flex-col mx-auto"
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
  );
};
