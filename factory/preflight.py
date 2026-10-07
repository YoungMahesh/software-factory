"""Pre-flight Guard and Issue Tracker Parser.

Validates target repository prerequisites for agent workflows:
1. Feature specification (.scratch/<feature>/spec.md)
2. Domain context documentation (CONTEXT.md at root or in domain paths)
3. Issue tracking configuration (docs/agents/issue-tracker.md or ## Agent skills in AGENTS.md/CLAUDE.md)

Parses local markdown issue tracker tickets (.scratch/<feature>/issues/) and discovers
open, unblocked tickets on the frontier.
"""

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Literal

TicketStatus = Literal[
    "open",
    "ready-for-agent",
    "claimed",
    "resolved",
    "ready-for-human",
] | str


@dataclass
class PreflightResult:
    valid: bool
    errors: list[str]


class PreflightError(Exception):
    """Raised when repository prerequisites are missing."""

    def __init__(self, errors: list[str]) -> None:
        message = (
            "Pre-flight Guard validation failed:\n"
            + "\n".join(f"  - {err}" for err in errors)
        )
        super().__init__(message)
        self.errors = errors


@dataclass
class Ticket:
    id: str
    number: int
    slug: str
    title: str
    file_path: Path
    status: TicketStatus
    blocked_by: list[str]


def _clean_markdown_value(value: str) -> str:
    cleaned = value.strip()
    return re.sub(r"^[`*_]+|[`*_]+$", "", cleaned).strip()


def _normalize_status(raw_status: str) -> str:
    cleaned = _clean_markdown_value(raw_status).lower()
    # Remove parenthetical comments or annotations (e.g., 'resolved (merged)' -> 'resolved')
    cleaned = re.sub(r"\(.*?\)", "", cleaned).strip()
    return _clean_markdown_value(cleaned)


def find_context_file(repo_root: Path) -> Path | None:
    """Finds CONTEXT.md at repo root or canonical domain paths (docs/CONTEXT.md, src/*/CONTEXT.md)."""
    root_context = repo_root / "CONTEXT.md"
    if root_context.is_file():
        return root_context

    docs_context = repo_root / "docs" / "CONTEXT.md"
    if docs_context.is_file():
        return docs_context

    src_dir = repo_root / "src"
    if src_dir.is_dir():
        try:
            for child in src_dir.iterdir():
                if child.is_dir():
                    sub_file = child / "CONTEXT.md"
                    if sub_file.is_file():
                        return sub_file
        except OSError:
            pass

    return None


def check_issue_tracking_config(repo_root: Path) -> bool:
    """Checks whether issue tracking configuration exists in the target repository.

    Accepted configurations:
    1. docs/agents/issue-tracker.md exists
    2. AGENTS.md contains '## Agent skills'
    3. CLAUDE.md contains '## Agent skills'
    """
    docs_tracker = repo_root / "docs" / "agents" / "issue-tracker.md"
    if docs_tracker.is_file():
        return True

    for config_filename in ("AGENTS.md", "CLAUDE.md"):
        config_path = repo_root / config_filename
        if config_path.is_file():
            try:
                content = config_path.read_text(encoding="utf-8")
                if re.search(r"##\s+Agent\s+skills", content, re.IGNORECASE):
                    return True
            except OSError:
                pass

    return False


def validate_preflight(repo_root: Path | str, feature_slug: str) -> PreflightResult:
    """Validates target repository workspace against domain standard prerequisites."""
    root = Path(repo_root).resolve()
    errors: list[str] = []

    # 1. Validate spec presence
    spec_path = root / ".scratch" / feature_slug / "spec.md"
    if not spec_path.is_file():
        rel_spec = f".scratch/{feature_slug}/spec.md"
        errors.append(
            f"Missing feature specification: expected '{rel_spec}' to exist in target repository. "
            "Please create the specification before executing assembly line stages."
        )

    # 2. Validate CONTEXT.md presence
    context_path = find_context_file(root)
    if not context_path:
        errors.append(
            "Missing domain context documentation: 'CONTEXT.md' not found at repository root or in domain paths. "
            "Please define the domain glossary in CONTEXT.md."
        )

    # 3. Validate issue tracking configuration
    if not check_issue_tracking_config(root):
        errors.append(
            "Missing issue tracking configuration: expected 'docs/agents/issue-tracker.md' "
            "or '## Agent skills' section in 'AGENTS.md' / 'CLAUDE.md'. "
            "Please configure local markdown issue tracking via /setup-matt-pocock-skills."
        )

    return PreflightResult(
        valid=len(errors) == 0,
        errors=errors,
    )


def assert_preflight(repo_root: Path | str, feature_slug: str) -> None:
    """Validates prerequisites and raises PreflightError if any are missing."""
    result = validate_preflight(repo_root, feature_slug)
    if not result.valid:
        raise PreflightError(result.errors)


def _extract_ticket_id_and_slug(file_name: str) -> tuple[str, int, str]:
    stem = Path(file_name).stem
    match = re.match(r"^(\d+)(?:-(.*))?$", stem)
    if match:
        ticket_id = match.group(1)
        num = int(ticket_id)
        slug = match.group(2) or ""
        return ticket_id, num, slug
    return stem, 0, stem


def _parse_blocked_by(raw_blocked_by: str) -> list[str]:
    cleaned = _clean_markdown_value(raw_blocked_by)
    if not cleaned or re.match(r"^none(?:\s*\(.*\))?$", cleaned, re.IGNORECASE):
        return []

    tokens = [
        _clean_markdown_value(tok)
        for tok in cleaned.split(",")
        if _clean_markdown_value(tok)
    ]
    blockers: list[str] = []

    for tok in tokens:
        if re.match(r"^none(?:\s*\(.*\))?$", tok, re.IGNORECASE):
            continue
        # Extract leading numeric ID, e.g. "01: Pre-flight Guard..." -> "01"
        match = re.match(r"^(\d+)", tok)
        if match:
            blockers.append(match.group(1))
        else:
            blockers.append(tok)

    return blockers


def parse_ticket(file_path: Path | str) -> Ticket:
    """Parses a markdown ticket file into a structured Ticket object."""
    path = Path(file_path).resolve()
    content = path.read_text(encoding="utf-8")
    ticket_id, number, slug = _extract_ticket_id_and_slug(path.name)

    # Title: # NN: Title or # Title
    title = slug
    title_match = re.search(r"^#\s+(?:(?:\d+):\s*)?(.+)$", content, re.MULTILINE)
    if title_match:
        title = _clean_markdown_value(title_match.group(1))

    # Status: Status: <val> or **Status:** <val>
    status: TicketStatus = "open"
    status_match = re.search(
        r"(?:^|\n)\s*\*{0,2}Status\*{0,2}\s*:\s*\*{0,2}\s*([^\n\r]+)",
        content,
        re.IGNORECASE,
    )
    if status_match:
        status = _normalize_status(status_match.group(1))

    # Blocked by: Blocked by: <val> or **Blocked by:** <val>
    blocked_by: list[str] = []
    blocked_match = re.search(
        r"(?:^|\n)\s*\*{0,2}Blocked\s+by\*{0,2}\s*:\s*\*{0,2}\s*([^\n\r]+)",
        content,
        re.IGNORECASE,
    )
    if blocked_match:
        blocked_by = _parse_blocked_by(blocked_match.group(1))

    return Ticket(
        id=ticket_id,
        number=number,
        slug=slug,
        title=title,
        file_path=path,
        status=status,
        blocked_by=blocked_by,
    )


def parse_tickets(repo_root: Path | str, feature_slug: str) -> list[Ticket]:
    """Scans and parses tickets under .scratch/<feature>/issues/ matching NN-*.md."""
    root = Path(repo_root).resolve()
    issues_dir = root / ".scratch" / feature_slug / "issues"
    if not issues_dir.is_dir():
        return []

    tickets: list[Ticket] = []
    for issue_file in sorted(issues_dir.glob("*.md")):
        # Only parse files conforming to NN-<slug>.md or numbered markdown files
        if not re.match(r"^\d+(-.*)?\.md$", issue_file.name):
            continue
        try:
            tickets.append(parse_ticket(issue_file))
        except Exception:
            continue

    tickets.sort(key=lambda t: t.number)
    return tickets


def _normalize_id(ticket_id: str) -> str:
    try:
        return str(int(ticket_id))
    except ValueError:
        return ticket_id.strip().lower()


def get_frontier_tickets(tickets: list[Ticket]) -> list[Ticket]:
    """Identifies open and unblocked tickets on the frontier in numerical order.

    A ticket is open if its status is 'ready-for-agent' or 'open'.
    A ticket is unblocked if every dependency in blocked_by has status 'resolved'.
    """
    ticket_map: dict[str, Ticket] = {}
    for t in tickets:
        ticket_map[t.id] = t
        ticket_map[_normalize_id(t.id)] = t

    frontier: list[Ticket] = []

    for ticket in tickets:
        # Must be open / ready-for-agent
        if ticket.status not in ("ready-for-agent", "open"):
            continue

        # Check if unblocked
        is_unblocked = True
        for blocker_id in ticket.blocked_by:
            blocker = ticket_map.get(blocker_id) or ticket_map.get(
                _normalize_id(blocker_id)
            )
            if not blocker or blocker.status != "resolved":
                is_unblocked = False
                break

        if is_unblocked:
            frontier.append(ticket)

    frontier.sort(key=lambda t: t.number)
    return frontier


def get_next_frontier_ticket(tickets: list[Ticket]) -> Ticket | None:
    """Returns the next open, unblocked ticket on the frontier (first by number wins), or None."""
    frontier = get_frontier_tickets(tickets)
    return frontier[0] if frontier else None
