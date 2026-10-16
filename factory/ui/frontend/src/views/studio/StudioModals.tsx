import React from "react";
import { AlertTriangle, Check, XCircle } from "lucide-react";
import { NewAppModal } from "../../components/NewAppModal";
import { TurnRollbackModal } from "../../components/TurnRollbackModal";
import { DisconnectedModal } from "../../components/DisconnectedModal";
import { IssueDrawer } from "../../components/IssueDrawer";
import { RollbackTarget } from "../../types";

export interface StudioModalsProps {
  isNewAppModalOpen: boolean;
  onCloseNewAppModal: () => void;
  onCreateRepo: (repoData: any) => Promise<any>;
  isRollbackModalOpen: boolean;
  onCloseRollbackModal: () => void;
  onConfirmRollback: () => Promise<void>;
  isRollingBack: boolean;
  selectedRepo: string;
  targetRollbackTurn: RollbackTarget | null;
  previewBranch: string | null;
  rollbackError: string | null;
  isDisconnected: boolean;
  isDismissedDisconnected: boolean;
  onReconnect: () => void;
  onDismissDisconnected: () => void;
  isLaunchingPreview: boolean;
  isIssueDrawerOpen: boolean;
  onCloseIssues: () => void;
  branchSwitchError: string | null;
  onDismissBranchSwitchError: () => void;
  toast: { type: "success" | "error"; message: string } | null;
  onDismissToast: () => void;
}

export const StudioModals: React.FC<StudioModalsProps> = ({
  isNewAppModalOpen,
  onCloseNewAppModal,
  onCreateRepo,
  isRollbackModalOpen,
  onCloseRollbackModal,
  onConfirmRollback,
  isRollingBack,
  selectedRepo,
  targetRollbackTurn,
  previewBranch,
  rollbackError,
  isDisconnected,
  isDismissedDisconnected,
  onReconnect,
  onDismissDisconnected,
  isLaunchingPreview,
  isIssueDrawerOpen,
  onCloseIssues,
  branchSwitchError,
  onDismissBranchSwitchError,
  toast,
  onDismissToast,
}) => {
  return (
    <>
      {/* New App Modal */}
      <NewAppModal
        isOpen={isNewAppModalOpen}
        onClose={onCloseNewAppModal}
        onCreate={onCreateRepo}
      />

      {/* Turn Rollback Confirmation Modal */}
      <TurnRollbackModal
        isOpen={isRollbackModalOpen}
        onClose={onCloseRollbackModal}
        onConfirm={onConfirmRollback}
        isRollingBack={isRollingBack}
        repo={selectedRepo}
        branch={targetRollbackTurn?.branch || previewBranch || null}
        commitSha={targetRollbackTurn?.commitSha || null}
        issueNumber={targetRollbackTurn?.issueNumber || null}
        issueTitle={targetRollbackTurn?.issueTitle || null}
        errorMessage={rollbackError}
      />

      {/* Sandbox Disconnected Dialog */}
      <DisconnectedModal
        isOpen={isDisconnected && !isDismissedDisconnected}
        branch={previewBranch || undefined}
        onReconnect={onReconnect}
        onDismiss={onDismissDisconnected}
        isReconnecting={isLaunchingPreview}
      />

      {/* GitHub Issue Drawer */}
      <IssueDrawer
        isOpen={isIssueDrawerOpen}
        onClose={onCloseIssues}
        repo={selectedRepo}
      />

      {/* Branch Switch Error Toast */}
      {branchSwitchError && (
        <div
          data-testid="branch-switch-error-toast"
          role="alert"
          className="fixed bottom-6 right-6 max-w-md bg-white border border-coral text-coral px-4 py-3 rounded-xl shadow-2xl z-50 flex items-start space-x-3 transition-all"
        >
          <AlertTriangle className="w-5 h-5 text-coral shrink-0 mt-0.5" />
          <div className="flex-1 text-xs">
            <h4 className="font-semibold text-coral mb-0.5 font-sans">Branch Switch Failed</h4>
            <p className="text-[11px] text-ink leading-relaxed mb-1">{branchSwitchError}</p>
            <p className="text-[10px] text-muted font-mono">
              Check the Dev Server Logs drawer for in-container diagnostics.
            </p>
          </div>
          <button
            type="button"
            data-testid="dismiss-branch-error-btn"
            onClick={onDismissBranchSwitchError}
            className="text-muted hover:text-coral p-1 rounded-pill transition-colors cursor-pointer"
            title="Dismiss error alert"
          >
            <XCircle className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Toast Notification */}
      {toast && (
        <div
          data-testid="studio-toast"
          role="alert"
          className={`fixed bottom-6 right-6 z-50 flex items-center space-x-2.5 px-4 py-2.5 rounded-pill border shadow-xl text-xs font-medium transition-all ${
            toast.type === "success"
              ? "bg-white border-deep-green/30 text-deep-green shadow-sm"
              : "bg-white border-coral/30 text-coral shadow-sm"
          }`}
        >
          {toast.type === "success" ? (
            <Check className="w-4 h-4 text-deep-green shrink-0" />
          ) : (
            <AlertTriangle className="w-4 h-4 text-coral shrink-0" />
          )}
          <span>{toast.message}</span>
          <button
            type="button"
            onClick={onDismissToast}
            className="ml-2 text-muted hover:text-ink cursor-pointer"
            aria-label="Dismiss notification"
          >
            <XCircle className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
    </>
  );
};
