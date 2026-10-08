import * as fs from "node:fs";

export interface TicketUpdateOptions {
  filePath: string;
  status: "resolved" | "ready-for-human" | "claimed" | "open" | "ready-for-agent";
  branch?: string;
  commitSha?: string;
  auditSummary?: string;
  failureDiagnostics?: string;
}

/**
 * Updates a local markdown ticket file inline with resolution status,
 * branch name, commit SHA, and audit trail / failure diagnostics.
 */
export function updateTicketFile(options: TicketUpdateOptions): string {
  const { filePath, status, branch, commitSha, auditSummary, failureDiagnostics } = options;
  let content = fs.readFileSync(filePath, "utf-8");

  // 1. Replace or update Status line
  const statusLineRegex = /(^|\n)\s*\*{0,2}Status(?::\*{0,2}|\*{0,2}:)[^\n\r]*/i;
  if (statusLineRegex.test(content)) {
    content = content.replace(statusLineRegex, `$1**Status:** ${status}`);
  } else {
    content = `**Status:** ${status}\n\n` + content;
  }

  // 2. Add or update Branch line if provided
  if (branch) {
    const branchLineRegex = /(^|\n)\s*\*{0,2}Branch(?::\*{0,2}|\*{0,2}:)[^\n\r]*/i;
    if (branchLineRegex.test(content)) {
      content = content.replace(branchLineRegex, `$1**Branch:** ${branch}`);
    } else {
      const statusMatch = /(^|\n)(\s*\*{0,2}Status(?::\*{0,2}|\*{0,2}:)[^\n\r]*)/i;
      if (statusMatch.test(content)) {
        content = content.replace(statusMatch, `$1$2\n\n**Branch:** ${branch}`);
      } else {
        content = `**Branch:** ${branch}\n\n` + content;
      }
    }
  }

  // 3. Add or update Commit line if provided
  if (commitSha) {
    const commitLineRegex = /(^|\n)\s*\*{0,2}Commit(?::\*{0,2}|\*{0,2}:)[^\n\r]*/i;
    if (commitLineRegex.test(content)) {
      content = content.replace(commitLineRegex, `$1**Commit:** ${commitSha}`);
    } else {
      const branchMatch = /(^|\n)(\s*\*{0,2}Branch(?::\*{0,2}|\*{0,2}:)[^\n\r]*)/i;
      const statusMatch = /(^|\n)(\s*\*{0,2}Status(?::\*{0,2}|\*{0,2}:)[^\n\r]*)/i;
      if (branchMatch.test(content)) {
        content = content.replace(branchMatch, `$1$2\n\n**Commit:** ${commitSha}`);
      } else if (statusMatch.test(content)) {
        content = content.replace(statusMatch, `$1$2\n\n**Commit:** ${commitSha}`);
      } else {
        content = `**Commit:** ${commitSha}\n\n` + content;
      }
    }
  }

  // 4. Append audit summary or failure diagnostics
  const appendBlock = auditSummary
    ? `### Quality Gate Audit\n\n${auditSummary.trim()}\n`
    : failureDiagnostics
    ? `### Failure Diagnostics\n\n${failureDiagnostics.trim()}\n`
    : "";

  if (appendBlock) {
    const commentsRegex = /(^|\n)##\s+Comments\s*([\s\S]*)$/i;
    if (commentsRegex.test(content)) {
      content = content.trimEnd() + `\n\n${appendBlock.trim()}\n`;
    } else {
      content = content.trimEnd() + `\n\n## Comments\n\n${appendBlock.trim()}\n`;
    }
  }

  fs.writeFileSync(filePath, content, "utf-8");
  return content;
}
