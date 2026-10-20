import React from "react";

interface DiffStatsBadgesProps {
  additions: number;
  deletions: number;
  additionsTestId?: string;
  deletionsTestId?: string;
}

export const DiffStatsBadges: React.FC<DiffStatsBadgesProps> = ({
  additions,
  deletions,
  additionsTestId = "diff-summary-additions",
  deletionsTestId = "diff-summary-deletions",
}) => {
  return (
    <div className="flex items-center space-x-1.5 font-mono text-xs">
      <span
        data-testid={additionsTestId}
        className="inline-flex items-center text-deep-green bg-pale-green/40 px-2 py-0.5 rounded-full font-medium text-[11px] border border-deep-green/20"
      >
        +{additions}
      </span>
      <span
        data-testid={deletionsTestId}
        className="inline-flex items-center text-coral bg-coral/10 px-2 py-0.5 rounded-full font-medium text-[11px] border border-coral/20"
      >
        -{deletions}
      </span>
    </div>
  );
};
