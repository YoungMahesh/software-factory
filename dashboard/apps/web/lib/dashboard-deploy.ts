import type { DashboardDeployRecord, DashboardDeployTarget } from "@dashboard/types";

export interface DashboardDeployAction {
  target: DashboardDeployTarget;
  label: string;
  targetDomain: string;
  targetUrl: string | null;
}

export function normalizeDeployHost(raw: string | null | undefined): string | null {
  if (!raw || !raw.trim()) return null;
  let cleaned = raw.trim();
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

export function isActiveDashboardDeploy(
  deploy: DashboardDeployRecord | null | undefined,
): boolean {
  if (!deploy) return false;
  return deploy.status === "queued" || deploy.status === "cloning" || deploy.status === "deploying";
}

export function resolveDashboardDeployActions(
  hostname: string | null | undefined,
  appsBaseDomain: string | null | undefined,
): DashboardDeployAction[] {
  const cleanHost = normalizeDeployHost(hostname);
  const cleanBase = normalizeDeployHost(appsBaseDomain);

  const subdomainDomain = cleanBase ? `dashboard.${cleanBase}` : "dashboard subdomain";
  const apexDomain = cleanBase ?? "app base domain";

  const subdomainAction: DashboardDeployAction = {
    target: "subdomain",
    label: cleanBase ? `Deploy ${subdomainDomain}` : "Deploy dashboard subdomain",
    targetDomain: subdomainDomain,
    targetUrl: cleanBase ? `https://${subdomainDomain}` : null,
  };
  const apexAction: DashboardDeployAction = {
    target: "apex",
    label: cleanBase ? `Deploy ${apexDomain}` : "Deploy app base domain",
    targetDomain: apexDomain,
    targetUrl: cleanBase ? `https://${cleanBase}` : null,
  };

  if (cleanBase && cleanHost) {
    if (cleanHost === cleanBase) {
      return [subdomainAction];
    }
    if (cleanHost === subdomainDomain) {
      return [apexAction];
    }
  }

  return [subdomainAction, apexAction];
}
