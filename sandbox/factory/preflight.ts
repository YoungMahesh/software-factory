import * as fs from "node:fs";
import * as path from "node:path";

export interface PreflightCheckResult {
  valid: boolean;
  errors: string[];
}

export class PreflightError extends Error {
  public readonly errors: string[];

  constructor(errors: string[]) {
    super(
      `Pre-flight Guard validation failed:\n${errors.map((e) => `  - ${e}`).join("\n")}`
    );
    this.name = "PreflightError";
    this.errors = errors;
  }
}

export type TicketStatus =
  | "open"
  | "ready-for-agent"
  | "claimed"
  | "resolved"
  | "ready-for-human"
  | string;

export interface Ticket {
  id: string;
  number: number;
  slug: string;
  title: string;
  filePath: string;
  status: TicketStatus;
  blockedBy: string[];
}

/**
 * Searches for CONTEXT.md or GLOSSARY.md at repository root or canonical domain paths (docs/, src/{domain}/).
 */
export function findContextFile(repoRoot: string): string | null {
  const contextFilenames = ["CONTEXT.md", "GLOSSARY.md"];

  for (const filename of contextFilenames) {
    const rootCandidate = path.join(repoRoot, filename);
    if (fs.existsSync(rootCandidate)) {
      return rootCandidate;
    }

    const docsCandidate = path.join(repoRoot, "docs", filename);
    if (fs.existsSync(docsCandidate)) {
      return docsCandidate;
    }
  }

  const srcDir = path.join(repoRoot, "src");
  if (fs.existsSync(srcDir)) {
    try {
      const entries = fs.readdirSync(srcDir, { withFileTypes: true });
      for (const entry of entries) {
        if (entry.isDirectory()) {
          for (const filename of contextFilenames) {
            const subCandidate = path.join(srcDir, entry.name, filename);
            if (fs.existsSync(subCandidate)) return subCandidate;
          }
        }
      }
    } catch {
      // Ignore
    }
  }

  return null;
}

/**
 * Checks whether issue tracking configuration exists in the target repository.
 * Accepted configurations:
 * 1. docs/agents/issue-tracker.md exists
 * 2. AGENTS.md exists and contains "## Agent skills"
 * 3. CLAUDE.md exists and contains "## Agent skills"
 */
function checkIssueTrackingConfig(repoRoot: string): boolean {
  const docsTracker = path.join(repoRoot, "docs", "agents", "issue-tracker.md");
  if (fs.existsSync(docsTracker)) {
    return true;
  }

  for (const configFile of ["AGENTS.md", "CLAUDE.md"]) {
    const configPath = path.join(repoRoot, configFile);
    if (fs.existsSync(configPath)) {
      try {
        const content = fs.readFileSync(configPath, "utf-8");
        if (/##\s+Agent\s+skills/i.test(content)) {
          return true;
        }
      } catch {
        // Ignore
      }
    }
  }

  return false;
}

/**
 * Checks if an ADR file is in accepted status.
 * ADRs without an explicit Status are considered accepted by default.
 * ADRs with status starting with superseded, deprecated, rejected, or proposed are considered non-accepted.
 */
export function isAdrAccepted(content: string): boolean {
  const statusMatch = content.match(/(?:^|\n)\s*\*{0,2}Status\*{0,2}\s*:\s*\*{0,2}([^\n\r]+)/i);
  if (!statusMatch) {
    return true;
  }
  const statusText = statusMatch[1].toLowerCase().trim();
  if (
    statusText.startsWith("superseded") ||
    statusText.startsWith("deprecated") ||
    statusText.startsWith("rejected") ||
    statusText.startsWith("proposed") ||
    statusText.startsWith("draft") ||
    statusText.startsWith("withdrawn")
  ) {
    return false;
  }
  return true;
}

/**
 * Validates that docs/adr/ exists and contains at least one accepted ADR.
 */
export function validateAdrPrerequisites(repoRoot: string): string[] {
  const errors: string[] = [];
  const adrDir = path.join(repoRoot, "docs", "adr");
  if (!fs.existsSync(adrDir)) {
    errors.push(
      "Missing architectural decision records: 'docs/adr/' directory not found at repository root. Target repositories must contain architectural decision records in docs/adr/."
    );
  } else {
    const acceptedAdrs = findAcceptedAdrFiles(repoRoot);
    if (acceptedAdrs.length === 0) {
      errors.push(
        "Missing accepted architectural decision records: 'docs/adr/' exists but contains no accepted ADR files. Target repositories must contain at least one accepted ADR file."
      );
    }
  }
  return errors;
}

/**
 * Discovers all accepted ADR files in docs/adr/.
 */
export function findAcceptedAdrFiles(repoRoot: string): string[] {
  const adrDir = path.join(repoRoot, "docs", "adr");
  if (!fs.existsSync(adrDir)) {
    return [];
  }
  try {
    const entries = fs.readdirSync(adrDir).filter((f) => f.endsWith(".md") && !f.toLowerCase().startsWith("readme"));
    const accepted: string[] = [];
    for (const entry of entries) {
      const fullPath = path.join(adrDir, entry);
      try {
        const content = fs.readFileSync(fullPath, "utf-8");
        if (isAdrAccepted(content)) {
          accepted.push(fullPath);
        }
      } catch {
        // Ignore unreadable files
      }
    }
    accepted.sort((a, b) => path.basename(a).localeCompare(path.basename(b), undefined, { numeric: true }));
    return accepted;
  } catch {
    return [];
  }
}

/**
 * Loads all accepted ADRs from docs/adr/ into a bundled markdown string.
 */
export function loadAcceptedAdrsBundle(repoRoot: string): string | undefined {
  const adrPaths = findAcceptedAdrFiles(repoRoot);
  if (adrPaths.length === 0) {
    return undefined;
  }
  const sections: string[] = [];
  for (const adrPath of adrPaths) {
    try {
      const filename = path.basename(adrPath);
      const content = fs.readFileSync(adrPath, "utf-8");
      sections.push(`### ${filename}\n\n${content}`);
    } catch {
      // Ignore
    }
  }
  return sections.length > 0 ? sections.join("\n\n---\n\n") : undefined;
}

/**
 * Validates repository workspace against domain standard prerequisites.
 */
export function validatePreflight(repoRoot: string, featureSlug: string): PreflightCheckResult {
  const errors: string[] = [];

  // 1. Validate spec presence
  const specPath = path.join(repoRoot, ".scratch", featureSlug, "spec.md");
  if (!fs.existsSync(specPath)) {
    errors.push(
      `Missing feature specification: expected '${path.relative(repoRoot, specPath)}' to exist in target repository. Please create the specification before executing assembly line stages.`
    );
  }

  // 2. Validate CONTEXT.md / GLOSSARY.md presence
  const contextPath = findContextFile(repoRoot);
  if (!contextPath) {
    errors.push(
      "Missing domain context documentation: 'CONTEXT.md' or 'GLOSSARY.md' not found at repository root or in domain paths. Please define the domain glossary in CONTEXT.md or GLOSSARY.md."
    );
  }

  // 3. Validate issue tracking configuration
  if (!checkIssueTrackingConfig(repoRoot)) {
    errors.push(
      "Missing issue tracking configuration: expected 'docs/agents/issue-tracker.md' or '## Agent skills' section in 'AGENTS.md' / 'CLAUDE.md'. Please configure local markdown issue tracking via /setup-matt-pocock-skills."
    );
  }

  // 4. Validate ADR presence and accepted status
  errors.push(...validateAdrPrerequisites(repoRoot));

  return {
    valid: errors.length === 0,
    errors,
  };
}

export interface PreflightOptions {
  tracker?: import("./tracker/types.ts").IssueTracker;
  trackerType?: import("./tracker/types.ts").TrackerType;
  issueId?: string;
  token?: string;
  owner?: string;
  repo?: string;
}

/**
 * Validates prerequisites asynchronously using the resolved IssueTracker (GitHub or Local).
 */
export async function validatePreflightAsync(
  repoRoot: string,
  featureSlug: string,
  options?: PreflightOptions
): Promise<PreflightCheckResult> {
  if (options?.tracker) {
    return options.tracker.validatePreflight(repoRoot, featureSlug, options?.issueId);
  }

  try {
    const { resolveIssueTracker } = await import("./tracker/factory.ts");
    const tracker = resolveIssueTracker({
      workspaceDir: repoRoot,
      featureSlug,
      trackerType: options?.trackerType,
      token: options?.token,
      owner: options?.owner,
      repo: options?.repo,
    });

    return await tracker.validatePreflight(repoRoot, featureSlug, options?.issueId);
  } catch (err: any) {
    if (err?.name === "GitHubAuthError" || (err && typeof err.message === "string" && err.message.includes("GitHub token"))) {
      return {
        valid: false,
        errors: [`Missing GitHub token: ${err.message}`],
      };
    }
    throw err;
  }
}

/**
 * Validates prerequisites asynchronously and throws an actionable PreflightError if any are missing.
 */
export async function assertPreflightAsync(
  repoRoot: string,
  featureSlug: string,
  options?: PreflightOptions
): Promise<void> {
  const result = await validatePreflightAsync(repoRoot, featureSlug, options);
  if (!result.valid) {
    throw new PreflightError(result.errors);
  }
}

/**
 * Validates prerequisites and throws an actionable PreflightError if any are missing.
 */
export function assertPreflight(repoRoot: string, featureSlug: string): void {
  const result = validatePreflight(repoRoot, featureSlug);
  if (!result.valid) {
    throw new PreflightError(result.errors);
  }
}


/**
 * Parses ticket identifier and numeric value from filename or header.
 */
function extractTicketIdAndSlug(fileName: string): { id: string; number: number; slug: string } {
  const base = path.basename(fileName, path.extname(fileName));
  const match = base.match(/^(\d+)(?:-(.*))?$/);
  if (match) {
    const id = match[1];
    const num = parseInt(match[1], 10);
    const slug = match[2] ?? "";
    return { id, number: num, slug };
  }
  return { id: base, number: 0, slug: base };
}

function cleanMarkdownValue(value: string): string {
  return value.trim().replace(/^[`*_]+|[`*_]+$/g, "").trim();
}

function normalizeStatus(rawStatus: string): string {
  const cleaned = cleanMarkdownValue(rawStatus).toLowerCase();
  const withoutAnnotations = cleaned.replace(/\(.*?\)/g, "").trim();
  return cleanMarkdownValue(withoutAnnotations);
}

/**
 * Parses blockers from the 'Blocked by:' line.
 */
function parseBlockedBy(rawBlockedBy: string): string[] {
  const cleaned = cleanMarkdownValue(rawBlockedBy).replace(/[\.;]+$/, "").trim();
  if (!cleaned || /^none(?:\s*\(.*?\))?[\.\s]*$/i.test(cleaned)) {
    return [];
  }

  const items = cleaned.split(",").map((s) => cleanMarkdownValue(s).replace(/[\.;]+$/, "").trim()).filter(Boolean);
  const blockerIds: string[] = [];

  for (const item of items) {
    if (/^none(?:\s*\(.*?\))?[\.\s]*$/i.test(item)) continue;
    // Match leading numbers (e.g. "01: Title" -> "01", "02" -> "02")
    const match = item.match(/^(\d+)/);
    if (match) {
      blockerIds.push(match[1]);
    } else {
      // Fallback: entire item token
      blockerIds.push(item);
    }
  }

  return blockerIds;
}

/**
 * Parses an individual markdown ticket file.
 */
export function parseTicket(filePath: string): Ticket {
  const content = fs.readFileSync(filePath, "utf-8");
  const fileName = path.basename(filePath);
  const { id: fileId, number: fileNum, slug } = extractTicketIdAndSlug(fileName);

  // Parse title: # NN: Title or # Title
  let title = slug;
  const titleMatch = content.match(/^#\s+(?:(?:\d+):\s*)?(.+)$/m);
  if (titleMatch) {
    title = cleanMarkdownValue(titleMatch[1]);
  }

  // Parse Status
  let status: TicketStatus = "open";
  const statusMatch = content.match(/(?:^|\n)\s*\*{0,2}Status\*{0,2}\s*:\s*\*{0,2}\s*([^\n\r]+)/i);
  if (statusMatch) {
    status = normalizeStatus(statusMatch[1]);
  }

  // Parse Blocked by
  let blockedBy: string[] = [];
  const blockedByMatch = content.match(/(?:^|\n)\s*\*{0,2}Blocked\s+by\*{0,2}\s*:\s*\*{0,2}\s*([^\n\r]+)/i);
  if (blockedByMatch) {
    blockedBy = parseBlockedBy(blockedByMatch[1]);
  }

  return {
    id: fileId,
    number: fileNum,
    slug,
    title,
    filePath,
    status,
    blockedBy,
  };
}

/**
 * Parses all ticket files in .scratch/<feature>/issues/ and returns them sorted by ticket number.
 */
export function parseTickets(repoRoot: string, featureSlug: string): Ticket[] {
  const issuesDir = path.join(repoRoot, ".scratch", featureSlug, "issues");
  if (!fs.existsSync(issuesDir)) {
    return [];
  }

  const files = fs.readdirSync(issuesDir).filter((f: string) => /^\d+(-.*)?\.md$/.test(f));
  const tickets: Ticket[] = [];

  for (const file of files) {
    const fullPath = path.join(issuesDir, file);
    try {
      const ticket = parseTicket(fullPath);
      tickets.push(ticket);
    } catch {
      // Ignore unparseable files
    }
  }

  tickets.sort((a, b) => a.number - b.number);
  return tickets;
}

/**
 * Normalizes ticket identifier for comparison (e.g. "01" and "1" match).
 */
function normalizeId(id: string): string {
  const num = parseInt(id, 10);
  if (!isNaN(num)) {
    return String(num);
  }
  return id.toLowerCase().trim();
}

/**
 * Identifies open and unblocked tickets on the frontier in numerical order.
 * A ticket is open if status is 'ready-for-agent' or 'open' (not 'resolved', 'claimed', 'ready-for-human').
 * A ticket is unblocked if every dependency in blockedBy has status 'resolved'.
 */
export function getFrontierTickets(tickets: Ticket[]): Ticket[] {
  const ticketMap = new Map<string, Ticket>();
  for (const t of tickets) {
    ticketMap.set(t.id, t);
    ticketMap.set(normalizeId(t.id), t);
  }

  const frontier: Ticket[] = [];

  for (const ticket of tickets) {
    // Only open tickets can be on the frontier
    const isOpen = ticket.status === "ready-for-agent" || ticket.status === "open";
    if (!isOpen) {
      continue;
    }

    // Check if unblocked
    let isUnblocked = true;
    for (const blockerId of ticket.blockedBy) {
      const blocker = ticketMap.get(blockerId) ?? ticketMap.get(normalizeId(blockerId));
      if (!blocker || blocker.status !== "resolved") {
        isUnblocked = false;
        break;
      }
    }

    if (isUnblocked) {
      frontier.push(ticket);
    }
  }

  frontier.sort((a, b) => a.number - b.number);
  return frontier;
}

/**
 * Returns the next open, unblocked ticket on the frontier (first by number wins), or null if none.
 */
export function getNextFrontierTicket(tickets: Ticket[]): Ticket | null {
  const frontier = getFrontierTickets(tickets);
  return frontier.length > 0 ? frontier[0] : null;
}
