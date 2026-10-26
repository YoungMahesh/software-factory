import React from "react";
import { GitPullRequest, ExternalLink } from "lucide-react";
import { Badge } from "./ui/Badge";
import { PullRequest } from "../types";

export interface DeliveryGateHeaderProps {
  pr?: PullRequest;
  pullNumber?: number;
  isReverted?: boolean;
  statusBadge: React.ReactNode;
}

export const DeliveryGateHeader: React.FC<DeliveryGateHeaderProps> = ({
  pr,
  pullNumber,
  isReverted = false,
  statusBadge,
}) => {
  return (
    <div className="flex items-start justify-between gap-2">
      <div className="space-y-1">
        <div className="flex items-center space-x-2">
          <GitPullRequest className="w-4 h-4 text-coral shrink-0" />
          <span className="font-semibold text-white text-sm">
            {pr?.title || (pullNumber ? `Feature Pull Request #${pullNumber}` : "Feature Pull Request")}
          </span>
          {pullNumber ? (
            <span className="text-slate-400 font-mono text-xs">#{pullNumber}</span>
          ) : null}
        </div>
        {pr?.head_branch && (
          <div className="text-[11px] font-mono text-slate-400 pl-6">
            {pr.head_branch} <span className="text-slate-500">➔</span> main
          </div>
        )}
      </div>

      <div className="flex items-center space-x-2 shrink-0">
        {isReverted && (
          <Badge
            data-testid="turn-reverted-badge"
            variant="neutral"
            className="bg-white/10 text-slate-400 border-white/10"
          >
            Reverted
          </Badge>
        )}
        {statusBadge}
        {pr?.html_url && (
          <a
            data-testid="delivery-gate-gh-link"
            href={pr.html_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-slate-400 hover:text-white transition-colors p-1"
            title="View Pull Request on GitHub"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        )}
      </div>
    </div>
  );
};
