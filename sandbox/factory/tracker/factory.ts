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

/**
 * Creates an IssueTracker instance based on explicit options or automated resolution.
 */
export function createIssueTracker(options: IssueTrackerFactoryOptions = {}): IssueTracker {
  if (options.trackerType === "github") {
    const client =
      options.client ??
      new GitHubClient({
        token: options.token,
        owner: options.owner,
        repo: options.repo,
      });
    return new GitHubIssueTracker({ client });
  }

  if (options.trackerType === "local") {
    return new LocalScratchTracker();
  }

  return resolveIssueTracker(options);
}

/**
 * Resolves the issue tracker by examining options, environment variables, and repository files.
 * Defaults to GitHubIssueTracker when repository environment includes an organization token or
 * TRACKER=github is set, or if .scratch/ is absent and GitHub credentials are present.
 * Defaults to LocalScratchTracker when .scratch/ is detected.
 */
export function resolveIssueTracker(options: IssueTrackerFactoryOptions = {}): IssueTracker {
  if (options.trackerType === "github" || process.env.TRACKER === "github") {
    const client =
      options.client ??
      new GitHubClient({
        token: options.token,
        owner: options.owner,
        repo: options.repo,
      });
    return new GitHubIssueTracker({ client });
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
      const client =
        options.client ??
        new GitHubClient({
          token: options.token,
          owner: options.owner,
          repo: options.repo,
        });
      return new GitHubIssueTracker({ client });
    } catch {
      // Fall through to LocalScratchTracker if client cannot be created
    }
  }

  return new LocalScratchTracker();
}
