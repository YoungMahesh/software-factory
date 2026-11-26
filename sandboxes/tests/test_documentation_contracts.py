"""Keep current user documentation aligned with executable public interfaces."""

from pathlib import Path
import re
import tomllib
from urllib.parse import unquote, urlsplit

import pytest

from sandbox.app_deploy._cli import build_deploy_app_parser
from sandbox.caddy_deploy import build_caddy_parser
from sandbox.cli import create_parser as launch_parser
from sandbox.dashboard_deploy import build_dashboard_deploy_parser
from sandbox.function import web_app
from sandbox.infra_deploy import create_parser as infra_parser
from scripts.create_app import create_parser as scaffold_parser


ROOT = Path(__file__).resolve().parents[2]
CLI_REFERENCE = ROOT / "docs/guides/cli.md"
CONTROL_PLANE_GUIDE = ROOT / "docs/guides/control-plane.md"


@pytest.mark.parametrize(
    ("parser_factory", "start", "end"),
    [
        (launch_parser, "## Command Options", "## Common Usage Examples"),
        (infra_parser, "## Resource Plane & VPS", "## Database & Storage"),
        (build_dashboard_deploy_parser, "### `modal-sandbox infra dashboard`", "## Database & Storage"),
        (scaffold_parser, "## Application Scaffolding", "## Deploying Hosted Apps"),
        (build_deploy_app_parser, "## Deploying Hosted Apps", "## Host Ingress"),
        (build_caddy_parser, "## Host Ingress", None),
    ],
)
def test_cli_options_have_reference_entries(parser_factory, start, end):
    reference = CLI_REFERENCE.read_text().split(start, 1)[1]
    if end:
        reference = reference.split(end, 1)[0]
    documented = set(re.findall(r"--[a-z][a-z0-9-]*", reference))
    missing = []
    for action in parser_factory()._actions:
        options = [s for s in action.option_strings if s.startswith("--") and s != "--help"]
        if options and not documented.intersection(options):
            missing.append(options[0])
    assert not missing, f"Missing options in {start}: {missing}"


def test_installed_commands_are_documented():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    reference = CLI_REFERENCE.read_text()
    missing = [name for name in project["project"]["scripts"] if name not in reference]
    assert not missing, f"Installed commands missing from CLI reference: {missing}"


def test_mcp_reference_uses_registered_tool_names():
    source = (ROOT / "resource-plane/apps/web/mcp/server.ts").read_text()
    tools = set(re.findall(r'server\.registerTool\(\s*"([^"]+)"', source))
    assert tools, "No MCP tool registrations found"
    for relative in ("docs/architecture/resource-plane.md", "resource-plane/README.md"):
        reference = (ROOT / relative).read_text()
        documented = set(re.findall(r"\| `([a-z_]+)` \|", reference))
        assert documented == tools, f"MCP reference differs from registered tools: {relative}"


def test_current_documentation_local_links_resolve():
    # Historical ADRs retain their original context and paths. Symlinked site
    # pages are checked through their canonical root documents instead.
    sources = [
        ROOT / name
        for name in (
            "AGENTS.md", "readme.md", "CONTRIBUTING.md", "SECURITY.md", "GLOSSARY.md",
            "app-template/README.md", "dashboard/README.md", "resource-plane/README.md", "resource-plane/GLOSSARY.md",
        )
    ]
    sources.extend(
        path for path in (ROOT / "docs").rglob("*.md")
        if "adr" not in path.relative_to(ROOT / "docs").parts and not path.is_symlink()
    )
    broken = []
    for source in sources:
        for target in re.findall(r"\]\(([^\s)]+)", source.read_text()):
            parsed = urlsplit(target)
            if parsed.scheme == "file":
                broken.append(f"{source.relative_to(ROOT)}: machine-local URL {target}")
            elif not parsed.scheme and parsed.path:
                destination = source.parent / unquote(parsed.path)
                if not destination.exists():
                    broken.append(f"{source.relative_to(ROOT)}: {target}")
    assert not broken, "Unresolved documentation links:\n" + "\n".join(broken)


def test_all_adrs_are_indexed_and_in_nav():
    adrs = sorted(
        path.name
        for path in (ROOT / "docs/adr").glob("*.md")
        if path.name != "index.md"
    )
    adr_index = (ROOT / "docs/adr/index.md").read_text()
    mkdocs_nav = (ROOT / "mkdocs.yml").read_text()
    missing_from_index = [name for name in adrs if name not in adr_index]
    missing_from_nav = [name for name in adrs if name not in mkdocs_nav]
    assert not missing_from_index, f"ADRs missing from docs/adr/index.md: {missing_from_index}"
    assert not missing_from_nav, f"ADRs missing from mkdocs.yml nav: {missing_from_nav}"


def test_control_plane_api_routes_match_openapi():
    openapi_routes = {
        (method.upper(), path)
        for path, item in web_app.openapi()["paths"].items()
        for method in item
    }
    section = CONTROL_PLANE_GUIDE.read_text().split("## API routes", 1)[1]
    documented = {
        (method.upper(), path)
        for method, path in re.findall(r"^\|\s*`([A-Z]+)`\s*\|\s*`([^`]+)`\s*\|", section, re.MULTILINE)
    }
    assert documented == openapi_routes, (
        f"Control plane API routes mismatch: missing={sorted(openapi_routes - documented)}, "
        f"extra={sorted(documented - openapi_routes)}"
    )
