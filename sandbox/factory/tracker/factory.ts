import * as fs from "node:fs";
import * as path from "node:path";
import { GitHubClient } from "../github.ts";
import { GitHubIssueTracker } from "./github-tracker.ts";
import { LocalScratchTracker } from "./local-tracker.ts";
import type { IssueTracker, TrackerType } from "./types.ts";

export interface IssueTrackerFactoryOptions {
  workspaceDir?: string;
  featureSlug?: string;
  trackerType?: TrackerType;
  token?: string;
  owner?: string;
  repo?: string;
  client?: GitHubClient;
}

function getGitHubClient(options: IssueTrackerFactoryOptions): GitHubClient {
  return (
    options.client ??
    new GitHubClient({
      token: options.token,
      owner: options.owner,
      repo: options.repo,
    })
  );
}

/**
 * Resolves the issue tracker by examining options, environment variables, and repository files.
 * Defaults to GitHubIssueTracker when repository environment includes an organization token or
 * TRACKER=github is set, or if .scratch/ is absent and GitHub credentials are present.
 * Defaults to LocalScratchTracker when .scratch/ is detected.
 */
export function resolveIssueTracker(options: IssueTrackerFactoryOptions = {}): IssueTracker {
  if (options.trackerType === "github" || process.env.TRACKER === "github") {
    return new GitHubIssueTracker({ client: getGitHubClient(options) });
  }

  if (options.trackerType === "local" || process.env.TRACKER === "local") {
    return new LocalScratchTracker();
  }

  const workspace = options.workspaceDir ?? process.cwd();
  const hasScratch = fs.existsSync(path.join(workspace, ".scratch"));
  const hasToken = Boolean(
    options.token || process.env.GH_TOKEN || process.env.GITHUB_TOKEN
  );

  if (hasToken && !hasScratch) {
    try {
      return new GitHubIssueTracker({ client: getGitHubClient(options) });
    } catch {
      // Fall through to LocalScratchTracker if client cannot be created
    }
  }

  return new LocalScratchTracker();
}

/**
 * Creates or resolves an IssueTracker instance (alias for resolveIssueTracker).
 */
export const createIssueTracker = resolveIssueTracker;

