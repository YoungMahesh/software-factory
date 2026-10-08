import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import { updateTicketFile } from "./ticket.ts";

test("updateTicketFile: updates ticket to resolved with commit, branch, and quality gate audit", () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "sf-ticket-test-"));
  const ticketPath = path.join(tmpDir, "01-test-ticket.md");

  const initialContent = `# 01: Test Ticket

**What to build:** Test description.

**Blocked by:** None

**Status:** ready-for-agent

- [ ] Item 1
- [ ] Item 2
`;

  fs.writeFileSync(ticketPath, initialContent, "utf-8");

  const updated = updateTicketFile({
    filePath: ticketPath,
    status: "resolved",
    branch: "factory/my-feature",
    commitSha: "abc1234567890",
    auditSummary: "### Verification: PASSED\n### Review: APPROVED",
  });

  const fileOnDisk = fs.readFileSync(ticketPath, "utf-8");
  assert.equal(updated, fileOnDisk);

  // Status must be resolved
  assert.match(fileOnDisk, /\*{0,2}Status(?::\*{0,2}|\*{0,2}:)\s*resolved/i);
  // Branch must be recorded
  assert.match(fileOnDisk, /\*{0,2}Branch(?::\*{0,2}|\*{0,2}:)\s*factory\/my-feature/i);
  // Commit must be recorded
  assert.match(fileOnDisk, /\*{0,2}Commit(?::\*{0,2}|\*{0,2}:)\s*abc1234567890/i);
  // Audit summary included
  assert.ok(fileOnDisk.includes("### Verification: PASSED"));
  assert.ok(fileOnDisk.includes("### Review: APPROVED"));

  fs.rmSync(tmpDir, { recursive: true, force: true });
});

test("updateTicketFile: updates ticket to ready-for-human with failure diagnostics appended under Comments", () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "sf-ticket-test-"));
  const ticketPath = path.join(tmpDir, "02-failing-ticket.md");

  const initialContent = `# 02: Failing Ticket

**What to build:** Something broken.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Item 1
`;

  fs.writeFileSync(ticketPath, initialContent, "utf-8");

  const updated = updateTicketFile({
    filePath: ticketPath,
    status: "ready-for-human",
    branch: "factory/my-feature",
    failureDiagnostics: "Deterministic verification failed after 2 retries:\nError: test failed on line 42",
  });

  const fileOnDisk = fs.readFileSync(ticketPath, "utf-8");
  assert.equal(updated, fileOnDisk);

  // Status must be ready-for-human
  assert.match(fileOnDisk, /\*{0,2}Status(?::\*{0,2}|\*{0,2}:)\s*ready-for-human/i);
  // Diagnostics must be present
  assert.ok(fileOnDisk.includes("## Comments"));
  assert.ok(fileOnDisk.includes("Deterministic verification failed after 2 retries"));

  fs.rmSync(tmpDir, { recursive: true, force: true });
});

test("updateTicketFile: preserves existing Comments section when appending", () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "sf-ticket-test-"));
  const ticketPath = path.join(tmpDir, "03-existing-comments.md");

  const initialContent = `# 03: Existing Comments

**Status:** open

## Comments

Initial human comment.
`;

  fs.writeFileSync(ticketPath, initialContent, "utf-8");

  updateTicketFile({
    filePath: ticketPath,
    status: "resolved",
    auditSummary: "Quality gate passed cleanly.",
  });

  const fileOnDisk = fs.readFileSync(ticketPath, "utf-8");
  assert.ok(fileOnDisk.includes("Initial human comment."));
  assert.ok(fileOnDisk.includes("Quality gate passed cleanly."));
  assert.match(fileOnDisk, /\*{0,2}Status(?::\*{0,2}|\*{0,2}:)\s*resolved/i);

  fs.rmSync(tmpDir, { recursive: true, force: true });
});
