import { loadWorkspaceEnv } from "./env";

const ALLOWED_METHODS = new Set(["GET", "POST", "DELETE"]);

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
      const parsed = new URL(cleaned);
      cleaned = parsed.hostname;
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
      "SANDBOX_CONTROL_PLANE_URL is not configured for the dashboard BFF proxy.",
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
      "WEB_UI_USERNAME and WEB_UI_PASSWORD must be configured for the dashboard BFF proxy.",
    );
  }
  const encoded = Buffer.from(`${user}:${pass}`, "utf-8").toString("base64");
  return `Basic ${encoded}`;
}

export function buildUpstreamApiUrl(
  origin: string,
  pathSegments: string[],
  search: string,
): string {
  if (!pathSegments.length) {
    throw new ControlPlaneConfigError("Missing control plane API path.", 400);
  }
  const cleanSegments = pathSegments.map((seg) => {
    if (!seg || seg === "." || seg === ".." || seg.includes("/") || seg.includes("\\")) {
      throw new ControlPlaneConfigError(`Invalid API path segment '${seg}'.`, 400);
    }
    return encodeURIComponent(seg);
  });
  return `${origin}/api/${cleanSegments.join("/")}${search}`;
}

export async function proxyToControlPlane(
  request: Request,
  pathSegments: string[],
  options: { fetchImpl?: typeof fetch; env?: NodeJS.ProcessEnv } = {},
): Promise<Response> {
  loadWorkspaceEnv();
  const env = options.env ?? process.env;
  const fetchImpl = options.fetchImpl ?? fetch;

  if (!ALLOWED_METHODS.has(request.method.toUpperCase())) {
    return Response.json(
      { detail: `Method ${request.method} is not allowed on dashboard BFF.` },
      { status: 405 },
    );
  }

  let targetUrl: string;
  let authHeader: string;
  try {
    const origin = resolveControlPlaneOrigin(env);
    authHeader = resolveControlPlaneAuthHeader(env);
    const reqUrl = new URL(request.url);
    targetUrl = buildUpstreamApiUrl(origin, pathSegments, reqUrl.search);
  } catch (err) {
    const status = err instanceof ControlPlaneConfigError ? err.status : 500;
    const message = err instanceof Error ? err.message : "Invalid BFF proxy configuration.";
    return Response.json({ detail: message }, { status });
  }

  const headers = new Headers();
  headers.set("Authorization", authHeader);
  const accept = request.headers.get("accept");
  if (accept) headers.set("Accept", accept);
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);

  let body: ArrayBuffer | undefined;
  if (request.method !== "GET" && request.method !== "HEAD") {
    const buf = await request.arrayBuffer();
    if (buf.byteLength > 0) {
      body = buf;
    }
  }

  let upstream: Response;
  try {
    upstream = await fetchImpl(targetUrl, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      signal: request.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      return Response.json({ detail: "Upstream request aborted." }, { status: 499 });
    }
    const detail = err instanceof Error ? err.message : String(err);
    return Response.json(
      { detail: `Failed connecting to Sandbox Control Plane: ${detail}` },
      { status: 502 },
    );
  }

  const upstreamType = upstream.headers.get("content-type") || "application/json; charset=utf-8";
  if (upstreamType.toLowerCase().includes("text/event-stream")) {
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
    });
  }

  const responseHeaders = new Headers();
  responseHeaders.set("Content-Type", upstreamType);
  responseHeaders.set("Cache-Control", "no-store");
  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}
