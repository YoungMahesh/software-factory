import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { loadWorkspaceEnv } from "../lib/env";

export interface DatabaseConnectionConfig {
  connectionString: string;
  ssl?: {
    rejectUnauthorized: boolean;
    ca: string;
  };
}

const DEFAULT_LOCAL_DATABASE_URL =
  "postgres://postgres:postgres@localhost:5432/template_db";

function findFallbackCaCert(cwd: string = process.cwd()): string | undefined {
  const candidates = [
    process.env.RESOURCE_PLANE_CA_CERT,
    process.env.PGSSLROOTCERT,
    path.join(os.homedir(), ".config", "resource-plane", "ca.crt"),
    path.join(os.homedir(), ".config", "db-host", "ca.crt"),
    path.resolve(cwd, ".certs", "ca.crt"),
    path.resolve(cwd, "../../.certs", "ca.crt"),
  ].filter((candidate): candidate is string => Boolean(candidate));

  for (const candidate of candidates) {
    if (
      fs.existsSync(/*turbopackIgnore: true*/ candidate) &&
      fs.statSync(/*turbopackIgnore: true*/ candidate).size > 0
    ) {
      return candidate;
    }
  }
  return undefined;
}

/**
 * Resolves the PostgreSQL connection string and portable TLS CA configuration
 * across local developer workstations and Modal sandboxes.
 */
export function resolveDatabaseConfig(
  explicitUrl?: string,
  cwd: string = process.cwd(),
): DatabaseConnectionConfig {
  loadWorkspaceEnv(cwd);

  const rawUrl =
    explicitUrl || process.env.DATABASE_URL || DEFAULT_LOCAL_DATABASE_URL;

  try {
    const parsed = new URL(rawUrl);
    const sslMode = parsed.searchParams.get("sslmode");
    const requestedCert = parsed.searchParams.get("sslrootcert");

    let resolvedCertPath: string | undefined;
    if (requestedCert && fs.existsSync(/*turbopackIgnore: true*/ requestedCert)) {
      resolvedCertPath = requestedCert;
    } else if (requestedCert || sslMode === "verify-full") {
      resolvedCertPath = findFallbackCaCert(cwd);
      if (resolvedCertPath) {
        parsed.searchParams.set("sslrootcert", resolvedCertPath);
      }
    }

    if (resolvedCertPath) {
      return {
        connectionString: parsed.toString(),
        ssl: {
          rejectUnauthorized: true,
          ca: fs.readFileSync(/*turbopackIgnore: true*/ resolvedCertPath, "utf-8"),
        },
      };
    }

    return { connectionString: parsed.toString() };
  } catch {
    return { connectionString: rawUrl };
  }
}
