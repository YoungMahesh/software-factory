import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import { execSync } from "node:child_process";
import { type ImplementationPlan, type ReviewVerdict } from "./harness.ts";
import {
  parseTelemetryEnvelope,
  setGlobalTelemetryStream,
  type TelemetryEnvelope,
} from "./events.ts";

export async function captureContainerOutput<T>(
  fn: () => Promise<T>
): Promise<{ result: T; envelopes: TelemetryEnvelope[] }> {
  const rawChunks: string[] = [];
  const stream = {
    write: (chunk: string) => {
      rawChunks.push(chunk);
    },
  };

  setGlobalTelemetryStream(stream);
  try {
    const result = await fn();
    const allLines = rawChunks.join("").split("\n");
    const envelopes: TelemetryEnvelope[] = [];
    for (const line of allLines) {
      const parsed = parseTelemetryEnvelope(line);
      if (parsed) {
        envelopes.push(parsed);
      }
    }
    return { result, envelopes };
  } finally {
    setGlobalTelemetryStream(null);
  }
}

export function setupRepoWithPrereqs(featureSlug: string): string {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "sf-pipeline-test-"));
  execSync("git init -b main", { cwd: tmpDir, stdio: "ignore" });
  execSync('git config user.name "Pipeline Test"', { cwd: tmpDir, stdio: "ignore" });
  execSync('git config user.email "pipe@example.com"', { cwd: tmpDir, stdio: "ignore" });

  fs.writeFileSync(path.join(tmpDir, "README.md"), "# Pipeline Test\n", "utf-8");
  fs.writeFileSync(path.join(tmpDir, "CONTEXT.md"), "# Domain Context\n\nGlossary here.\n", "utf-8");
  fs.writeFileSync(path.join(tmpDir, "AGENTS.md"), "# Agent Instructions\n\n## Agent skills\n\nSkills.\n", "utf-8");
  const adrDir = path.join(tmpDir, "docs", "adr");
  fs.mkdirSync(adrDir, { recursive: true });
  fs.writeFileSync(
    path.join(adrDir, "0001-init.md"),
    "# 0001: Architecture\n\n**Status**: Accepted\n\nInitial architecture.\n",
    "utf-8"
  );

  const featureDir = path.join(tmpDir, ".scratch", featureSlug);
  const issuesDir = path.join(featureDir, "issues");
  fs.mkdirSync(issuesDir, { recursive: true });

  fs.writeFileSync(path.join(featureDir, "spec.md"), `# Spec: ${featureSlug}\n\nFeature spec.\n`, "utf-8");

  execSync("git add . && git commit -m 'initial repo with prerequisites'", {
    cwd: tmpDir,
    stdio: "ignore",
  });

  return tmpDir;
}

export function addTicket(repoDir: string, featureSlug: string, id: string, title: string, blockedBy: string = "None"): string {
  const ticketPath = path.join(repoDir, ".scratch", featureSlug, "issues", `${id}-${title.toLowerCase().replace(/\s+/g, "-")}.md`);
  const content = `# ${id}: ${title}

**What to build:** ${title}

**Blocked by:** ${blockedBy}

**Status:** ready-for-agent

- [ ] Task
`;
  fs.writeFileSync(ticketPath, content, "utf-8");
  execSync(`git add "${ticketPath}" && git commit -m "add ticket ${id}"`, { cwd: repoDir, stdio: "ignore" });
  return ticketPath;
}

export const mockPlan: ImplementationPlan = {
  ticketId: "mock",
  summary: "Mock plan",
  affectedFiles: ["app.ts"],
  testCommands: ["echo 'test passed'"],
  steps: ["step 1"],
  rawContent: "```json\n{}\n```",
};

export const mockPassingReview: ReviewVerdict = {
  verdict: "approved",
  summary: "Clean implementation",
  specCompliance: { passed: true, details: "Pass" },
  standardsCompliance: { passed: true, details: "Pass" },
  issues: [],
  rawContent: "{}",
};
