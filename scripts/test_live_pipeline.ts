import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { execSync } from "node:child_process";

import { createOpenCodeGoProvider, getFactoryModel } from "../sandbox/factory/provider.ts";
import { runAssemblyLinePipeline } from "../sandbox/factory/pipeline.ts";

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
  console.log("🚀 Way 1: Local Live Runner for Assembly Line Pipeline on test3");
  console.log("================================================================\n");

  const rootDir = path.resolve(import.meta.dirname, "..");
  const test3FetchPath = path.join(rootDir, "secrets_testing", "test3", "fetch.env");
  const opencodeEnvPath = path.join(rootDir, "secrets", "opencode.env");

  if (!fs.existsSync(test3FetchPath)) {
    throw new Error(`Missing test3 fetch credentials at ${test3FetchPath}`);
  }
  if (!fs.existsSync(opencodeEnvPath)) {
    throw new Error(`Missing OpenCode credentials at ${opencodeEnvPath}`);
  }

  console.log("🔑 Decrypting credentials with SOPS...");
  const test3Env = decryptEnv(test3FetchPath);
  const opencodeEnv = decryptEnv(opencodeEnvPath);

  const ghRepo = test3Env.GH_REPO;
  const ghToken = test3Env.GH_TOKEN;
  const opencodeApiKey = opencodeEnv.OPENCODE_GO_API_KEY;

  if (!ghRepo || !ghToken || !opencodeApiKey) {
    throw new Error("Missing required credentials from decrypted secrets");
  }

  process.env.OPENCODE_GO_API_KEY = opencodeApiKey;
  console.log(`✅ Target repository: ${ghRepo}`);
  console.log(`✅ OpenCode API Key configured (${opencodeApiKey.slice(0, 10)}...)`);

  // Provider and model
  const provider = createOpenCodeGoProvider({ apiKey: opencodeApiKey });
  const model = getFactoryModel("deepseek-v4.1-flash", provider);
  console.log(`✅ Model initialized: ${model.id} (${model.name})`);

  // Setup fresh temporary workspace
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "sf-pipeline-test3-"));
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

    // Run the full assembly line pipeline
    console.log("\n----------------------------------------------------------------");
    console.log("🏭 Executing Assembly Line Pipeline Coordinator (runAssemblyLinePipeline)");
    console.log("----------------------------------------------------------------\n");

    const startTime = Date.now();
    const result = await runAssemblyLinePipeline({
      workspaceDir: tempDir,
      featureSlug: "slug-generator",
      provider,
      model,
      push: true,
    });

    const elapsed = Date.now() - startTime;
    console.log(`\n⏱️  Pipeline execution completed in ${elapsed}ms!`);
    console.log("\n" + result.summary);

    if (result.haltedOnError || !result.allResolved) {
      throw new Error(`Pipeline halted or failed to resolve all tickets: ${JSON.stringify(result)}`);
    }

    // Verify remote branch was pushed
    console.log("\n🔍 Verifying remote branch on GitHub...");
    const remoteRefs = execSync(`git ls-remote --heads origin "factory/slug-generator"`, {
      cwd: tempDir,
      encoding: "utf-8",
    });
    console.log("Remote ref:\n" + remoteRefs.trim());

    if (!remoteRefs.includes("refs/heads/factory/slug-generator")) {
      throw new Error("factory/slug-generator ref was NOT found on origin after push!");
    }

    console.log("✅ Remote feature branch verified on GitHub origin!");
    console.log("\n🎉 WAY 1: LOCAL LIVE ASSEMBLY LINE PIPELINE PASSED SUCCESSFULLY!");

  } finally {
    console.log(`\n🧹 Cleaning temporary workspace ${tempDir}...`);
    fs.rmSync(tempDir, { recursive: true, force: true });
    console.log("✅ Temporary workspace cleaned.");
  }
}

main().catch((err) => {
  console.error("\n❌ Fatal error during Way 1 live pipeline execution:", err);
  process.exit(1);
});
