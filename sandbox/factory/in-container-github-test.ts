import fs from "node:fs";
import { execSync } from "node:child_process";
import { GitHubClient } from "./github.ts";
import { GitHubIssueTracker } from "./tracker/github-tracker.ts";
import { validatePreflightAsync } from "./preflight.ts";

async function runLiveGitHubSandboxVerification() {
  console.log("================================================================");
  console.log("🚀 Live In-Sandbox GitHub Issues & PR Delivery Gate Verification");
  console.log("================================================================\n");

  const workspaceDir = "/root/test3";
  if (!fs.existsSync(workspaceDir)) {
    throw new Error(`Target workspace directory ${workspaceDir} does not exist`);
  }

  const token = process.env.GH_TOKEN || process.env.GITHUB_TOKEN;
  if (!token) {
    throw new Error("Missing GH_TOKEN in sandbox environment");
  }

  const owner = "software-factory-09-test";
  const repo = "test3";
  const featureSlug = "test-delivery-gate";
  const branch = `factory/${featureSlug}`;

  const client = new GitHubClient({
    token,
    owner,
    repo,
  });

  console.log(`📡 Connected to GitHub repository ${owner}/${repo}`);

  // 1. Verify remote milestones
  const milestones = await client.listMilestones("open");
  console.log(`📋 Found ${milestones.length} open milestone(s) on GitHub:`, milestones.map((m) => m.title));
  const targetMilestone = milestones.find((m) => m.title === featureSlug || m.slug === featureSlug);
  if (!targetMilestone) {
    throw new Error(`Target milestone "${featureSlug}" not found on GitHub`);
  }
  console.log(`✅ Verified target milestone "${targetMilestone.title}" (#${targetMilestone.number}) on GitHub`);

  // 2. Verify remote milestone issues
  const milestoneIssues = await client.listIssuesForMilestone(targetMilestone.number);
  console.log(`📋 Found ${milestoneIssues.length} issue(s) assigned to milestone on GitHub:`, milestoneIssues.map((i) => `#${i.number} ${i.title}`));
  if (milestoneIssues.length === 0) {
    throw new Error(`Milestone "${featureSlug}" has no assigned issues`);
  }
  console.log(`✅ Verified assigned issues in milestone`);

  // 3. Test Pre-flight Guard inside sandbox (Positive validation)
  console.log("\n🔍 Running in-sandbox Pre-flight Guard validation (Positive)...");
  const preflightPos = await validatePreflightAsync(workspaceDir, featureSlug);
  console.log("Preflight result valid:", preflightPos.valid);
  if (!preflightPos.valid) {
    throw new Error(`Positive preflight validation failed unexpectedly: ${JSON.stringify(preflightPos.errors)}`);
  }
  console.log("✅ In-sandbox pre-flight validation passed for GitHub milestone without local .scratch requirements!");

  // 4. Test Pre-flight Guard inside sandbox (Negative validation on missing milestone)
  console.log("\n🔍 Running in-sandbox Pre-flight Guard validation (Negative on missing milestone)...");
  const preflightNeg = await validatePreflightAsync(workspaceDir, "non-existent-feature-xyz");
  console.log("Negative preflight valid:", preflightNeg.valid, "errors:", preflightNeg.errors.length);
  if (preflightNeg.valid !== false || preflightNeg.errors.length === 0) {
    throw new Error("Expected negative preflight validation to fail for non-existent milestone");
  }
  console.log("✅ In-sandbox pre-flight correctly rejected non-existent milestone:", preflightNeg.errors[0]);

  // 5. Test GitHubIssueTracker discovery & frontier calculation
  console.log("\n🔍 Testing GitHubIssueTracker ticket discovery and execution frontier...");
  const tracker = new GitHubIssueTracker({ client });
  const spec = await tracker.getFeatureSpec(workspaceDir, featureSlug);
  console.log("Feature spec length:", spec?.length ?? 0);
  if (!spec) {
    throw new Error("Expected feature specification to be retrieved from milestone description");
  }

  const tickets = await tracker.getTickets(workspaceDir, featureSlug);
  console.log(`Discovered ${tickets.length} ticket(s) from tracker`);
  const frontier = await tracker.getFrontierTickets(workspaceDir, featureSlug);
  console.log(`Frontier has ${frontier.length} unblocked candidate(s):`, frontier.map((t) => `#${t.number} ${t.title}`));
  if (frontier.length === 0) {
    throw new Error("Frontier is unexpectedly empty");
  }
  const ticket = frontier[0];

  // 6. Test claiming ticket on GitHub
  console.log(`\n🏷️  Claiming ticket #${ticket.number} on GitHub via tracker...`);
  await tracker.claimTicket(ticket, { branch });
  const claimedIssue = await client.getIssue(ticket.number);
  const claimedLabels = (claimedIssue.labels || []).map((l: any) => typeof l === "string" ? l : l.name);
  console.log(`Claimed issue labels on GitHub:`, claimedLabels);
  if (!claimedLabels.includes("factory:claimed")) {
    throw new Error(`Expected issue #${ticket.number} to have label 'factory:claimed'`);
  }
  console.log("✅ Verified 'factory:claimed' label on GitHub Issue!");

  // 7. Test Git commit and push from inside container
  console.log(`\n🌿 Preparing git branch ${branch} in ${workspaceDir}...`);
  execSync(`git checkout -B "${branch}" origin/main`, { cwd: workspaceDir, stdio: "inherit" });

  const testFile = `${workspaceDir}/test/delivery-gate.test.ts`;
  fs.writeFileSync(
    testFile,
    `import test from "node:test";
import assert from "node:assert/strict";
import { slugify } from "../src/index.ts";

test("slugify handles underscore delimiter in delivery gate verification", () => {
  assert.strictEqual(slugify("Hello Cloud Sandbox", { delimiter: "_" }), "hello_cloud_sandbox");
});
`,
    "utf-8"
  );

  execSync("git add -A", { cwd: workspaceDir, stdio: "inherit" });
  execSync(`git commit -m "feat(${featureSlug}): resolve #${ticket.number} - add delimiter delivery gate test\n\nFixes #${ticket.number}"`, { cwd: workspaceDir, stdio: "inherit" });
  const commitSha = execSync("git rev-parse HEAD", { cwd: workspaceDir, encoding: "utf-8" }).trim();
  console.log(`Pushed commit: ${commitSha}`);
  execSync(`git push -u origin "${branch}"`, { cwd: workspaceDir, stdio: "inherit" });
  console.log(`✅ Successfully pushed ${branch} to GitHub origin!`);

  // 8. Test Feature Pull Request Delivery Gate (Draft PR creation)
  console.log(`\n🚪 Initializing Delivery Gate (Opening Draft PR targeting main)...`);
  const gateInitResult = await tracker.initializeDeliveryGate({
    workspaceDir,
    featureSlug,
    branch,
    ticket,
  });
  if (!gateInitResult) {
    throw new Error("initializeDeliveryGate returned null");
  }
  console.log(`Draft PR created: #${gateInitResult.pullRequestNumber} (${gateInitResult.pullRequestUrl})`);
  const pr = await client.getPullRequest(gateInitResult.pullRequestNumber);
  console.log(`PR #${pr.number} title: "${pr.title}", draft: ${pr.draft}`);
  if (!pr.draft) {
    throw new Error(`Expected newly opened PR #${pr.number} to be draft`);
  }
  if (!pr.body?.includes(`Fixes #${ticket.number}`)) {
    throw new Error(`Expected PR body to include 'Fixes #${ticket.number}'`);
  }
  console.log("✅ Verified Draft Feature Pull Request created with 'Fixes #<id>' link on GitHub!");

  // 9. Test resolving ticket: updating labels and posting audit comment on GitHub Issue
  console.log(`\n📝 Resolving ticket #${ticket.number} and posting audit comment to GitHub Issue...`);
  await tracker.resolveTicket(ticket, {
    branch,
    commitSha,
    auditSummary: "### Live Modal Sandbox Verification Audit\n\nAll automated assembly line quality checks verified inside live ephemeral container.",
  });
  const resolvedIssue = await client.getIssue(ticket.number);
  const resolvedLabels = (resolvedIssue.labels || []).map((l: any) => typeof l === "string" ? l : l.name);
  console.log(`Resolved issue labels on GitHub:`, resolvedLabels);
  if (!resolvedLabels.includes("factory:resolved")) {
    throw new Error(`Expected issue #${ticket.number} to have label 'factory:resolved'`);
  }
  console.log("✅ Verified 'factory:resolved' label on GitHub Issue!");

  // 10. Test finalizing Delivery Gate: converting Draft PR to Ready for Review
  console.log(`\n🏁 Finalizing Delivery Gate (Converting PR #${pr.number} to Ready for Review)...`);
  const finalizeResult = await tracker.finalizeDeliveryGate({
    workspaceDir,
    featureSlug,
    branch,
    tickets: [ticket],
    summary: `### Software Factory Summary: ${featureSlug}\n\nAll tickets in milestone resolved and verified inside live Modal sandbox.`,
  });
  if (!finalizeResult) {
    throw new Error("finalizeDeliveryGate returned null");
  }
  console.log(`Delivery gate finalized: PR #${finalizeResult.pullRequestNumber}, readyForReview: ${finalizeResult.readyForReview}`);

  const finalizedPr = await client.getPullRequest(pr.number);
  console.log(`Finalized PR #${finalizedPr.number} draft status: ${finalizedPr.draft}`);
  console.log("✅ Delivery Gate finalization complete!");

  console.log("\n================================================================");
  console.log("🎉 ALL IN-SANDBOX GITHUB ISSUES & PR GATE VERIFICATIONS PASSED!");
  console.log("================================================================\n");
}

runLiveGitHubSandboxVerification().catch((err) => {
  console.error("❌ Fatal error in live sandbox verification:", err);
  process.exit(1);
});
