import {
  type ImplementationPlan,
  type ReviewVerdict,
  type ReviewIssue,
  PlanParseError,
  ReviewParseError,
} from "./types.ts";
import { isDevServerCommand } from "../verifier.ts";

/**
 * Parses an implementation plan from JSON or markdown text.
 * Requires non-empty affectedFiles and testCommands.
 */
export function parseImplementationPlan(
  content: string,
  fallbackTicketId: string = "unknown"
): ImplementationPlan {
  const trimmed = content.trim();

  // Try extracting from all JSON blocks first
  const codeBlockRegex = /```(?:json)?\s*([\s\S]*?)\s*```/g;
  let codeMatch: RegExpExecArray | null;
  while ((codeMatch = codeBlockRegex.exec(trimmed)) !== null) {
    try {
      const parsed = JSON.parse(codeMatch[1]);
      if (typeof parsed === "object" && parsed !== null) {
        const ticketId = String(parsed.ticketId || fallbackTicketId);
        const summary = String(parsed.summary || "");
        const rawFiles = parsed.affectedFiles ?? parsed.affected_files ?? parsed.files ?? parsed.targetFiles;
        const affectedFiles = Array.isArray(rawFiles)
          ? rawFiles.map(String).map((f: string) => f.trim()).filter(Boolean)
          : [];
        const rawCmds = parsed.testCommands ?? parsed.test_commands ?? parsed.tests ?? parsed.commands;
        const testCommands = Array.isArray(rawCmds)
          ? rawCmds
              .map(String)
              .map((c: string) => c.trim())
              .filter(Boolean)
              .filter((c: string) => !isDevServerCommand(c))
          : [];
        const rawSteps = parsed.steps ?? parsed.tasks ?? parsed.plan;
        const steps = Array.isArray(rawSteps)
          ? rawSteps.map(String).map((s: string) => s.trim()).filter(Boolean)
          : [];
        const rationale = parsed.rationale ? String(parsed.rationale) : undefined;

        const hasPlanFields =
          parsed.affectedFiles !== undefined ||
          parsed.affected_files !== undefined ||
          parsed.files !== undefined ||
          parsed.testCommands !== undefined ||
          parsed.test_commands !== undefined;

        if (hasPlanFields) {
          if (affectedFiles.length === 0) {
            throw new PlanParseError("Implementation plan must specify at least one affected file in affectedFiles.");
          }
          if (testCommands.length === 0) {
            throw new PlanParseError("Implementation plan must specify at least one valid non-daemon test command in testCommands.");
          }
          return {
            ticketId,
            summary,
            affectedFiles,
            testCommands,
            steps,
            rationale,
            rawContent: trimmed,
          };
        }
      }
    } catch (e: any) {
      if (e instanceof PlanParseError) throw e;
    }
  }

  // Parse structured Markdown
  const summaryMatch = trimmed.match(/(?:^|\n)#+\s*Summary\s*([\s\S]*?)(?=(?:^|\n)#+|$)/i);
  const summary = summaryMatch ? summaryMatch[1].trim() : "";

  // Extract Affected Files from markdown (handles ##, ###, or **bold** headings)
  const filesMatch = trimmed.match(
    /(?:^|\n)(?:#+\s*|\*\*\s*)(?:affected\s+files|files\s+to\s+(?:modify|change)|target\s+files|files)\s*(?:\*\*)?:?\s*([\s\S]*?)(?=(?:^|\n)#+|$)/i
  );
  const affectedFiles: string[] = [];
  if (filesMatch) {
    const lines = filesMatch[1].split("\n");
    for (const line of lines) {
      const cleaned = line.replace(/^[-*+]\s*/, "").trim();
      const codeMatch = cleaned.match(/`([^`]+)`/);
      const filePath = codeMatch ? codeMatch[1].trim() : cleaned;
      if (filePath && !filePath.startsWith("#") && !filePath.endsWith(":")) {
        const cleanPath = filePath.split(/\s+/)[0];
        if (cleanPath && !affectedFiles.includes(cleanPath)) {
          affectedFiles.push(cleanPath);
        }
      }
    }
  }

  // Fallback: extract backticked code file paths if Affected Files section was absent/empty
  if (affectedFiles.length === 0) {
    const fileMatches = trimmed.matchAll(/`([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)`/g);
    for (const match of fileMatches) {
      const candidate = match[1].trim();
      if (
        (candidate.startsWith("src/") ||
          candidate.startsWith("test/") ||
          candidate.startsWith("lib/") ||
          candidate.endsWith(".ts") ||
          candidate.endsWith(".js") ||
          candidate.endsWith(".json")) &&
        !affectedFiles.includes(candidate)
      ) {
        affectedFiles.push(candidate);
      }
    }
  }

  // Extract Test Commands from markdown
  const testsMatch = trimmed.match(
    /(?:^|\n)(?:#+\s*|\*\*\s*)(?:test\s+commands|tests|verification\s+commands)\s*(?:\*\*)?:?\s*([\s\S]*?)(?=(?:^|\n)#+|$)/i
  );
  const testCommands: string[] = [];
  if (testsMatch) {
    const blockMatch = testsMatch[1].match(/```(?:bash|sh)?\s*([\s\S]*?)\s*```/);
    if (blockMatch) {
      const lines = blockMatch[1].split("\n");
      for (const line of lines) {
        const cmd = line.trim();
        if (cmd && !cmd.startsWith("#") && !isDevServerCommand(cmd)) {
          testCommands.push(cmd);
        }
      }
    } else {
      const lines = testsMatch[1].split("\n");
      for (const line of lines) {
        const cleaned = line.replace(/^[-*+]\s*/, "").replace(/^`|`$/g, "").trim();
        if (cleaned && !cleaned.startsWith("#") && !isDevServerCommand(cleaned)) {
          testCommands.push(cleaned);
        }
      }
    }
  }

  // Fallback: search for common test invocations if section was absent
  if (testCommands.length === 0) {
    const cmdMatches = trimmed.matchAll(/`(npm\s+test|pnpm\s+test|node\s+--[^`]+|pytest[^`]*)`/g);
    for (const match of cmdMatches) {
      const cmd = match[1].trim();
      if (!isDevServerCommand(cmd) && !testCommands.includes(cmd)) {
        testCommands.push(cmd);
      }
    }
  }

  // Extract Steps from markdown
  const stepsMatch = trimmed.match(
    /(?:^|\n)(?:#+\s*|\*\*\s*)(?:steps|implementation\s+steps|tasks)\s*(?:\*\*)?:?\s*([\s\S]*?)(?=(?:^|\n)#+|$)/i
  );
  const steps: string[] = [];
  if (stepsMatch) {
    const lines = stepsMatch[1].split("\n");
    for (const line of lines) {
      const cleaned = line.replace(/^\d+\.\s*/, "").replace(/^[-*+]\s*/, "").trim();
      if (cleaned) {
        steps.push(cleaned);
      }
    }
  }

  if (affectedFiles.length === 0) {
    throw new PlanParseError("Implementation plan must specify at least one affected file under Affected Files.");
  }
  if (testCommands.length === 0) {
    throw new PlanParseError("Implementation plan must specify at least one test command under Test Commands.");
  }

  return {
    ticketId: fallbackTicketId,
    summary,
    affectedFiles,
    testCommands,
    steps,
    rawContent: trimmed,
  };
}

/**
 * Parses a review verdict from JSON or markdown text.
 */
export function parseReviewVerdict(content: string): ReviewVerdict {
  const trimmed = content.trim();

  // Try all JSON blocks first
  const codeBlockRegex = /```(?:json)?\s*([\s\S]*?)\s*```/g;
  let codeMatch: RegExpExecArray | null;
  while ((codeMatch = codeBlockRegex.exec(trimmed)) !== null) {
    try {
      const parsed = JSON.parse(codeMatch[1]);
      if (typeof parsed === "object" && parsed !== null && parsed.verdict) {
        const rawVerdict = String(parsed.verdict).toLowerCase().trim();
        if (rawVerdict !== "approved" && rawVerdict !== "rejected") {
          throw new ReviewParseError(`Invalid review verdict: "${parsed.verdict}". Expected "approved" or "rejected".`);
        }
        let verdict: "approved" | "rejected" = rawVerdict;

        const summary = String(parsed.summary || "");
        const specCompliance = {
          passed: Boolean(parsed.specCompliance?.passed),
          details: String(parsed.specCompliance?.details || ""),
        };
        const standardsCompliance = {
          passed: Boolean(parsed.standardsCompliance?.passed),
          details: String(parsed.standardsCompliance?.details || ""),
        };
        if (!specCompliance.passed || !standardsCompliance.passed) {
          verdict = "rejected";
        }
        const issues: ReviewIssue[] = Array.isArray(parsed.issues)
          ? parsed.issues.map((i: any) => ({
              severity: i.severity === "blocker" || i.severity === "warning" || i.severity === "suggestion" ? i.severity : "warning",
              description: String(i.description || ""),
              file: i.file ? String(i.file) : undefined,
            }))
          : [];
        const remediation = parsed.remediation ? String(parsed.remediation) : undefined;

        return {
          verdict,
          summary,
          specCompliance,
          standardsCompliance,
          issues,
          remediation,
          rawContent: trimmed,
        };
      }
    } catch (e: any) {
      if (e instanceof ReviewParseError) throw e;
    }
  }

  // Parse markdown format - accommodate all common markdown styles:
  // **Verdict:** APPROVED, **Verdict**: APPROVED, **Verdict**: **APPROVED**,
  // # Verdict: APPROVED, Verdict: `APPROVED`, etc.
  const verdictMatch =
    trimmed.match(/(?:[*#_`\s]*(?:review\s+)?verdict[*#_`\s]*:?)\s*[*_`\s]*(APPROVED|REJECTED)[*_`\s]*/i) ||
    trimmed.match(/(?:^|\n)\s*(?:#+\s*)?(?:[*_`\s]*(?:review\s+)?verdict[*_`\s]*:?)?\s*[*_`\s]*(APPROVED|REJECTED)\b/i);

  if (!verdictMatch) {
    throw new ReviewParseError('Could not determine review verdict. Must clearly state "APPROVED" or "REJECTED".');
  }

  let verdict = verdictMatch[1].toLowerCase() as "approved" | "rejected";
  const summaryMatch = trimmed.match(/##\s*Summary\s*([\s\S]*?)(?=##|$)/i);
  const summary = summaryMatch ? summaryMatch[1].trim() : "";

  const specMatch = trimmed.match(/##\s*Spec Compliance\s*([\s\S]*?)(?=##|$)/i);
  const specPassed = specMatch ? /status:\s*passed/i.test(specMatch[1]) : verdict === "approved";
  const specDetailsMatch = specMatch ? specMatch[1].match(/details:\s*([\s\S]*?)$/im) : null;
  const specDetails = specDetailsMatch ? specDetailsMatch[1].trim() : specMatch ? specMatch[1].trim() : "";

  const standardsMatch = trimmed.match(/##\s*Standards Compliance\s*([\s\S]*?)(?=##|$)/i);
  const standardsPassed = standardsMatch ? /status:\s*passed/i.test(standardsMatch[1]) : verdict === "approved";
  const standardsDetailsMatch = standardsMatch ? standardsMatch[1].match(/details:\s*([\s\S]*?)$/im) : null;
  const standardsDetails = standardsDetailsMatch ? standardsDetailsMatch[1].trim() : standardsMatch ? standardsMatch[1].trim() : "";

  if (!specPassed || !standardsPassed) {
    verdict = "rejected";
  }

  const issuesMatch = trimmed.match(/##\s*Issues\s*([\s\S]*?)(?=##|$)/i);
  const issues: ReviewIssue[] = [];
  if (issuesMatch) {
    const lines = issuesMatch[1].split("\n");
    for (const line of lines) {
      const cleaned = line.replace(/^[-*+]\s*/, "").trim();
      if (cleaned && !/^(none|n\/a)\.?$/i.test(cleaned)) {
        const severity: "blocker" | "warning" | "suggestion" =
          /\b(blocker|critical|error)\b/i.test(cleaned)
            ? "blocker"
            : /\b(suggestion|nit)\b/i.test(cleaned)
            ? "suggestion"
            : "warning";
        issues.push({ severity, description: cleaned });
      }
    }
  }

  const remediationMatch = trimmed.match(/##\s*Remediation\s*([\s\S]*?)(?=##|$)/i);
  const remediation = remediationMatch ? remediationMatch[1].trim() : undefined;

  return {
    verdict,
    summary,
    specCompliance: {
      passed: specPassed,
      details: specDetails,
    },
    standardsCompliance: {
      passed: standardsPassed,
      details: standardsDetails,
    },
    issues,
    remediation,
    rawContent: trimmed,
  };
}
