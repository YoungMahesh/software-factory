import type { T3PairingLinkEntry } from "@dashboard/types";

export function buildSandboxT3LinksPath(
  sandboxId: string,
  profile?: string | null,
): string {
  const query = profile ? `?profile=${encodeURIComponent(profile)}` : "";
  return `/api/sandboxes/${encodeURIComponent(sandboxId)}/t3-links${query}`;
}

export function seedInitialT3Links(
  t3PairUrl: string | null | undefined,
): T3PairingLinkEntry[] {
  if (!t3PairUrl || !t3PairUrl.includes("#token=")) {
    return [];
  }
  return [
    {
      url: t3PairUrl,
      status: "active",
    },
  ];
}

export function appendGeneratedT3Link(
  existing: T3PairingLinkEntry[],
  created: T3PairingLinkEntry,
): T3PairingLinkEntry[] {
  const filtered = existing.filter(
    (item) =>
      !(
        (created.id && item.id === created.id) ||
        item.url === created.url
      ),
  );
  return [...filtered, created];
}
