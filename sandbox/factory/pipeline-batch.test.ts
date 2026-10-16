import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import { execSync } from "node:child_process";
import { runAssemblyLinePipeline } from "./pipeline.ts";
import { PreflightError } from "./preflight.ts";
import { type ImplementationPlan, type ReviewVerdict } from "./harness.ts";
import { GitHubClient } from "./github.ts";
import { GitHubIssueTracker } from "./tracker/github-tracker.ts";
import {
  parseTelemetryEnvelope,
  setGlobalTelemetryStream,
  type TelemetryEnvelope,
  type DeliveryGateEventData,
} from "./events.ts";
import {
  captureContainerOutput,
  setupRepoWithPrereqs,
  addTicket,
  mockPlan,
  mockPassingReview,
} from "./pipeline-test-helpers.ts";

test("runAssemblyLinePipeline: throws PreflightError if repository prerequisites are missing", async () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "sf-pipeline-bad-"));
  execSync("git init -b main", { cwd: tmpDir, stdio: "ignore" });
  execSync('git config user.name "Test"', { cwd: tmpDir, stdio: "ignore" });
  execSync('git config user.email "test@example.com"', { cwd: tmpDir, stdio: "ignore" });
  execSync("git commit --allow-empty -m 'initial commit'", { cwd: tmpDir, stdio: "ignore" });

  try {
    await assert.rejects(
      async () => {
        await runAssemblyLinePipeline({
          workspaceDir: tmpDir,
          featureSlug: "bad-feature",
          push: false,
        });
      },
      (err: any) => {
        assert.ok(err instanceof PreflightError);
        assert.ok(err.errors.length > 0);
        return true;
      }
    );
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

test("runAssemblyLinePipeline: targeted single-ticket mode runs only requested ticket", async () => {
  const repoDir = setupRepoWithPrereqs("single-ticket-feature");

  try {
    addTicket(repoDir, "single-ticket-feature", "01", "Ticket One");
    addTicket(repoDir, "single-ticket-feature", "02", "Ticket Two", "01");

    const executedTicketIds: string[] = [];

    const result = await runAssemblyLinePipeline({
      workspaceDir: repoDir,
      featureSlug: "single-ticket-feature",
      issueId: "01",
      push: false,
      plannerRunner: async ({ ticket }) => {
        const id = typeof ticket === "string" ? ticket : ticket.id;
        executedTicketIds.push(id);
        return { plan: mockPlan, messages: [] };
      },
      coderRunner: async () => {
        fs.writeFileSync(path.join(repoDir, "output.txt"), "ticket 1 done", "utf-8");
        return { summary: "Implemented", messages: [] };
      },
      verifierRunner: async () => ({
        passed: true,
        totalCommands: 1,
        passedCommands: 1,
        failedCommands: 0,
        results: [],
        summary: "PASSED",
        durationMs: 10,
      }),
      reviewerRunner: async () => ({ verdict: mockPassingReview, messages: [] }),
    });

    assert.equal(result.executedTickets.length, 1);
    assert.equal(result.executedTickets[0].ticketId, "01");
    assert.equal(result.executedTickets[0].status, "resolved");
    assert.deepEqual(executedTicketIds, ["01"]);
    assert.equal(result.branch, "factory/single-ticket-feature");
    assert.equal(result.haltedOnError, false);
  } finally {
    fs.rmSync(repoDir, { recursive: true, force: true });
  }
});

test("runAssemblyLinePipeline: Autonomous Feature Batch sequentially resolves frontier tickets", async () => {
  const repoDir = setupRepoWithPrereqs("batch-feature");

  try {
    addTicket(repoDir, "batch-feature", "01", "Ticket One");
    addTicket(repoDir, "batch-feature", "02", "Ticket Two", "01");

    const executedOrder: string[] = [];

    const result = await runAssemblyLinePipeline({
      workspaceDir: repoDir,
      featureSlug: "batch-feature",
      push: false,
      plannerRunner: async ({ ticket }) => {
        const id = typeof ticket === "string" ? ticket : ticket.id;
        executedOrder.push(id);
        return { plan: mockPlan, messages: [] };
      },
      coderRunner: async ({ ticket }) => {
        const id = typeof ticket === "string" ? ticket : ticket.id;
        fs.writeFileSync(path.join(repoDir, `file-${id}.txt`), `done ${id}`, "utf-8");
        return { summary: "Done", messages: [] };
      },
      verifierRunner: async () => ({
        passed: true,
        totalCommands: 1,
        passedCommands: 1,
        failedCommands: 0,
        results: [],
        summary: "PASSED",
        durationMs: 10,
      }),
      reviewerRunner: async () => ({ verdict: mockPassingReview, messages: [] }),
    });

    assert.equal(result.executedTickets.length, 2);
    assert.deepEqual(executedOrder, ["01", "02"]);
    assert.equal(result.allResolved, true);
    assert.equal(result.haltedOnError, false);

    // Both tickets should be resolved on disk
    const t1 = fs.readFileSync(path.join(repoDir, ".scratch", "batch-feature", "issues", "01-ticket-one.md"), "utf-8");
    const t2 = fs.readFileSync(path.join(repoDir, ".scratch", "batch-feature", "issues", "02-ticket-two.md"), "utf-8");
    assert.match(t1, /\*{0,2}Status(?::\*{0,2}|\*{0,2}:)\s*resolved/i);
    assert.match(t2, /\*{0,2}Status(?::\*{0,2}|\*{0,2}:)\s*resolved/i);
  } finally {
    fs.rmSync(repoDir, { recursive: true, force: true });
  }
});

test("runAssemblyLinePipeline: Autonomous Feature Batch halts immediately (fail-fast) when ticket fails and marks ready-for-human", async () => {
  const repoDir = setupRepoWithPrereqs("fail-fast-feature");

  try {
    addTicket(repoDir, "fail-fast-feature", "01", "Broken Ticket");
    addTicket(repoDir, "fail-fast-feature", "02", "Dependent Ticket", "01");

    const executedOrder: string[] = [];

    const result = await runAssemblyLinePipeline({
      workspaceDir: repoDir,
      featureSlug: "fail-fast-feature",
      maxRetries: 2,
      push: false,
      plannerRunner: async ({ ticket }) => {
        const id = typeof ticket === "string" ? ticket : ticket.id;
        executedOrder.push(id);
        return { plan: mockPlan, messages: [] };
      },
      coderRunner: async () => {
        fs.writeFileSync(path.join(repoDir, "broken.txt"), "failed code", "utf-8");
        return { summary: "Tried to fix", messages: [] };
      },
      verifierRunner: async () => ({
        passed: false,
        totalCommands: 1,
        passedCommands: 0,
        failedCommands: 1,
        results: [],
        summary: "SyntaxError: tests failed",
        durationMs: 10,
      }),
      reviewerRunner: async () => ({ verdict: mockPassingReview, messages: [] }),
    });

    // Batch halted immediately on ticket 01 failure!
    assert.equal(result.haltedOnError, true);
    assert.equal(result.allResolved, false);
    assert.deepEqual(executedOrder, ["01"]); // Ticket 02 was never run!
    assert.equal(result.executedTickets.length, 1);
    assert.equal(result.executedTickets[0].status, "ready-for-human");

    // Ticket 01 marked ready-for-human on disk
    const t1 = fs.readFileSync(path.join(repoDir, ".scratch", "fail-fast-feature", "issues", "01-broken-ticket.md"), "utf-8");
    assert.match(t1, /\*{0,2}Status(?::\*{0,2}|\*{0,2}:)\s*ready-for-human/i);

    // Ticket 02 remains ready-for-agent
    const t2 = fs.readFileSync(path.join(repoDir, ".scratch", "fail-fast-feature", "issues", "02-dependent-ticket.md"), "utf-8");
    assert.match(t2, /\*{0,2}Status(?::\*{0,2}|\*{0,2}:)\s*ready-for-agent/i);
  } finally {
    fs.rmSync(repoDir, { recursive: true, force: true });
  }
});
