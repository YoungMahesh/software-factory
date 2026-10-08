import fs from "node:fs";
import { execSync } from "node:child_process";
import { runAssemblyLinePipeline } from "./pipeline.ts";

async function run() {
  console.log("================================================================");
  console.log("🚀 In-Container Assembly Line Pipeline Verification on /root/test3");
  console.log("================================================================\n");

  const workspaceDir = "/root/test3";
  if (!fs.existsSync(workspaceDir)) {
    throw new Error(`Workspace directory ${workspaceDir} does not exist`);
  }

  // Execute the complete assembly line pipeline inside the Modal Sandbox container
  console.log("🏭 Launching runAssemblyLinePipeline for feature 'slug-generator'...");
  const startTime = Date.now();
  const result = await runAssemblyLinePipeline({
    workspaceDir,
    featureSlug: "slug-generator",
    push: true,
  });

  const duration = Date.now() - startTime;
  console.log(`\n⏱️  In-container pipeline completed in ${duration}ms!\n`);
  console.log(result.summary);

  if (result.haltedOnError || !result.allResolved) {
    throw new Error(`In-container assembly line pipeline failed: ${JSON.stringify(result)}`);
  }

  // Verify that the branch exists on remote origin
  console.log("\n🔍 Verifying pushed feature branch on remote origin...");
  const remoteRef = execSync('git ls-remote --heads origin "factory/slug-generator"', {
    cwd: workspaceDir,
    encoding: "utf-8",
  }).trim();

  console.log(`Remote ref: ${remoteRef}`);
  if (!remoteRef.includes("refs/heads/factory/slug-generator")) {
    throw new Error("Feature branch factory/slug-generator not found on remote origin!");
  }
  console.log("✅ Remote feature branch verified on GitHub origin from inside container!");

  console.log("\n================================================================");
  console.log("🏁 IN-CONTAINER ASSEMBLY LINE PIPELINE PASSED SUCCESSFULLY!");
  console.log("================================================================\n");
}

run().catch((err) => {
  console.error("❌ Fatal error in container verification:", err);
  process.exit(1);
});
