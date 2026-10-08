import { execSync } from "node:child_process";

export interface GitBranchOptions {
  workspaceDir: string;
  featureSlug: string;
  remote?: string;
}

export interface CommitAndPushOptions {
  workspaceDir: string;
  featureSlug: string;
  ticketId: string;
  ticketTitle?: string;
  commitMessage?: string;
  push?: boolean;
  remote?: string;
}

export interface CommitFailureOptions {
  workspaceDir: string;
  featureSlug: string;
  ticketId: string;
  ticketFilePath?: string;
  push?: boolean;
  remote?: string;
}

export class GitExecutionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "GitExecutionError";
  }
}

/**
 * Helper to check whether there are staged changes in the git index.
 */
export function hasStagedChanges(workspaceDir: string): boolean {
  try {
    execSync("git diff --cached --quiet", {
      cwd: workspaceDir,
      stdio: "ignore",
    });
    return false;
  } catch {
    return true;
  }
}

/**
 * Checks out the shared feature branch (`factory/<feature>`).
 * If the branch doesn't exist locally:
 * - Checks if remote branch exists (origin/factory/<feature>) and tracks it.
 * - Otherwise creates a new branch from current HEAD.
 */
export function ensureFeatureBranch(options: GitBranchOptions): string {
  const { workspaceDir, featureSlug } = options;
  const remote = options.remote ?? "origin";
  const branchName = `factory/${featureSlug}`;

  try {
    const currentBranch = execSync("git branch --show-current", {
      cwd: workspaceDir,
      encoding: "utf-8",
    }).trim();

    if (currentBranch === branchName) {
      return branchName;
    }

    // Check if branch exists locally
    let localExists = false;
    try {
      execSync(`git rev-parse --verify "${branchName}"`, {
        cwd: workspaceDir,
        stdio: "ignore",
      });
      localExists = true;
    } catch {
      localExists = false;
    }

    if (localExists) {
      execSync(`git checkout "${branchName}"`, {
        cwd: workspaceDir,
        stdio: ["ignore", "pipe", "pipe"],
      });
      return branchName;
    }

    // Check if remote branch exists
    let remoteExists = false;
    try {
      const remoteCheck = execSync(`git ls-remote --heads ${remote} "${branchName}"`, {
        cwd: workspaceDir,
        stdio: ["ignore", "pipe", "ignore"],
        encoding: "utf-8",
      }).trim();
      if (remoteCheck.length > 0) {
        remoteExists = true;
      }
    } catch {
      remoteExists = false;
    }

    if (remoteExists) {
      try {
        execSync(`git fetch ${remote} "+refs/heads/${branchName}:refs/remotes/${remote}/${branchName}"`, {
          cwd: workspaceDir,
          stdio: ["ignore", "pipe", "ignore"],
        });
      } catch {
        // ignore fetch error if tracking ref already populated
      }
      execSync(`git checkout -b "${branchName}" "${remote}/${branchName}"`, {
        cwd: workspaceDir,
        stdio: ["ignore", "pipe", "pipe"],
      });
    } else {
      execSync(`git checkout -b "${branchName}"`, {
        cwd: workspaceDir,
        stdio: ["ignore", "pipe", "pipe"],
      });
    }

    return branchName;
  } catch (err: any) {
    throw new GitExecutionError(
      `Failed to ensure feature branch "${branchName}": ${err?.message ?? String(err)}`
    );
  }
}

/**
 * Stages all changes, creates a commit for the resolved ticket,
 * and pushes immediately to `origin factory/<feature>` if push is enabled.
 */
export function commitAndPushFeatureBranch(options: CommitAndPushOptions): {
  commitSha: string;
  branch: string;
  pushed: boolean;
} {
  const { workspaceDir, featureSlug, ticketId } = options;
  const remote = options.remote ?? "origin";
  const branch = `factory/${featureSlug}`;
  const shouldPush = options.push ?? true;

  try {
    // Stage all changes
    execSync("git add -A", {
      cwd: workspaceDir,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let commitSha: string;
    if (hasStagedChanges(workspaceDir)) {
      const titleSuffix = options.ticketTitle ? ` - ${options.ticketTitle}` : "";
      const commitMsg =
        options.commitMessage || `feat(${featureSlug}): resolve ${ticketId}${titleSuffix}`;

      execSync(`git commit -m "${commitMsg.replace(/"/g, '\\"')}"`, {
        cwd: workspaceDir,
        stdio: ["ignore", "pipe", "pipe"],
      });
    }

    commitSha = execSync("git rev-parse HEAD", {
      cwd: workspaceDir,
      encoding: "utf-8",
    }).trim();

    let pushed = false;
    if (shouldPush) {
      try {
        execSync(`git push -u ${remote} "${branch}"`, {
          cwd: workspaceDir,
          stdio: ["ignore", "pipe", "pipe"],
        });
        pushed = true;
      } catch (pushErr: any) {
        throw new GitExecutionError(
          `Failed to push "${branch}" to ${remote}: ${pushErr?.message ?? String(pushErr)}`
        );
      }
    }

    return { commitSha, branch, pushed };
  } catch (err: any) {
    if (err instanceof GitExecutionError) throw err;
    throw new GitExecutionError(
      `Git commit or push failed for ticket ${ticketId}: ${err?.message ?? String(err)}`
    );
  }
}

/**
 * Commits failure diagnostics when a ticket fails after exhausted retries.
 */
export function commitFailureDiagnostics(options: CommitFailureOptions): {
  commitSha: string;
  branch: string;
  pushed: boolean;
} {
  const { workspaceDir, featureSlug, ticketId, ticketFilePath } = options;
  const remote = options.remote ?? "origin";
  const branch = `factory/${featureSlug}`;
  const shouldPush = options.push ?? false;

  try {
    if (ticketFilePath) {
      execSync(`git add "${ticketFilePath}"`, {
        cwd: workspaceDir,
        stdio: ["ignore", "pipe", "pipe"],
      });
    } else {
      execSync("git add -A", {
        cwd: workspaceDir,
        stdio: ["ignore", "pipe", "pipe"],
      });
    }

    if (hasStagedChanges(workspaceDir)) {
      const commitMsg = `chore(${featureSlug}): mark ticket ${ticketId} ready-for-human [diagnostics]`;
      execSync(`git commit -m "${commitMsg.replace(/"/g, '\\"')}"`, {
        cwd: workspaceDir,
        stdio: ["ignore", "pipe", "pipe"],
      });
    }

    const commitSha = execSync("git rev-parse HEAD", {
      cwd: workspaceDir,
      encoding: "utf-8",
    }).trim();

    let pushed = false;
    if (shouldPush) {
      try {
        execSync(`git push ${remote} "${branch}"`, {
          cwd: workspaceDir,
          stdio: ["ignore", "pipe", "pipe"],
        });
        pushed = true;
      } catch {
        pushed = false;
      }
    }

    return { commitSha, branch, pushed };
  } catch (err: any) {
    throw new GitExecutionError(
      `Failed to commit failure diagnostics for ticket ${ticketId}: ${err?.message ?? String(err)}`
    );
  }
}
