import test from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import { execSync } from "node:child_process";

import {
  validatePreflight,
  parseTickets,
  getNextFrontierTicket,
} from "./preflight.ts";

function getOrgToken(): string {
  const tokenPath = path.resolve(import.meta.dirname, "../../secrets_org/software-factory-09-test/token");
  return execSync(`sops -d "${tokenPath}"`, { encoding: "utf-8" }).trim();
}

function cloneRepo(ghRepo: string, ghToken: string, destDir: string): void {
  const url = `https://x-access-token:${ghToken}@github.com/${ghRepo}.git`;
  try {
    execSync(`git clone --depth 1 "${url}" "${destDir}"`, {
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (err) {
    // If repo is empty, git clone may exit with code 128 / warning, but create destDir with .git
    if (fs.existsSync(destDir)) {
      return;
    }
    throw err;
  }
}

test("Integration: test1 (empty repo) is cleanly rejected by preflight guard", (t) => {
  const tokenPath = path.resolve(import.meta.dirname, "../../secrets_org/software-factory-09-test/token");
  if (!fs.existsSync(tokenPath)) {
    t.skip("secrets_org/software-factory-09-test/token not found");
    return;
  }

  const ghToken = getOrgToken();
  const ghRepo = "software-factory-09-test/test1";
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "sf-int-test1-"));

  try {
    cloneRepo(ghRepo, ghToken, tempDir);

    const result = validatePreflight(tempDir, "test-feature");
    assert.strictEqual(result.valid, false, "Expected preflight to fail for empty repo");
    assert.strictEqual(result.errors.length, 4, "Expected exactly 4 prerequisite errors");

    // 1. Missing spec
    assert.ok(
      result.errors.some((e) => e.includes(".scratch/test-feature/spec.md")),
      "Expected missing spec error"
    );

    // 2. Missing CONTEXT.md / GLOSSARY.md
    assert.ok(
      result.errors.some((e) => e.includes("CONTEXT.md") && e.includes("GLOSSARY.md")),
      "Expected missing context/glossary error"
    );

    // 3. Missing issue tracker configuration
    assert.ok(
      result.errors.some((e) => e.includes("issue tracking configuration")),
      "Expected missing issue tracking error"
    );

    // 4. Missing architectural decision records (docs/adr/)
    assert.ok(
      result.errors.some((e) => e.includes("docs/adr/")),
      "Expected missing ADR error"
    );
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});

test("Integration: test2 (queues-page) passes preflight, parses tickets, and resolves ticket 01 on frontier", (t) => {
  const tokenPath = path.resolve(import.meta.dirname, "../../secrets_org/software-factory-09-test/token");
  if (!fs.existsSync(tokenPath)) {
    t.skip("secrets_org/software-factory-09-test/token not found");
    return;
  }

  const ghToken = getOrgToken();
  const ghRepo = "software-factory-09-test/test2";
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "sf-int-test2-"));

  try {
    cloneRepo(ghRepo, ghToken, tempDir);

    // 1. Preflight validation for queues-page feature
    const result = validatePreflight(tempDir, "queues-page");
    assert.strictEqual(
      result.valid,
      true,
      `Expected preflight to pass for test2, got errors: ${result.errors.join("; ")}`
    );
    assert.strictEqual(result.errors.length, 0);

    // 2. Discover and parse tickets
    const tickets = parseTickets(tempDir, "queues-page");
    assert.strictEqual(tickets.length, 3, "Expected 3 tickets in queues-page");

    assert.strictEqual(tickets[0].id, "01");
    assert.strictEqual(tickets[0].number, 1);
    assert.strictEqual(tickets[0].status, "ready-for-agent");
    assert.deepStrictEqual(tickets[0].blockedBy, []);
    assert.ok(tickets[0].title.includes("Page shell plus opening sections"));

    assert.strictEqual(tickets[1].id, "02");
    assert.strictEqual(tickets[1].number, 2);

    assert.strictEqual(tickets[2].id, "03");
    assert.strictEqual(tickets[2].number, 3);

    // 3. Frontier resolution: Ticket 01 is open and unblocked
    const nextTicket = getNextFrontierTicket(tickets);
    assert.ok(nextTicket, "Expected an unblocked frontier ticket");
    assert.strictEqual(nextTicket.id, "01");
    assert.strictEqual(nextTicket.status, "ready-for-agent");
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});
