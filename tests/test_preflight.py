import shutil
import tempfile
from pathlib import Path
import pytest

from factory.preflight import (
    PreflightError,
    validate_preflight,
    assert_preflight,
    parse_ticket,
    parse_tickets,
    get_frontier_tickets,
    get_next_frontier_ticket,
)


@pytest.fixture
def temp_repo():
    tmp_dir = tempfile.mkdtemp(prefix="sf-py-test-repo-")
    yield Path(tmp_dir)
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_validate_preflight_missing_spec(temp_repo: Path):
    (temp_repo / "CONTEXT.md").write_text("# Domain Context")
    (temp_repo / "AGENTS.md").write_text("# Agents\n\n## Agent skills\n")

    result = validate_preflight(temp_repo, "test-feature")
    assert not result.valid
    assert any(".scratch/test-feature/spec.md" in err for err in result.errors)


def test_validate_preflight_missing_context(temp_repo: Path):
    feat_dir = temp_repo / ".scratch" / "test-feature"
    feat_dir.mkdir(parents=True)
    (feat_dir / "spec.md").write_text("# Spec")
    (temp_repo / "AGENTS.md").write_text("## Agent skills\n")

    result = validate_preflight(temp_repo, "test-feature")
    assert not result.valid
    assert any("CONTEXT.md" in err for err in result.errors)


def test_validate_preflight_context_in_domain_path(temp_repo: Path):
    feat_dir = temp_repo / ".scratch" / "test-feature"
    feat_dir.mkdir(parents=True)
    (feat_dir / "spec.md").write_text("# Spec")
    domain_dir = temp_repo / "src" / "domain"
    domain_dir.mkdir(parents=True)
    (domain_dir / "CONTEXT.md").write_text("# Context")
    (temp_repo / "AGENTS.md").write_text("## Agent skills\n")

    result = validate_preflight(temp_repo, "test-feature")
    assert result.valid
    assert len(result.errors) == 0


def test_validate_preflight_missing_issue_tracker_config(temp_repo: Path):
    feat_dir = temp_repo / ".scratch" / "test-feature"
    feat_dir.mkdir(parents=True)
    (feat_dir / "spec.md").write_text("# Spec")
    (temp_repo / "CONTEXT.md").write_text("# Context")

    result = validate_preflight(temp_repo, "test-feature")
    assert not result.valid
    assert any("issue tracking configuration" in err for err in result.errors)


def test_validate_preflight_accepts_docs_issue_tracker(temp_repo: Path):
    feat_dir = temp_repo / ".scratch" / "test-feature"
    feat_dir.mkdir(parents=True)
    (feat_dir / "spec.md").write_text("# Spec")
    (temp_repo / "CONTEXT.md").write_text("# Context")
    docs_dir = temp_repo / "docs" / "agents"
    docs_dir.mkdir(parents=True)
    (docs_dir / "issue-tracker.md").write_text("# Issue tracker")

    result = validate_preflight(temp_repo, "test-feature")
    assert result.valid
    assert len(result.errors) == 0


def test_validate_preflight_accepts_claude_agent_skills(temp_repo: Path):
    feat_dir = temp_repo / ".scratch" / "test-feature"
    feat_dir.mkdir(parents=True)
    (feat_dir / "spec.md").write_text("# Spec")
    (temp_repo / "CONTEXT.md").write_text("# Context")
    (temp_repo / "CLAUDE.md").write_text("# Instructions\n\n## Agent skills\n")

    result = validate_preflight(temp_repo, "test-feature")
    assert result.valid
    assert len(result.errors) == 0


def test_assert_preflight_raises_actionable_error(temp_repo: Path):
    with pytest.raises(PreflightError) as exc_info:
        assert_preflight(temp_repo, "test-feature")
    err_msg = str(exc_info.value)
    assert ".scratch/test-feature/spec.md" in err_msg
    assert "CONTEXT.md" in err_msg


def test_parse_ticket_headers_and_blockers(temp_repo: Path):
    ticket_file = temp_repo / "01-sample-task.md"
    ticket_file.write_text(
        "# 01: Sample Task\n\n"
        "**What to build:** Test task.\n\n"
        "**Blocked by:** None (can start immediately)\n\n"
        "**Status:** ready-for-agent\n\n"
        "- [ ] Item 1\n"
    )

    ticket = parse_ticket(ticket_file)
    assert ticket.id == "01"
    assert ticket.number == 1
    assert ticket.title == "Sample Task"
    assert ticket.status == "ready-for-agent"
    assert ticket.blocked_by == []


def test_parse_ticket_multiple_blockers(temp_repo: Path):
    ticket_file = temp_repo / "03-third-task.md"
    ticket_file.write_text(
        "# 03: Third Task\n\n"
        "**Blocked by:** 01: Sample Task, 02: Second Task\n\n"
        "**Status:** ready-for-agent\n"
    )

    ticket = parse_ticket(ticket_file)
    assert ticket.id == "03"
    assert ticket.number == 3
    assert ticket.title == "Third Task"
    assert ticket.blocked_by == ["01", "02"]


def test_parse_tickets_and_frontier(temp_repo: Path):
    issues_dir = temp_repo / ".scratch" / "feature-x" / "issues"
    issues_dir.mkdir(parents=True)

    (issues_dir / "01-first.md").write_text(
        "# 01: First\n\nBlocked by: None\nStatus: ready-for-agent\n"
    )
    (issues_dir / "02-second.md").write_text(
        "# 02: Second\n\nBlocked by: None\nStatus: ready-for-agent\n"
    )
    (issues_dir / "03-third.md").write_text(
        "# 03: Third\n\nBlocked by: 01, 02\nStatus: ready-for-agent\n"
    )
    (issues_dir / "04-fourth.md").write_text(
        "# 04: Fourth\n\nBlocked by: None\nStatus: claimed\n"
    )

    tickets = parse_tickets(temp_repo, "feature-x")
    assert len(tickets) == 4
    assert [t.id for t in tickets] == ["01", "02", "03", "04"]

    frontier = get_frontier_tickets(tickets)
    assert [t.id for t in frontier] == ["01", "02"]

    # When 01 is resolved, frontier is [02]
    tickets[0].status = "resolved"
    assert [t.id for t in get_frontier_tickets(tickets)] == ["02"]

    # When 02 is also resolved, frontier is [03]
    tickets[1].status = "resolved"
    assert [t.id for t in get_frontier_tickets(tickets)] == ["03"]

    # Test get_next_frontier_ticket
    next_ticket = get_next_frontier_ticket(tickets)
    assert next_ticket is not None
    assert next_ticket.id == "03"

    # Non-ticket files (like README.md) should be ignored
    (issues_dir / "README.md").write_text("# Issues Tracker README\n")
    tickets_with_readme = parse_tickets(temp_repo, "feature-x")
    assert len(tickets_with_readme) == 4
    assert not any(t.id == "README" for t in tickets_with_readme)


def test_parse_ticket_annotated_and_backticks(temp_repo: Path):
    ticket_file = temp_repo / "05-annotated.md"
    ticket_file.write_text(
        "# 05: Annotated Task\n\n"
        "Status: `ready-for-agent` (ready to claim)\n"
        "Blocked by: None\n"
    )
    ticket = parse_ticket(ticket_file)
    assert ticket.status == "ready-for-agent"


def test_smoke_software_factory_repo():
    repo_root = Path(__file__).resolve().parent.parent
    result = validate_preflight(repo_root, "software-factory")
    assert result.valid, f"Validation errors: {result.errors}"
    assert len(result.errors) == 0

    tickets = parse_tickets(repo_root, "software-factory")
    assert len(tickets) >= 6
    assert tickets[0].id == "01"
    assert tickets[0].status in ("ready-for-agent", "resolved")

    frontier = get_frontier_tickets(tickets)
    # Since 01 is resolved, 02 is on the frontier
    assert any(t.id == "02" for t in frontier)
