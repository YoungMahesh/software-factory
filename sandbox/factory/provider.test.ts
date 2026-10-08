import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";

import {
  DEFAULT_MODEL_ID,
  SUPPORTED_MODELS,
  OPENCODE_GO_PROVIDER_ID,
  resolveOpenCodeGoApiKey,
  createOpenCodeGoProvider,
  getFactoryModel,
  ProviderConfigError,
} from "./provider.ts";

test("resolveOpenCodeGoApiKey: resolves explicit apiKey option first", () => {
  const originalEnv = process.env.OPENCODE_GO_API_KEY;
  try {
    process.env.OPENCODE_GO_API_KEY = "env-key";
    const key = resolveOpenCodeGoApiKey({ apiKey: "explicit-key" });
    assert.equal(key, "explicit-key");
  } finally {
    if (originalEnv !== undefined) {
      process.env.OPENCODE_GO_API_KEY = originalEnv;
    } else {
      delete process.env.OPENCODE_GO_API_KEY;
    }
  }
});

test("resolveOpenCodeGoApiKey: resolves from process.env.OPENCODE_GO_API_KEY", () => {
  const originalEnv = process.env.OPENCODE_GO_API_KEY;
  try {
    process.env.OPENCODE_GO_API_KEY = "opencode-go-secret-123";
    const key = resolveOpenCodeGoApiKey();
    assert.equal(key, "opencode-go-secret-123");
  } finally {
    if (originalEnv !== undefined) {
      process.env.OPENCODE_GO_API_KEY = originalEnv;
    } else {
      delete process.env.OPENCODE_GO_API_KEY;
    }
  }
});

test("resolveOpenCodeGoApiKey: resolves from config file when env is unset", async () => {
  const originalGoEnv = process.env.OPENCODE_GO_API_KEY;
  const originalApiEnv = process.env.OPENCODE_API_KEY;
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "opencode-config-"));
  const envFilePath = path.join(tmpDir, "opencode.env");
  await fs.writeFile(envFilePath, "FOO=BAR\nOPENCODE_GO_API_KEY=file-secret-key-456\nBAZ=QUX\n");

  try {
    delete process.env.OPENCODE_GO_API_KEY;
    delete process.env.OPENCODE_API_KEY;
    const key = resolveOpenCodeGoApiKey({ envPath: envFilePath });
    assert.equal(key, "file-secret-key-456");
  } finally {
    if (originalGoEnv !== undefined) process.env.OPENCODE_GO_API_KEY = originalGoEnv;
    if (originalApiEnv !== undefined) process.env.OPENCODE_API_KEY = originalApiEnv;
    await fs.rm(tmpDir, { recursive: true, force: true });
  }
});

test("resolveOpenCodeGoApiKey: falls back to OPENCODE_API_KEY", () => {
  const originalGoEnv = process.env.OPENCODE_GO_API_KEY;
  const originalApiEnv = process.env.OPENCODE_API_KEY;
  try {
    delete process.env.OPENCODE_GO_API_KEY;
    process.env.OPENCODE_API_KEY = "fallback-key-789";
    const key = resolveOpenCodeGoApiKey();
    assert.equal(key, "fallback-key-789");
  } finally {
    if (originalGoEnv !== undefined) process.env.OPENCODE_GO_API_KEY = originalGoEnv;
    if (originalApiEnv !== undefined) process.env.OPENCODE_API_KEY = originalApiEnv;
  }
});

test("createOpenCodeGoProvider: throws ProviderConfigError when no key is found", () => {
  const originalGoEnv = process.env.OPENCODE_GO_API_KEY;
  const originalApiEnv = process.env.OPENCODE_API_KEY;
  try {
    delete process.env.OPENCODE_GO_API_KEY;
    delete process.env.OPENCODE_API_KEY;
    assert.throws(
      () => createOpenCodeGoProvider({ envPath: "/nonexistent/path/opencode.env" }),
      (err) => err instanceof ProviderConfigError && /OPENCODE_GO_API_KEY/.test(err.message)
    );
  } finally {
    if (originalGoEnv !== undefined) process.env.OPENCODE_GO_API_KEY = originalGoEnv;
    if (originalApiEnv !== undefined) process.env.OPENCODE_API_KEY = originalApiEnv;
  }
});

test("createOpenCodeGoProvider: returns provider configured for opencode-go and supported models", () => {
  const provider = createOpenCodeGoProvider({ apiKey: "test-api-key" });
  assert.equal(provider.id, OPENCODE_GO_PROVIDER_ID);
  assert.equal(provider.id, "opencode-go");

  const models = provider.getModels();
  const modelIds = models.map((m) => m.id);
  assert.ok(modelIds.includes("deepseek-v4.1-flash"), "must include deepseek-v4.1-flash");
  assert.ok(modelIds.includes("mimo-v2.6-flash"), "must include mimo-v2.6-flash");

  // Every model in provider must be one of the supported models
  for (const model of models) {
    assert.ok(
      SUPPORTED_MODELS.includes(model.id as any),
      `Model ${model.id} should be among supported models: ${SUPPORTED_MODELS.join(", ")}`
    );
  }
});

test("getFactoryModel: defaults to DeepSeek V4.1 Flash flagship model", () => {
  const provider = createOpenCodeGoProvider({ apiKey: "test-api-key" });
  const model = getFactoryModel(undefined, provider);
  assert.equal(model.id, DEFAULT_MODEL_ID);
  assert.equal(model.id, "deepseek-v4.1-flash");
  assert.equal(model.name, "DeepSeek V4.1 Flash");
  assert.equal(model.provider, "opencode-go");
});

test("getFactoryModel: retrieves MiMo-V2.6-Flash when requested", () => {
  const provider = createOpenCodeGoProvider({ apiKey: "test-api-key" });
  const model = getFactoryModel("mimo-v2.6-flash", provider);
  assert.equal(model.id, "mimo-v2.6-flash");
  assert.equal(model.name, "MiMo-V2.6-Flash");
  assert.equal(model.provider, "opencode-go");
});

test("getFactoryModel: resolves CLI alias 'mimo' to MiMo-V2.6-Flash per ADR 0027", () => {
  const provider = createOpenCodeGoProvider({ apiKey: "test-api-key" });
  const model = getFactoryModel("mimo", provider);
  assert.equal(model.id, "mimo-v2.6-flash");
  assert.equal(model.name, "MiMo-V2.6-Flash");
});

test("getFactoryModel: rejects unsupported models", () => {
  const provider = createOpenCodeGoProvider({ apiKey: "test-api-key" });
  assert.throws(
    () => getFactoryModel("unsupported-model-x" as any, provider),
    (err) => err instanceof ProviderConfigError && /unsupported/i.test(err.message)
  );
});
