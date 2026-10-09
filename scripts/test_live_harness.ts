import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { execSync } from "node:child_process";

import { createOpenCodeGoProvider, getFactoryModel } from "../sandbox/factory/provider.ts";
import {
  validatePreflight,
  parseTickets,
  getNextFrontierTicket,
} from "../sandbox/factory/preflight.ts";
import {
  runPlannerAgent,
  runCoderAgent,
  runReviewerAgent,
} from "../sandbox/factory/harness.ts";
import { verifyWorkspace } from "../sandbox/factory/verifier.ts";

function decryptEnv(filePath: string): Record<string, string> {
  const output = execSync(`sops -d "${filePath}"`, { encoding: "utf-8" });
  const result: Record<string, string> = {};
  for (const line of output.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const match = trimmed.match(/^([A-Za-z0-9_]+)=(.*)$/);
    if (match) {
      result[match[1]] = match[2].trim().replace(/^['"]|['"]$/g, "");
    }
  }
  return result;
}

async function main() {
  console.log("================================================================");
  console.log("🚀 Starting Phase 1 Live Integration Test: Pi Agent Harness on test3");
  console.log("================================================================\n");

  const rootDir = path.resolve(import.meta.dirname, "..");
  const test3TokenPath = path.join(rootDir, "secrets_org", "software-factory-09-test", "token");
  const opencodeEnvPath = path.join(rootDir, "secrets", "opencode.env");

  if (!fs.existsSync(test3TokenPath)) {
    throw new Error(`Missing organization token at ${test3TokenPath}`);
  }
  if (!fs.existsSync(opencodeEnvPath)) {
    throw new Error(`Missing OpenCode credentials at ${opencodeEnvPath}`);
  }

  console.log("🔑 Decrypting credentials with SOPS...");
  const ghToken = execSync(`sops -d "${test3TokenPath}"`, { encoding: "utf-8" }).trim();
  const opencodeEnv = decryptEnv(opencodeEnvPath);

  const ghRepo = "software-factory-09-test/test3";
  const opencodeApiKey = opencodeEnv.OPENCODE_GO_API_KEY;

  if (!ghRepo || !ghToken) {
    throw new Error("Failed to extract GH_REPO or GH_TOKEN from test3 credentials");
  }
  if (!opencodeApiKey) {
    throw new Error("Failed to extract OPENCODE_GO_API_KEY from opencode.env");
  }

  console.log(`✅ Target repository: ${ghRepo}`);
  console.log(`✅ OpenCode API Key resolved (${opencodeApiKey.slice(0, 10)}...)`);

  // Setup Provider and Model
  console.log("\n🤖 Initializing OpenCode Go Provider with DeepSeek V4.1 Flash flagship model...");
  const provider = createOpenCodeGoProvider({ apiKey: opencodeApiKey });
  const model = getFactoryModel("deepseek-v4.1-flash", provider);
  console.log(`✅ Model initialized: ${model.id} (${model.name})`);

  // Clone test3 into temp workspace
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "sf-live-test3-"));
  console.log(`\n📂 Created temporary workspace: ${tempDir}`);

  try {
    console.log("📥 Cloning remote test3 workspace...");
    const cloneUrl = `https://x-access-token:${ghToken}@github.com/${ghRepo}.git`;
    execSync(`git clone --depth 1 "${cloneUrl}" "${tempDir}"`, {
      stdio: ["ignore", "pipe", "pipe"],
    });

    execSync(`git config user.name "Software Factory"`, { cwd: tempDir });
    execSync(`git config user.email "factory@mahesh0.dev"`, { cwd: tempDir });
    console.log("✅ Repository cloned successfully.");

    // Stage 0: Pre-flight Guard
    console.log("\n----------------------------------------------------------------");
    console.log("🛡️  STAGE 0: Pre-flight Guard Check");
    console.log("----------------------------------------------------------------");
    const preflight = validatePreflight(tempDir, "slug-generator");
    if (!preflight.valid) {
      console.error("❌ Pre-flight check failed with errors:", preflight.errors);
      process.exit(1);
    }
    console.log("✅ Pre-flight Guard passed cleanly: All prerequisites satisfied!");

    // Ticket Discovery
    const tickets = parseTickets(tempDir, "slug-generator");
    console.log(`📋 Found ${tickets.length} ticket(s) in .scratch/slug-generator/issues/`);
    const ticket = getNextFrontierTicket(tickets);
    if (!ticket) {
      throw new Error("No unblocked frontier ticket found in test3!");
    }
    console.log(`🎯 Frontier Ticket ${ticket.id}: "${ticket.title}" (${ticket.status})`);

    const specPath = path.join(tempDir, ".scratch", "slug-generator", "spec.md");
    const contextPath = path.join(tempDir, "CONTEXT.md");
    const specContent = fs.readFileSync(specPath, "utf-8");
    const contextContent = fs.readFileSync(contextPath, "utf-8");

    // Stage 1: Planner Agent
    console.log("\n----------------------------------------------------------------");
    console.log("🧠 STAGE 1: Planner Agent (Read-only reasoning & plan creation)");
    console.log("----------------------------------------------------------------");
    console.log("Invoking Planner Agent with OpenCode Go...");
    const planStartTime = Date.now();
    const { plan } = await runPlannerAgent({
      workspaceDir: tempDir,
      ticket,
      specContent,
      contextContent,
      provider,
      model,
    });
    console.log(`✅ Plan generated in ${Date.now() - planStartTime}ms!`);
    console.log("\n📄 --- Structured Implementation Plan ---");
    console.log(`Summary:      ${plan.summary}`);
    console.log(`Affected:     ${JSON.stringify(plan.affectedFiles)}`);
    console.log(`Test Cmds:    ${JSON.stringify(plan.testCommands)}`);
    console.log("Steps:");
    plan.steps.forEach((step, idx) => console.log(`  ${idx + 1}. ${step}`));
    if (plan.rationale) {
      console.log(`Rationale:    ${plan.rationale}`);
    }

    // Stage 2: Coder Agent
    console.log("\n----------------------------------------------------------------");
    console.log("💻 STAGE 2: Coder Agent (Read, write, edit, bash, and test implementation)");
    console.log("----------------------------------------------------------------");
    console.log("Invoking Coder Agent with OpenCode Go...");
    const coderStartTime = Date.now();
    const { messages: coderMessages } = await runCoderAgent({
      workspaceDir: tempDir,
      ticket,
      plan,
      provider,
      model,
    });
    console.log(`✅ Coder Agent completed in ${Date.now() - coderStartTime}ms!`);
    console.log(`Total messages in agent run: ${coderMessages.length}`);

    // Inspect git status and diff in the workspace
    const gitDiff = execSync("git diff", { cwd: tempDir, encoding: "utf-8" });
    const gitStatus = execSync("git status --porcelain", { cwd: tempDir, encoding: "utf-8" });
    console.log("\n📝 Workspace Modifications (git status):");
    console.log(gitStatus || "(no changes)");
    console.log("\n🔍 Git Diff snippet (first 30 lines):");
    console.log(gitDiff.split("\n").slice(0, 30).join("\n") || "(empty diff)");

    // Stage 3: Deterministic Verifier
    console.log("\n----------------------------------------------------------------");
    console.log("⚖️  STAGE 3: Deterministic Verifier (Non-agentic test execution)");
    console.log("----------------------------------------------------------------");
    const verifierLogPath = path.join(tempDir, ".scratch", "slug-generator", "verification.md");
    const verifyResult = await verifyWorkspace({
      workspacePath: tempDir,
      commands: plan.testCommands.length > 0 ? plan.testCommands : undefined,
      logPath: verifierLogPath,
      streamToProcess: true,
    });

    console.log("\n" + verifyResult.summary);
    if (!verifyResult.passed) {
      console.error("❌ Deterministic verification failed!");
    } else {
      console.log("🎉 Deterministic verification PASSED!");
    }

    // Stage 4: Reviewer Agent
    console.log("\n----------------------------------------------------------------");
    console.log("🧐 STAGE 4: Reviewer Agent (Read-only audit of diff & standards)");
    console.log("----------------------------------------------------------------");
    console.log("Invoking Reviewer Agent with OpenCode Go...");
    const reviewerStartTime = Date.now();
    const { verdict } = await runReviewerAgent({
      workspaceDir: tempDir,
      ticket,
      plan,
      diff: gitDiff,
      provider,
      model,
    });
    console.log(`✅ Reviewer completed in ${Date.now() - reviewerStartTime}ms!`);
    console.log("\n📋 --- Structured Review Verdict ---");
    console.log(`Verdict:              ${verdict.verdict.toUpperCase()}`);
    console.log(`Summary:              ${verdict.summary}`);
    console.log(`Spec Compliance:      ${verdict.specCompliance.passed ? "PASS" : "FAIL"} - ${verdict.specCompliance.details}`);
    console.log(`Standards Compliance: ${verdict.standardsCompliance.passed ? "PASS" : "FAIL"} - ${verdict.standardsCompliance.details}`);
    if (verdict.issues && verdict.issues.length > 0) {
      console.log("Issues:");
      for (const iss of verdict.issues) {
        console.log(`  [${iss.severity.toUpperCase()}] ${iss.description} (${iss.file || "workspace"})`);
      }
    }
    if (verdict.remediation) {
      console.log(`Remediation:          ${verdict.remediation}`);
    }

    console.log("\n================================================================");
    console.log("🏁 Phase 1 Live Verification Summary:");
    console.log(`• Model:                 ${model.id}`);
    console.log(`• Pre-flight:            PASSED`);
    console.log(`• Planner Agent:         PASSED (Plan parsed with ${plan.affectedFiles.length} affected files)`);
    console.log(`• Coder Agent:           PASSED (${coderMessages.length} turns)`);
    console.log(`• Deterministic Verifier: ${verifyResult.passed ? "PASSED" : "FAILED"}`);
    console.log(`• Reviewer Agent:        VERDICT=${verdict.verdict.toUpperCase()}`);
    console.log("================================================================\n");

  } finally {
    console.log(`🧹 Cleaning temporary workspace ${tempDir}...`);
    fs.rmSync(tempDir, { recursive: true, force: true });
    console.log("✅ Workspace cleaned.");
  }
}

main().catch((err) => {
  console.error("\n❌ Fatal error during live test execution:", err);
  process.exit(1);
});
