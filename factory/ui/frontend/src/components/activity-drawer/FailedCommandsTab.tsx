import React from "react";
import { CheckCircle2 } from "lucide-react";
import { FailedCommand } from "../../types";
import { CommandCard } from "../CommandCard";

export interface FailedCommandsTabProps {
  failedCommands: FailedCommand[];
}

export const FailedCommandsTab: React.FC<FailedCommandsTabProps> = ({ failedCommands }) => {
  if (failedCommands.length === 0) {
    return (
      <div
        data-testid="failed-commands-empty-state"
        id="failed-commands-empty-state"
        className="flex flex-col items-center justify-center py-16 px-4 text-center space-y-3"
      >
        <div className="w-12 h-12 rounded-full bg-pale-green/40 border border-deep-green/20 flex items-center justify-center text-deep-green shadow-xs">
          <CheckCircle2 className="w-6 h-6" />
        </div>
        <div className="space-y-1">
          <h3 className="text-sm font-semibold text-ink font-sans">
            No Failed Commands
          </h3>
          <p className="text-xs text-muted max-w-sm leading-relaxed">
            All shell commands executed successfully during Coder Agent and Deterministic Verifier stages. Zero command failures detected.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div id="studio-drawer-failed-commands" className="space-y-3">
      {failedCommands.map((cmd) => (
        <CommandCard
          key={cmd.id}
          id={`failed-cmd-${cmd.id}`}
          command={cmd.command}
          cwd={cmd.cwd}
          stage={cmd.stage}
          exitCode={cmd.exitCode ?? cmd.exit_code}
          isError={cmd.isError ?? cmd.is_error}
          durationMs={cmd.durationMs ?? cmd.duration_ms}
          output={cmd.output || cmd.stdout || ""}
          stderr={cmd.stderr}
        />
      ))}
    </div>
  );
};
