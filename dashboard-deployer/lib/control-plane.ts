import { loadWorkspaceEnv } from "./env";
import {
  DashboardDeployStatusResponseSchema,
  DocsDeployStatusResponseSchema,
  VersionInfoSchema,
  type DashboardDeployRecord,
  type DeployerStatusPayload,
  type DocsDeployRecord,
  type VersionInfo,
} from "./deploy-types";

export class ControlPlaneConfigError extends Error {
  status: number;

  constructor(message: string, status = 500) {
    super(message);
    this.name = "ControlPlaneConfigError";
    this.status = status;
  }
}

export function normalizeBaseDomain(rawDomain: string | undefined): string | null {
  if (!rawDomain || !rawDomain.trim()) return null;
  let cleaned = rawDomain.trim();
  if (cleaned.includes("://")) {
    try {
      cleaned = new URL(cleaned).hostname;
    } catch {
      return null;
    }
  }
  cleaned = cleaned
    .split("/")[0]
    .split(":")[0]
    .trim()
    .toLowerCase()
    .replace(/^\*\./, "")
    .replace(/\.+$/, "");
  return cleaned || null;
}

export function isSubdomainOf(hostname: string, baseDomain: string): boolean {
  const cleanHost = hostname.trim().toLowerCase().replace(/\.+$/, "");
  const cleanBase = baseDomain.trim().toLowerCase().replace(/\.+$/, "");
  return cleanHost === cleanBase || cleanHost.endsWith(`.${cleanBase}`);
}

export function resolveControlPlaneOrigin(env: NodeJS.ProcessEnv = process.env): string {
  const raw = env.SANDBOX_CONTROL_PLANE_URL?.trim() || env.SANDBOX_DASHBOARD_UPSTREAM?.trim();
  if (!raw) {
    throw new ControlPlaneConfigError(
      "SANDBOX_CONTROL_PLANE_URL is not configured for Dashboard Deployer.",
    );
  }

  const candidate = raw.includes("://") ? raw : `https://${raw}`;
  let parsed: URL;
  try {
    parsed = new URL(candidate);
  } catch {
    throw new ControlPlaneConfigError(`Invalid SANDBOX_CONTROL_PLANE_URL: '${raw}'.`);
  }

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new ControlPlaneConfigError(
      `Invalid SANDBOX_CONTROL_PLANE_URL scheme '${parsed.protocol}'; expected http or https.`,
    );
  }
  if ((parsed.pathname && parsed.pathname !== "/") || parsed.search || parsed.hash) {
    throw new ControlPlaneConfigError(
      `SANDBOX_CONTROL_PLANE_URL '${raw}' must be an origin without path, query, or hash.`,
    );
  }

  const baseDomain = normalizeBaseDomain(env.APPS_BASE_DOMAIN);
  if (baseDomain && isSubdomainOf(parsed.hostname, baseDomain)) {
    throw new ControlPlaneConfigError(
      `SANDBOX_CONTROL_PLANE_URL '${raw}' cannot target '${baseDomain}' or its subdomains (proxy loop guard).`,
    );
  }

  return `${parsed.protocol}//${parsed.host}`;
}

export function resolveControlPlaneAuthHeader(env: NodeJS.ProcessEnv = process.env): string {
  const user = env.WEB_UI_USERNAME?.trim();
  const pass = env.WEB_UI_PASSWORD?.trim();
  if (!user || !pass) {
    throw new ControlPlaneConfigError(
      "WEB_UI_USERNAME and WEB_UI_PASSWORD must be configured for Dashboard Deployer.",
    );
  }
  const encoded = Buffer.from(`${user}:${pass}`, "utf-8").toString("base64");
  return `Basic ${encoded}`;
}

export async function proxyControlPlaneRequest(
  path: string,
  options: {
    method?: "GET" | "POST";
    body?: string;
    fetchImpl?: typeof fetch;
    env?: NodeJS.ProcessEnv;
    signal?: AbortSignal;
  } = {},
): Promise<Response> {
  loadWorkspaceEnv();
  const env = options.env ?? process.env;
  const fetchImpl = options.fetchImpl ?? fetch;

  let targetUrl: string;
  let authHeader: string;
  try {
    const origin = resolveControlPlaneOrigin(env);
    authHeader = resolveControlPlaneAuthHeader(env);
    targetUrl = `${origin}${path}`;
  } catch (err) {
    const status = err instanceof ControlPlaneConfigError ? err.status : 500;
    const message = err instanceof Error ? err.message : "Invalid Control Plane configuration.";
    return Response.json({ detail: message }, { status });
  }

  const headers = new Headers();
  headers.set("Authorization", authHeader);
  headers.set("Accept", "application/json");
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }

  let upstream: Response;
  try {
    upstream = await fetchImpl(targetUrl, {
      method: options.method ?? "GET",
      headers,
      body: options.body,
      cache: "no-store",
      signal: options.signal,
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return Response.json(
      { detail: `Failed connecting to Sandbox Control Plane: ${detail}` },
      { status: 502 },
    );
  }

  const upstreamType = upstream.headers.get("content-type") || "application/json; charset=utf-8";
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": upstreamType,
      "Cache-Control": "no-store",
    },
  });
}

export async function proxyDeployStatusById(
  upstreamPrefix: string,
  deployId: string,
  signal?: AbortSignal,
): Promise<Response> {
  if (!deployId || !/^[A-Za-z0-9_-]+$/.test(deployId)) {
    return Response.json({ detail: "Invalid deploy ID." }, { status: 400 });
  }
  return proxyControlPlaneRequest(`${upstreamPrefix}/${encodeURIComponent(deployId)}`, {
    method: "GET",
    signal,
  });
}

async function fetchLiveCommitProbe(
  probeUrl: string | null,
  extractCommit: (payload: Record<string, unknown>) => string | null,
  fetchImpl: typeof fetch = fetch,
): Promise<{ commit: string | null; reachable: boolean }> {
  if (!probeUrl) return { commit: null, reachable: false };
  try {
    const res = await fetchImpl(probeUrl, {
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    if (!res.ok) return { commit: null, reachable: false };
    const data = (await res.json()) as Record<string, unknown>;
    return { commit: extractCommit(data), reachable: true };
  } catch {
    return { commit: null, reachable: false };
  }
}

export async function fetchLiveDashboardHealth(
  targetUrl: string | null,
  fetchImpl: typeof fetch = fetch,
): Promise<{ commit: string | null; reachable: boolean }> {
  return fetchLiveCommitProbe(
    targetUrl ? `${targetUrl}/api/health` : null,
    (data) =>
      typeof data.dashboard_commit === "string" && data.dashboard_commit.trim()
        ? data.dashboard_commit.trim()
        : null,
    fetchImpl,
  );
}

export async function fetchLiveDocsInfo(
  docsTargetUrl: string | null,
  fetchImpl: typeof fetch = fetch,
): Promise<{ commit: string | null; reachable: boolean }> {
  return fetchLiveCommitProbe(
    docsTargetUrl ? `${docsTargetUrl}/deploy-info.json` : null,
    (data) => {
      if (typeof data.commit_short === "string" && data.commit_short.trim()) {
        return data.commit_short.trim();
      }
      if (typeof data.commit === "string" && data.commit.trim()) {
        return data.commit.trim().slice(0, 7);
      }
      return null;
    },
    fetchImpl,
  );
}

export async function gatherDeployerStatus(
  options: { fetchImpl?: typeof fetch; env?: NodeJS.ProcessEnv } = {},
): Promise<DeployerStatusPayload> {
  loadWorkspaceEnv();
  const env = options.env ?? process.env;
  const fetchImpl = options.fetchImpl ?? fetch;

  const baseDomain = normalizeBaseDomain(env.APPS_BASE_DOMAIN);
  const targetUrl = baseDomain ? `https://${baseDomain}` : null;
  const docsTargetUrl = baseDomain ? `https://docs.${baseDomain}` : null;
  const deployerCommit = env.NEXT_PUBLIC_DASHBOARD_COMMIT?.trim() || null;

  let origin: string | null = null;
  let authHeader: string | null = null;
  let configError: string | null = null;
  try {
    origin = resolveControlPlaneOrigin(env);
    authHeader = resolveControlPlaneAuthHeader(env);
  } catch (err) {
    configError = err instanceof Error ? err.message : "Invalid Control Plane configuration.";
  }

  let controlPlaneVersion: VersionInfo | null = null;
  let latestDeploy: DashboardDeployRecord | null = null;
  let latestDocsDeploy: DocsDeployRecord | null = null;
  let cpError = configError;

  const liveDashboardPromise = fetchLiveDashboardHealth(targetUrl, fetchImpl);
  const liveDocsPromise = fetchLiveDocsInfo(docsTargetUrl, fetchImpl);

  if (origin && authHeader) {
    const headers = { Authorization: authHeader, Accept: "application/json" };
    const [versionRes, deployRes, docsDeployRes] = await Promise.allSettled([
      fetchImpl(`${origin}/api/version`, { headers, cache: "no-store" }),
      fetchImpl(`${origin}/api/dashboard/deploy`, { headers, cache: "no-store" }),
      fetchImpl(`${origin}/api/docs/deploy`, { headers, cache: "no-store" }),
    ]);

    if (versionRes.status === "fulfilled" && versionRes.value.ok) {
      try {
        controlPlaneVersion = VersionInfoSchema.parse(await versionRes.value.json());
      } catch {
        // Ignore malformed version payload.
      }
    } else if (versionRes.status === "rejected" && !cpError) {
      cpError = `Failed reaching Sandbox Control Plane: ${String(versionRes.reason)}`;
    } else if (versionRes.status === "fulfilled" && !versionRes.value.ok && !cpError) {
      cpError = `Sandbox Control Plane returned HTTP ${versionRes.value.status}.`;
    }

    if (deployRes.status === "fulfilled" && deployRes.value.ok) {
      try {
        latestDeploy = DashboardDeployStatusResponseSchema.parse(await deployRes.value.json()).deploy;
      } catch {
        // Ignore malformed deploy payload.
      }
    }

    if (docsDeployRes.status === "fulfilled" && docsDeployRes.value.ok) {
      try {
        latestDocsDeploy = DocsDeployStatusResponseSchema.parse(await docsDeployRes.value.json()).deploy;
      } catch {
        // Ignore malformed docs deploy payload.
      }
    }
  }

  const [liveHealth, liveDocs] = await Promise.all([liveDashboardPromise, liveDocsPromise]);

  return {
    apps_base_domain: baseDomain,
    target_url: targetUrl,
    docs_target_url: docsTargetUrl,
    deployer_commit: deployerCommit,
    control_plane_configured: Boolean(origin && authHeader),
    control_plane_error: cpError,
    control_plane_version: controlPlaneVersion,
    live_dashboard_commit: liveHealth.commit,
    live_dashboard_reachable: liveHealth.reachable,
    live_docs_commit: liveDocs.commit,
    live_docs_reachable: liveDocs.reachable,
    latest_deploy: latestDeploy,
    latest_docs_deploy: latestDocsDeploy,
  };
}
