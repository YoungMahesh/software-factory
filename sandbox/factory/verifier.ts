import * as child_process from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";

export type StreamChunkHandler = (chunk: string, stream: "stdout" | "stderr") => void;

export interface StreamOptions {
  onStream?: StreamChunkHandler;
  streamToProcess?: boolean;
}

export interface CommandResult {
  command: string;
  exitCode: number | null;
  signal: NodeJS.Signals | null;
  passed: boolean;
  timedOut: boolean;
  stdout: string;
  stderr: string;
  output: string;
  durationMs: number;
  error?: string;
}

export interface RunCommandOptions extends StreamOptions {
  cwd: string;
  timeoutMs?: number;
  env?: NodeJS.ProcessEnv;
}

export interface DiscoveredCommands {
  test: string[];
  lint: string[];
  all: string[];
}

export interface VerifyWorkspaceOptions extends StreamOptions {
  workspacePath: string;
  commands?: string[];
  timeoutMs?: number;
  env?: NodeJS.ProcessEnv;
  failFast?: boolean;
  logPath?: string;
}

export interface VerificationResult {
  passed: boolean;
  totalCommands: number;
  passedCommands: number;
  failedCommands: number;
  results: CommandResult[];
  summary: string;
  durationMs: number;
  logPath?: string;
}

/**
 * Discovers default test and lint commands from Node.js and common workspace configuration.
 */
export function discoverCommands(workspacePath: string): DiscoveredCommands {
  const test: string[] = [];
  const lint: string[] = [];

  const pkgPath = path.join(workspacePath, "package.json");
  if (fs.existsSync(pkgPath)) {
    try {
      const content = fs.readFileSync(pkgPath, "utf-8");
      const pkg = JSON.parse(content);
      const scripts = pkg.scripts || {};

      let pm = "npm";
      if (fs.existsSync(path.join(workspacePath, "pnpm-lock.yaml"))) {
        pm = "pnpm";
      } else if (fs.existsSync(path.join(workspacePath, "yarn.lock"))) {
        pm = "yarn";
      } else if (
        fs.existsSync(path.join(workspacePath, "bun.lockb")) ||
        fs.existsSync(path.join(workspacePath, "bun.lock"))
      ) {
        pm = "bun";
      }

      if (scripts.lint) {
        lint.push(`${pm} run lint`);
      }
      if (scripts.typecheck) {
        lint.push(`${pm} run typecheck`);
      } else if (scripts.check) {
        lint.push(`${pm} run check`);
      }

      if (scripts.test) {
        const testScript = String(scripts.test).trim();
        const isPlaceholder = /echo\s+["']?Error:\s+no\s+test\s+specified["']?\s*&&\s*exit\s+1/i.test(testScript);
        if (!isPlaceholder) {
          test.push(`${pm} test`);
        }
      }
    } catch {
      // Ignore JSON parse errors
    }
  }

  const pyprojectPath = path.join(workspacePath, "pyproject.toml");
  if (fs.existsSync(pyprojectPath)) {
    test.push("pytest");
  }

  const cargoPath = path.join(workspacePath, "Cargo.toml");
  if (fs.existsSync(cargoPath)) {
    test.push("cargo test");
  }

  const uniqueTest = Array.from(new Set(test));
  const uniqueLint = Array.from(new Set(lint));
  const all = [...uniqueLint, ...uniqueTest];

  return {
    test: uniqueTest,
    lint: uniqueLint,
    all,
  };
}

function attachStreamListener(
  stream: NodeJS.ReadableStream | null | undefined,
  name: "stdout" | "stderr",
  options: StreamOptions,
  onChunk: (text: string) => void
): void {
  if (!stream) return;
  stream.on("data", (chunk: Buffer) => {
    const text = chunk.toString("utf-8");
    onChunk(text);
    if (options.onStream) {
      options.onStream(text, name);
    }
    if (options.streamToProcess) {
      if (name === "stdout") {
        process.stdout.write(text);
      } else {
        process.stderr.write(text);
      }
    }
  });
}

export async function runCommand(command: string, options: RunCommandOptions): Promise<CommandResult> {
  const startTime = Date.now();

  return new Promise<CommandResult>((resolve) => {
    let stdout = "";
    let stderr = "";
    let output = "";
    let timedOut = false;
    let settled = false;
    let timer: NodeJS.Timeout | null = null;
    let killTimer: NodeJS.Timeout | null = null;

    let child: child_process.ChildProcess;
    try {
      child = child_process.spawn(command, {
        cwd: options.cwd,
        shell: true,
        detached: process.platform !== "win32",
        env: options.env ? { ...process.env, ...options.env } : process.env,
      });
    } catch (err: unknown) {
      const durationMs = Date.now() - startTime;
      const errorMsg = err instanceof Error ? err.message : String(err);
      resolve({
        command,
        exitCode: null,
        signal: null,
        passed: false,
        timedOut: false,
        stdout: "",
        stderr: "",
        output: "",
        durationMs,
        error: errorMsg,
      });
      return;
    }

    const cleanupTimers = () => {
      if (timer) clearTimeout(timer);
      if (killTimer) clearTimeout(killTimer);
    };

    const killProcessGroup = (sig: NodeJS.Signals) => {
      if (!child.pid) return;
      try {
        if (process.platform !== "win32") {
          process.kill(-child.pid, sig);
        } else {
          child.kill(sig);
        }
      } catch (err: unknown) {
        if ((err as NodeJS.ErrnoException).code !== "ESRCH") {
          // ignore already exited processes
        }
      }
    };

    if (options.timeoutMs && options.timeoutMs > 0) {
      timer = setTimeout(() => {
        timedOut = true;
        killProcessGroup("SIGTERM");
        killTimer = setTimeout(() => {
          killProcessGroup("SIGKILL");
        }, 500);
      }, options.timeoutMs);
    }

    attachStreamListener(child.stdout, "stdout", options, (text) => {
      stdout += text;
      output += text;
    });

    attachStreamListener(child.stderr, "stderr", options, (text) => {
      stderr += text;
      output += text;
    });

    child.on("error", (err: Error) => {
      if (settled) return;
      settled = true;
      cleanupTimers();
      const durationMs = Date.now() - startTime;
      resolve({
        command,
        exitCode: null,
        signal: null,
        passed: false,
        timedOut: false,
        stdout,
        stderr,
        output,
        durationMs,
        error: err.message,
      });
    });

    child.on("close", (code, signal) => {
      if (settled) return;
      settled = true;
      cleanupTimers();
      const durationMs = Date.now() - startTime;
      const passed = !timedOut && code === 0 && signal === null;
      let error: string | undefined;

      if (timedOut) {
        error = `Command timed out after ${options.timeoutMs}ms`;
      }

      resolve({
        command,
        exitCode: code,
        signal,
        passed,
        timedOut,
        stdout,
        stderr,
        output,
        durationMs,
        error,
      });
    });
  });
}

export function formatVerificationSummary(
  passed: boolean,
  results: CommandResult[],
  totalCommands: number,
  passedCommands: number,
  durationMs: number
): string {
  const statusBadge = passed ? "PASSED" : "FAILED";
  const lines: string[] = [
    `### Verification Summary: ${statusBadge}`,
    ``,
    `- **Status**: ${statusBadge}`,
    `- **Passed**: ${passedCommands} / ${totalCommands} command(s)`,
    `- **Duration**: ${durationMs}ms`,
    ``,
    `| Status | Command | Exit Code | Duration |`,
    `| :--- | :--- | :--- | :--- |`,
  ];

  for (const r of results) {
    const status = r.passed ? "PASS" : r.timedOut ? "TIMEOUT" : "FAIL";
    const code = r.exitCode !== null ? String(r.exitCode) : r.signal ? `signal(${r.signal})` : "err";
    lines.push(`| ${status} | \`${r.command}\` | ${code} | ${r.durationMs}ms |`);
  }

  const failedRuns = results.filter((r) => !r.passed);
  if (failedRuns.length > 0) {
    lines.push(``, `#### Failure Details`, ``);
    for (const f of failedRuns) {
      lines.push(`**Command**: \`${f.command}\``);
      if (f.error) {
        lines.push(`**Error**: ${f.error}`);
      }
      if (f.stderr.trim()) {
        lines.push(`**Stderr**:`, "```", f.stderr.trim(), "```");
      }
      if (f.stdout.trim()) {
        lines.push(`**Stdout**:`, "```", f.stdout.trim(), "```");
      }
      lines.push(``);
    }
  }

  return lines.join("\n");
}

export async function verifyWorkspace(options: VerifyWorkspaceOptions): Promise<VerificationResult> {
  const startTime = Date.now();
  const failFast = options.failFast ?? true;

  // Determine commands: respect explicit commands array if provided, otherwise discover
  let commands: string[];
  if (options.commands !== undefined) {
    commands = options.commands;
  } else {
    const discovered = discoverCommands(options.workspacePath);
    commands = discovered.all;
  }

  if (commands.length === 0) {
    const durationMs = Date.now() - startTime;
    const summary = "### Verification Summary: FAILED\n\nNo test or lint commands specified or discovered in workspace.";
    return {
      passed: false,
      totalCommands: 0,
      passedCommands: 0,
      failedCommands: 0,
      results: [],
      summary,
      durationMs,
    };
  }

  const results: CommandResult[] = [];
  let passedCommands = 0;
  let failedCommands = 0;

  for (const command of commands) {
    const result = await runCommand(command, {
      cwd: options.workspacePath,
      timeoutMs: options.timeoutMs,
      env: options.env,
      onStream: options.onStream,
      streamToProcess: options.streamToProcess,
    });

    results.push(result);

    if (result.passed) {
      passedCommands++;
    } else {
      failedCommands++;
      if (failFast) {
        break;
      }
    }
  }

  const durationMs = Date.now() - startTime;
  const passed = results.length > 0 && failedCommands === 0;
  const summary = formatVerificationSummary(
    passed,
    results,
    commands.length,
    passedCommands,
    durationMs
  );

  // Persist structured verification log if logPath is configured
  if (options.logPath) {
    try {
      const logDir = path.dirname(options.logPath);
      if (!fs.existsSync(logDir)) {
        fs.mkdirSync(logDir, { recursive: true });
      }
      fs.writeFileSync(options.logPath, summary, "utf-8");
    } catch {
      // Non-fatal if writing log fails
    }
  }

  return {
    passed,
    totalCommands: commands.length,
    passedCommands,
    failedCommands,
    results,
    summary,
    durationMs,
    logPath: options.logPath,
  };
}
