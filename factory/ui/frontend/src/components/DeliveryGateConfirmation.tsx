import React from "react";
import { GitMerge } from "lucide-react";
import { Button } from "./ui/Button";

export interface DeliveryGateConfirmationProps {
  pullNumber?: number;
  isLoading: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export const DeliveryGateConfirmation: React.FC<DeliveryGateConfirmationProps> = ({
  pullNumber,
  isLoading,
  onConfirm,
  onCancel,
}) => {
  return (
    <div className="p-3 rounded-lg bg-cohere-black/90 border border-white/10 space-y-2.5">
      <div className="text-slate-200 font-medium text-xs">
        Squash merge Feature Pull Request #{pullNumber} into main?
      </div>
      <div className="text-[11px] text-slate-400">
        This will create a squash commit on <span className="font-mono text-slate-300">main</span>, delete the remote feature branch, and update the Live Preview.
      </div>
      <div className="flex items-center space-x-2 pt-1">
        <Button
          data-testid="btn-delivery-gate-confirm-merge"
          type="button"
          variant="inverted"
          size="sm"
          onClick={onConfirm}
          isLoading={isLoading}
          disabled={isLoading}
          icon={<GitMerge className="w-3.5 h-3.5" />}
          className="font-medium"
        >
          Confirm Squash Merge
        </Button>
        <Button
          data-testid="btn-delivery-gate-cancel-merge"
          type="button"
          variant="secondary"
          size="sm"
          onClick={onCancel}
          disabled={isLoading}
          className="text-slate-300"
        >
          Cancel
        </Button>
      </div>
    </div>
  );
};
