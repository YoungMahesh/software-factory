import test from "node:test";
import assert from "node:assert/strict";

import {
  parseImplementationPlan,
  parseReviewVerdict,
  PlanParseError,
  ReviewParseError,
  type ImplementationPlan,
  type ReviewVerdict,
} from "./harness.ts";

test("parseImplementationPlan: parses valid JSON block with affectedFiles and testCommands", () => {
  const jsonContent = `
Here is my plan:
\`\`\`json
{
  "ticketId": "03",
  "summary": "Configure OpenCode Go provider and agents",
  "affectedFiles": [
    "sandbox/factory/provider.ts",
    "sandbox/factory/tools.ts",
    "sandbox/factory/harness.ts"
  ],
  "testCommands": [
    "pnpm test",
    "pnpm typecheck"
  ],
  "steps": [
    "1. Implement provider",
    "2. Implement tools",
    "3. Implement harness"
  ],
  "rationale": "Enforces least-privilege role boundaries"
}
\`\`\`
Hope this helps!
`;

  const plan = parseImplementationPlan(jsonContent, "03");
  assert.equal(plan.ticketId, "03");
  assert.equal(plan.summary, "Configure OpenCode Go provider and agents");
  assert.deepEqual(plan.affectedFiles, [
    "sandbox/factory/provider.ts",
    "sandbox/factory/tools.ts",
    "sandbox/factory/harness.ts",
  ]);
  assert.deepEqual(plan.testCommands, ["pnpm test", "pnpm typecheck"]);
  assert.equal(plan.steps.length, 3);
  assert.equal(plan.rationale, "Enforces least-privilege role boundaries");
});

test("parseImplementationPlan: parses structured markdown sections", () => {
  const markdownContent = `
# Implementation Plan for Ticket 03

## Summary
Add Pi Agent harness and OpenCode Go models.

## Affected Files
- \`sandbox/factory/provider.ts\`
- \`sandbox/factory/tools.ts\`

## Test Commands
\`\`\`bash
pnpm test:verifier
pnpm typecheck
\`\`\`

## Steps
1. Create provider module.
2. Create tools module.
`;

  const plan = parseImplementationPlan(markdownContent, "03");
  assert.equal(plan.ticketId, "03");
  assert.ok(plan.summary.includes("Add Pi Agent harness"));
  assert.deepEqual(plan.affectedFiles, [
    "sandbox/factory/provider.ts",
    "sandbox/factory/tools.ts",
  ]);
  assert.deepEqual(plan.testCommands, [
    "pnpm test:verifier",
    "pnpm typecheck",
  ]);
  assert.equal(plan.steps.length, 2);
});

test("parseImplementationPlan: throws PlanParseError when affectedFiles are missing", () => {
  const badContent = `
\`\`\`json
{
  "ticketId": "03",
  "summary": "Plan without files",
  "affectedFiles": [],
  "testCommands": ["pnpm test"]
}
\`\`\`
`;

  assert.throws(
    () => parseImplementationPlan(badContent, "03"),
    (err) => err instanceof PlanParseError && /affected/i.test(err.message)
  );
});

test("parseImplementationPlan: throws PlanParseError when testCommands are missing", () => {
  const badContent = `
\`\`\`json
{
  "ticketId": "03",
  "summary": "Plan without tests",
  "affectedFiles": ["sandbox/factory/test.ts"],
  "testCommands": []
}
\`\`\`
`;

  assert.throws(
    () => parseImplementationPlan(badContent, "03"),
    (err) => err instanceof PlanParseError && /test command/i.test(err.message)
  );
});

test("parseReviewVerdict: parses valid JSON review verdict with APPROVED", () => {
  const jsonContent = `
\`\`\`json
{
  "verdict": "approved",
  "summary": "Implementation satisfies all ticket acceptance criteria.",
  "specCompliance": {
    "passed": true,
    "details": "All requirements from ticket 03 are met."
  },
  "standardsCompliance": {
    "passed": true,
    "details": "TypeScript strict mode and repo conventions followed."
  },
  "issues": []
}
\`\`\`
`;

  const verdict = parseReviewVerdict(jsonContent);
  assert.equal(verdict.verdict, "approved");
  assert.equal(verdict.specCompliance.passed, true);
  assert.equal(verdict.standardsCompliance.passed, true);
  assert.equal(verdict.issues.length, 0);
});

test("parseReviewVerdict: parses valid JSON review verdict with REJECTED and issues", () => {
  const jsonContent = `
\`\`\`json
{
  "verdict": "rejected",
  "summary": "Missing least-privilege enforcement on Reviewer agent.",
  "specCompliance": {
    "passed": false,
    "details": "Reviewer had write tools enabled."
  },
  "standardsCompliance": {
    "passed": true,
    "details": "Code style looks good."
  },
  "issues": [
    {
      "severity": "blocker",
      "description": "Reviewer must be strictly read-only per ADR 0025.",
      "file": "sandbox/factory/tools.ts"
    }
  ],
  "remediation": "Remove write and edit tools from Reviewer toolset."
}
\`\`\`
`;

  const verdict = parseReviewVerdict(jsonContent);
  assert.equal(verdict.verdict, "rejected");
  assert.equal(verdict.specCompliance.passed, false);
  assert.equal(verdict.issues.length, 1);
  assert.equal(verdict.issues[0].severity, "blocker");
  assert.equal(verdict.remediation, "Remove write and edit tools from Reviewer toolset.");
});

test("parseReviewVerdict: parses markdown review verdict", () => {
  const markdownContent = `
# Review Verdict

**Verdict:** APPROVED

## Summary
The changes match the specification and adhere to domain rules.

## Spec Compliance
Status: Passed
Details: All checkboxes in issue 03 are satisfied.

## Standards Compliance
Status: Passed
Details: Follows single-context layout and least-privilege principles.

## Issues
None.
`;

  const verdict = parseReviewVerdict(markdownContent);
  assert.equal(verdict.verdict, "approved");
  assert.equal(verdict.specCompliance.passed, true);
  assert.equal(verdict.standardsCompliance.passed, true);
});

test("parseReviewVerdict: parses markdown review verdict with issues and remediation", () => {
  const markdownContent = `
# Review Verdict

**Verdict:** REJECTED

## Summary
Found critical issues.

## Spec Compliance
Status: Failed
Details: Missing tool restrictions.

## Standards Compliance
Status: Failed
Details: Violates least-privilege.

## Issues
- Blocker: Reviewer has write tool enabled.
- Suggestion: Consider extracting helper.

## Remediation
Remove write tool from reviewer.
`;

  const verdict = parseReviewVerdict(markdownContent);
  assert.equal(verdict.verdict, "rejected");
  assert.equal(verdict.specCompliance.passed, false);
  assert.equal(verdict.standardsCompliance.passed, false);
  assert.equal(verdict.issues.length, 2);
  assert.equal(verdict.issues[0].severity, "blocker");
  assert.equal(verdict.issues[1].severity, "suggestion");
  assert.equal(verdict.remediation, "Remove write tool from reviewer.");
});

test("parseReviewVerdict: parses diverse markdown formatting styles", () => {
  const variations = [
    "**Verdict**: APPROVED\n\n## Summary\nLooks great.",
    "**Verdict**: **APPROVED**\n\n## Summary\nLooks great.",
    "**Review Verdict**: APPROVED\n\n## Summary\nLooks great.",
    "### Verdict: APPROVED\n\n## Summary\nLooks great.",
    "Verdict: `APPROVED`\n\n## Summary\nLooks great.",
  ];

  for (const text of variations) {
    const verdict = parseReviewVerdict(text);
    assert.equal(verdict.verdict, "approved");
  }
});

test("parseReviewVerdict: throws ReviewParseError when verdict cannot be determined", () => {
  const badContent = `
I reviewed the code, but I am not sure what verdict to give. It looks okay maybe.
`;

  assert.throws(
    () => parseReviewVerdict(badContent),
    (err) => err instanceof ReviewParseError && /verdict/i.test(err.message)
  );
});

test("parseImplementationPlan: filters out dev server commands from testCommands", () => {
  const jsonContent = `
\`\`\`json
{
  "ticketId": "01",
  "summary": "Build feature",
  "affectedFiles": ["src/App.tsx"],
  "testCommands": ["pnpm test", "pnpm dev", "vite dev"],
  "steps": ["1. Write code"]
}
\`\`\`
`;
  const plan = parseImplementationPlan(jsonContent, "01");
  assert.deepEqual(plan.testCommands, ["pnpm test"]);
});

test("parseImplementationPlan: throws PlanParseError if testCommands only contains dev server commands", () => {
  const jsonContent = `
\`\`\`json
{
  "ticketId": "01",
  "summary": "Build feature",
  "affectedFiles": ["src/App.tsx"],
  "testCommands": ["pnpm dev", "npm run dev"],
  "steps": ["1. Write code"]
}
\`\`\`
`;
  assert.throws(
    () => parseImplementationPlan(jsonContent, "01"),
    PlanParseError
  );
});


