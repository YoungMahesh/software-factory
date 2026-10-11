import test from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { LocalScratchTracker } from "./local-tracker.ts";

function createTempRepo(): string {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "local-tracker-test-"));
  fs.writeFileSync(path.join(tmpDir, "CONTEXT.md"), "# Domain Context\n");
  const adrDir = path.join(tmpDir, "docs", "adr");
  fs.mkdirSync(adrDir, { recursive: true });
  fs.writeFileSync(
    path.join(adrDir, "0001-init.md"),
    "# 0001: Architecture\n\n**Status**: Accepted\n"
  );
  const docsAgents = path.join(tmpDir, "docs", "agents");
  fs.mkdirSync(docsAgents, { recursive: true });
  fs.writeFileSync(path.join(docsAgents, "issue-tracker.md"), "# Issue Tracker\n");

  const featureDir = path.join(tmpDir, ".scratch", "demo-feat");
  const issuesDir = path.join(featureDir, "issues");
  fs.mkdirSync(issuesDir, { recursive: true });
  fs.writeFileSync(path.join(featureDir, "spec.md"), "# Demo Spec\nThis is demo spec.\n");

  fs.writeFileSync(
    path.join(issuesDir, "01-first.md"),
    `# 01: First Ticket\n\n**Status:** ready-for-agent\n**Blocked by:** none\n\n- Task 1\n`
  );
  fs.writeFileSync(
    path.join(issuesDir, "02-second.md"),
    `# 02: Second Ticket\n\n**Status:** ready-for-agent\n**Blocked by:** 01\n\n- Task 2\n`
  );

  return tmpDir;
}

test("LocalScratchTracker: validates preflight and retrieves feature spec", async () => {
  const tmpRepo = createTempRepo();
  try {
    const tracker = new LocalScratchTracker();
    const result = await tracker.validatePreflight(tmpRepo, "demo-feat");
    assert.equal(result.valid, true);
    assert.equal(result.errors.length, 0);

    const spec = await tracker.getFeatureSpec(tmpRepo, "demo-feat");
    assert.ok(spec?.includes("This is demo spec."));
  } finally {
    fs.rmSync(tmpRepo, { recursive: true, force: true });
  }
});

test("LocalScratchTracker: returns tickets and computes frontier respecting blockers", async () => {
  const tmpRepo = createTempRepo();
  try {
    const tracker = new LocalScratchTracker();
    const tickets = await tracker.getTickets(tmpRepo, "demo-feat");
    assert.equal(tickets.length, 2);
    assert.equal(tickets[0].id, "01");
    assert.equal(tickets[1].id, "02");

    // Only ticket 01 is on frontier because 02 is blocked by 01
    const frontier = await tracker.getFrontierTickets(tmpRepo, "demo-feat");
    assert.equal(frontier.length, 1);
    assert.equal(frontier[0].id, "01");

    // Claim ticket 01
    await tracker.claimTicket(frontier[0], { branch: "factory/demo-feat" });
    assert.equal(frontier[0].status, "claimed");

    // After claim, frontier should be empty
    const frontierAfterClaim = await tracker.getFrontierTickets(tmpRepo, "demo-feat");
    assert.equal(frontierAfterClaim.length, 0);

    // Resolve ticket 01
    await tracker.resolveTicket(frontier[0], {
      branch: "factory/demo-feat",
      commitSha: "abc123456",
      auditSummary: "All tests pass",
    });
    assert.equal(frontier[0].status, "resolved");

    // Now ticket 02 should be unblocked and on frontier!
    const frontierAfterResolve = await tracker.getFrontierTickets(tmpRepo, "demo-feat");
    assert.equal(frontierAfterResolve.length, 1);
    assert.equal(frontierAfterResolve[0].id, "02");
  } finally {
    fs.rmSync(tmpRepo, { recursive: true, force: true });
  }
});
