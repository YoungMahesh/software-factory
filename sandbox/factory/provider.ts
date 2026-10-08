import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import crypto from "node:crypto";
import { type Provider, type Model } from "@earendil-works/pi-ai";
import { opencodeGoProvider } from "@earendil-works/pi-ai/providers/opencode-go";

export const OPENCODE_GO_PROVIDER_ID = "opencode-go" as const;

export const SUPPORTED_MODELS = [
  "deepseek-v4.1-flash",
  "mimo-v2.6-flash",
] as const;

export type SupportedModelId = typeof SUPPORTED_MODELS[number];

export const DEFAULT_MODEL_ID: SupportedModelId = "deepseek-v4.1-flash";

export class ProviderConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ProviderConfigError";
  }
}

/**
 * Resolves the OpenCode Go API key from explicit option, environment variables,
 * or decrypted ~/.config/opencode/opencode.env file.
 */
export function resolveOpenCodeGoApiKey(options?: {
  apiKey?: string;
  envPath?: string;
}): string | undefined {
  if (options?.apiKey && options.apiKey.trim().length > 0) {
    return options.apiKey.trim();
  }

  if (process.env.OPENCODE_GO_API_KEY && process.env.OPENCODE_GO_API_KEY.trim().length > 0) {
    return process.env.OPENCODE_GO_API_KEY.trim();
  }

  const defaultEnvPath = path.join(os.homedir(), ".config", "opencode", "opencode.env");
  const targetEnvPath = options?.envPath ?? defaultEnvPath;

  if (fs.existsSync(targetEnvPath)) {
    try {
      const content = fs.readFileSync(targetEnvPath, "utf-8");
      const lines = content.split("\n");
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith("#")) continue;
        const matchGo = trimmed.match(/^OPENCODE_GO_API_KEY=(.+)$/);
        if (matchGo && matchGo[1]) {
          return matchGo[1].trim().replace(/^['"]|['"]$/g, "");
        }
        const matchDefault = trimmed.match(/^OPENCODE_API_KEY=(.+)$/);
        if (matchDefault && matchDefault[1]) {
          return matchDefault[1].trim().replace(/^['"]|['"]$/g, "");
        }
      }
    } catch {
      // Fall through to fallback env var
    }
  }

  if (process.env.OPENCODE_API_KEY && process.env.OPENCODE_API_KEY.trim().length > 0) {
    return process.env.OPENCODE_API_KEY.trim();
  }

  return undefined;
}

/**
 * Configures the OpenCode Go provider with the resolved API key and restricts
 * available models strictly to DeepSeek V4.1 Flash and MiMo-V2.6-Flash.
 */
export function createOpenCodeGoProvider(options?: {
  apiKey?: string;
  envPath?: string;
}): Provider {
  const apiKey = resolveOpenCodeGoApiKey(options);
  if (!apiKey) {
    throw new ProviderConfigError(
      "OpenCode Go API key not found. Ensure OPENCODE_GO_API_KEY is set in environment or decrypted in ~/.config/opencode/opencode.env"
    );
  }

  // Ensure OPENCODE_API_KEY is ambiently set for underlying pi-ai auth handlers
  process.env.OPENCODE_API_KEY = apiKey;
  if (!process.env.OPENCODE_GO_API_KEY) {
    process.env.OPENCODE_GO_API_KEY = apiKey;
  }

  const baseProvider = opencodeGoProvider();

  const supportedModelsList = baseProvider
    .getModels()
    .filter((m) => (SUPPORTED_MODELS as readonly string[]).includes(m.id));

  const injectDefaults = (opts?: any) => {
    return {
      ...opts,
      apiKey: opts?.apiKey ?? apiKey,
      sessionId: opts?.sessionId ?? crypto.randomUUID(),
    };
  };

  return {
    ...baseProvider,
    getModels: () => supportedModelsList,
    getAllModels: () => supportedModelsList,
    stream: (model, context, streamOptions) =>
      baseProvider.stream(model, context, injectDefaults(streamOptions)),
    streamSimple: (model, context, streamOptions) =>
      baseProvider.streamSimple(model, context, injectDefaults(streamOptions)),
  };
}

/**
 * Resolves a model from provider, defaulting to DeepSeek V4.1 Flash.
 * Validates that requested model belongs to the supported list.
 */
export function getFactoryModel(
  modelId?: string,
  provider?: Provider
): Model<string> {
  const effectiveProvider = provider ?? createOpenCodeGoProvider();
  const effectiveModelId = modelId ?? DEFAULT_MODEL_ID;

  if (effectiveProvider.id === OPENCODE_GO_PROVIDER_ID) {
    if (!(SUPPORTED_MODELS as readonly string[]).includes(effectiveModelId)) {
      throw new ProviderConfigError(
        `Unsupported model: "${effectiveModelId}". Supported OpenCode Go models are: ${SUPPORTED_MODELS.join(", ")}`
      );
    }
  }

  const models = effectiveProvider.getModels();
  const found = models.find((m) => m.id === effectiveModelId);

  if (!found) {
    throw new ProviderConfigError(
      `Model "${effectiveModelId}" not found in provider "${effectiveProvider.id}". Available models: ${models.map((m) => m.id).join(", ")}`
    );
  }

  return found;
}
