import fs from "node:fs";
import path from "node:path";
import { execSync } from "node:child_process";

import { createOpenCodeGoProvider, getFactoryModel } from "./provider.ts";
import {
  validatePreflight,
  parseTickets,
  getNextFrontierTicket,
} from "./preflight.ts";
import {
  runPlannerAgent,
  runCoderAgent,
  runReviewerAgent,
} from "./harness.ts";
import { verifyWorkspace } from "./verifier.ts";

async function run() {
  console.log("================================================================");
  console.log("🚀 In-Container Assembly Line Verification on /root/test3");
  console.log("================================================================\n");

  const workspaceDir = "/root/test3";
  if (!fs.existsSync(workspaceDir)) {
    throw new Error(`Workspace directory ${workspaceDir} does not exist`);
  }

  // 1. Preflight
  console.log("🛡️  Running Pre-flight Guard on /root/test3...");
  const preflight = validatePreflight(workspaceDir, "slug-generator");
  if (!preflight.valid) {
    console.error("❌ Pre-flight failed:", preflight.errors);
    process.exit(1);
  }
  console.log("✅ Pre-flight Guard PASSED!");

  // 2. Ticket discovery
  const tickets = parseTickets(workspaceDir, "slug-generator");
  const ticket = getNextFrontierTicket(tickets);
  if (!ticket) {
    throw new Error("No unblocked frontier ticket found in /root/test3");
  }
  console.log(`📋 Found frontier Ticket ${ticket.id}: "${ticket.title}" (${ticket.status})`);

  const specPath = path.join(workspaceDir, ".scratch", "slug-generator", "spec.md");
  const contextPath = path.join(workspaceDir, "CONTEXT.md");
  const specContent = fs.readFileSync(specPath, "utf-8");
  const contextContent = fs.readFileSync(contextPath, "utf-8");

  // 3. Provider & Model
  console.log("🤖 Initializing OpenCode Go Provider with DeepSeek V4.1 Flash...");
  const provider = createOpenCodeGoProvider();
  const model = getFactoryModel("deepseek-v4.1-flash", provider);
  console.log(`✅ Model ready: ${model.id}`);

  // 4. Planner Agent
  console.log("\n🧠 [STAGE 1] Running Planner Agent...");
  const planStart = Date.now();
  const { plan } = await runPlannerAgent({
    workspaceDir,
    ticket,
    specContent,
    contextContent,
    provider,
    model,
  });
  console.log(`✅ Plan generated in ${Date.now() - planStart}ms!`);
  console.log(`Affected files: ${JSON.stringify(plan.affectedFiles)}`);
  console.log(`Test commands:  ${JSON.stringify(plan.testCommands)}`);

  // 5. Coder Agent
  console.log("\n💻 [STAGE 2] Running Coder Agent...");
  const coderStart = Date.now();
  const { messages: coderMessages } = await runCoderAgent({
    workspaceDir,
    ticket,
    plan,
    provider,
    model,
  });
  console.log(`✅ Coder Agent completed in ${Date.now() - coderStart}ms (${coderMessages.length} turns)`);

  const gitDiff = execSync("git diff", { cwd: workspaceDir, encoding: "utf-8" });
  console.log(`Git diff size: ${gitDiff.length} characters`);

  // 6. Deterministic Verifier
  console.log("\n⚖️  [STAGE 3] Running Deterministic Verifier...");
  const verifyResult = await verifyWorkspace({
    workspacePath: workspaceDir,
    streamToProcess: true,
  });
  console.log("\n" + verifyResult.summary);
  if (!verifyResult.passed) {
    throw new Error("Deterministic verification failed inside container!");
  }
  console.log("🎉 Deterministic verification PASSED!");

  // 7. Reviewer Agent
  console.log("\n🧐 [STAGE 4] Running Reviewer Agent...");
  const reviewerStart = Date.now();
  const { verdict } = await runReviewerAgent({
    workspaceDir,
    ticket,
    plan,
    diff: gitDiff,
    provider,
    model,
  });
  console.log(`✅ Reviewer completed in ${Date.now() - reviewerStart}ms! Verdict: ${verdict.verdict.toUpperCase()}`);
  console.log(`Spec Compliance:     ${verdict.specCompliance.passed ? "PASS" : "FAIL"}`);
  console.log(`Standards Compliance: ${verdict.standardsCompliance.passed ? "PASS" : "FAIL"}`);

  console.log("\n================================================================");
  console.log("🏁 IN-CONTAINER ASSEMBLY LINE TEST COMPLETED SUCCESSFULLY!");
  console.log("================================================================\n");
}

run().catch((err) => {
  console.error("❌ Fatal error in container verification:", err);
  process.exit(1);
});
