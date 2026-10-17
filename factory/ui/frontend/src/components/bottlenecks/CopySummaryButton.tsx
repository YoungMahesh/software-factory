import React, { useState } from "react";
import { Copy, Check } from "lucide-react";
import { copyToClipboard } from "../../utils";

export interface CopySummaryButtonProps {
  id?: string;
  testId?: string;
  getText: () => string;
  title?: string;
}

export const CopySummaryButton: React.FC<CopySummaryButtonProps> = ({
  id = "btn-copy-bottlenecks-summary",
  testId = "btn-copy-bottlenecks-summary",
  getText,
  title = "Copy markdown summary to clipboard",
}) => {
  const [copied, setCopied] = useState<boolean>(false);

  const handleCopy = async () => {
    const text = getText();
    const ok = await copyToClipboard(text);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <button
      id={id}
      data-testid={testId}
      type="button"
      onClick={handleCopy}
      className="flex items-center space-x-1 px-2.5 py-1 rounded-pill text-xs font-mono font-medium text-slate-600 hover:text-ink bg-white border border-hairline hover:bg-soft-stone transition-colors cursor-pointer shadow-2xs"
      title={title}
    >
      {copied ? (
        <>
          <Check className="w-3.5 h-3.5 text-emerald-500" />
          <span>Copied</span>
        </>
      ) : (
        <>
          <Copy className="w-3.5 h-3.5 text-muted" />
          <span>Copy Summary</span>
        </>
      )}
    </button>
  );
};
