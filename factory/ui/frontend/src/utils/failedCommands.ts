import { AgentEvent, FailedCommand } from "../types";

/**
 * Extracts and isolates failed shell command executions from telemetry events.
 *
 * Scoped strictly to bash tool executions within the CODER and VERIFIER stages
 * where exitCode != 0 or isError is true. Excludes zero exit codes and read-only tools.
 */
export function extractFailedCommands(events: AgentEvent[] = []): FailedCommand[] {
  if (!events || events.length === 0) {
    return [];
  }

  const failed: FailedCommand[] = [];
  const allowedStages = new Set(["CODER", "VERIFIER"]);

  events.forEach((evt, idx) => {
    const evtType = evt.type;
    if (evtType !== "tool_result") {
      return;
    }

    const stage = (evt.stage || "").toUpperCase();
    if (!allowedStages.has(stage)) {
      return;
    }

    const data = evt.data || {};
    const toolName = (data.toolName || "").toLowerCase();
    if (toolName !== "bash") {
      return;
    }

    const exitCodeRaw = data.exitCode !== undefined && data.exitCode !== null ? data.exitCode : data.exit_code;
    const isError = Boolean(data.isError || data.is_error || false);

    let exitCode: number;
    if (exitCodeRaw !== undefined && exitCodeRaw !== null) {
      exitCode = Number(exitCodeRaw);
      if (isNaN(exitCode)) {
        exitCode = isError ? 1 : 0;
      }
    } else {
      exitCode = isError ? 1 : 0;
    }

    if (exitCode === 0 && !isError) {
      return;
    }

    const args = typeof data.args === "object" && data.args !== null ? data.args : {};
    const command = data.command || args.command || "bash";
    const cwd = data.cwd || args.cwd;
    const durationMs = data.durationMs !== undefined ? data.durationMs : data.duration_ms;
    const stdout = data.stdout || "";
    const stderr = data.stderr || "";
    const output = data.output || stdout || stderr || "";
    const id = data.toolCallId || data.tool_call_id || (evt.timestamp ? `failed-${evt.timestamp}-${idx}` : `failed-${idx}`);

    failed.push({
      id: String(id),
      command,
      cwd,
      stage,
      exitCode,
      exit_code: exitCode,
      durationMs,
      duration_ms: durationMs,
      stdout,
      stderr,
      output,
      isError: isError || exitCode !== 0,
      is_error: isError || exitCode !== 0,
      timestamp: evt.timestamp,
    });
  });

  return failed;
}
