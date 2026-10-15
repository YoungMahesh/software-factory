"""ADR metadata synthesis, sequential resolution, and markdown plan generation."""

from pathlib import Path
import re
from factory.ui.grill._models import DraftADR, GrillQuestion, PromptArchetype


def slugify(text: str) -> str:
    """Converts a phrase into a clean URL-friendly kebab-case slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-") or "feature-decision"


def compute_next_adr_metadata(
    repo: str,
    prompt: str,
    existing_adrs: list[str] | None = None,
) -> tuple[int, str, str]:
    """Computes next sequential ADR number, slug, and filename."""
    highest_num = 1
    if existing_adrs:
        for adr in existing_adrs:
            m = re.match(r"^(\d{4})-", Path(adr).name)
            if m:
                highest_num = max(highest_num, int(m.group(1)))

    next_num = highest_num + 1
    words = [w for w in prompt.split() if w.lower() not in {"build", "add", "create", "make", "an", "a", "the", "with"}]
    core_title = " ".join(words[:4]).title() or "Architectural Specification"
    slug = slugify(core_title)
    filename = f"docs/adr/{next_num:04d}-{slug}.md"
    title = f"{next_num:04d}: {core_title}"
    return next_num, title, filename


def format_questions_markdown(questions: list[GrillQuestion]) -> str:
    """Formats a list of GrillQuestion instances into canonical grilling markdown."""
    return "\n\n---\n\n".join(q.format_markdown() for q in questions)


def synthesize_mock_plan_and_adr(
    repo: str,
    clean_title: str,
    effective_prompt: str,
    archetype: PromptArchetype,
    existing_adrs: list[str],
) -> tuple[str, str, str, DraftADR | None]:
    """Generates plan, summary, formatted_text, and optional draft ADR for settled mock turns."""
    draft_adr: DraftADR | None = None

    if archetype == "deletion":
        plan = f"""# Implementation Plan: {clean_title}

1. **Target Component**: Locate and remove specified elements in existing component (e.g. `app/components/Footer.tsx`).
2. **Layout Reflow**: Adjust flexbox/grid containers and padding to ensure clean visual flow without residual whitespace.
3. **Asset Pruning**: Remove unused icon imports, attributes, and dead references.
4. **Verification**: Verify component renders cleanly and tests pass.
"""
        summary = "Deletion scope confirmed and layout reflow requirements settled. Ready for build approval."
        formatted_text = f"### Finalized Implementation Plan\n\n{plan}"

    elif archetype == "component_modification":
        plan = f"""# Implementation Plan: {clean_title}

1. **Component Modification**: Update existing component logic and markup in `app/components/`.
2. **Props & State**: Adjust localized component props and state cleanly.
3. **Visual Alignment**: Maintain consistent layout, design tokens, and accessibility.
4. **Verification**: Verify component behavior and test suite pass without regressions.
"""
        summary = "Component modification scope clarified and requirements aligned. Ready for build approval."
        formatted_text = f"### Finalized Implementation Plan\n\n{plan}"

    elif archetype == "styling":
        plan = f"""# Implementation Plan: {clean_title}

1. **Styling Adjustments**: Apply responsive Tailwind CSS utility classes to target elements.
2. **Visual Consistency**: Verify color contrast, padding, and layout across breakpoints.
3. **Accessibility**: Ensure interactive elements maintain accessible focus states and contrast ratios.
4. **Verification**: Verify visual appearance and responsive layout in preview.
"""
        summary = "Styling requirements and design tokens aligned. Ready for build approval."
        formatted_text = f"### Finalized Implementation Plan\n\n{plan}"

    else:
        num, title, filename = compute_next_adr_metadata(repo, effective_prompt, existing_adrs)
        feature_slug = slugify(effective_prompt)
        content = f"""# {title}

**Status**: Proposed

To implement {effective_prompt} within {repo}, we decided to adopt type-safe file routing and client state caching conforming to the target application domain context.

## Considered Options

- **External Serverless Storage / Database**: Rejected because target applications are single-page frontend applications with client-first state.
- **In-Memory Client State with TanStack Query**: Accepted to maintain fast reactivity, offline resilience, and zero backend maintenance.

## Consequences

- Implemented under `app/routes/{feature_slug}.tsx`.
- State managed strictly through Client State primitives without external database dependencies.
- Styled using responsive Tailwind CSS utility tokens.
"""
        draft_adr = DraftADR(title=title, filename=filename, content=content)
        plan = f"""# Implementation Plan: {title}

1. **Route Hierarchy**: Create new route `app/routes/{feature_slug}.tsx` with typed loader and params.
2. **Client State**: Manage UI and domain state using React primitives and TanStack Query cache.
3. **Responsive UI**: Construct clean, accessible components styled with Tailwind CSS tokens.
4. **Architectural Verification**: Ensure code adheres strictly to `{filename}` and `CONTEXT.md`.
"""
        summary = "Requirements clarified, domain terminology aligned with CONTEXT.md, and draft ADR synthesized. Ready for build approval."
        formatted_text = f"### Finalized Implementation Plan\n\n{plan}\n\n**Draft ADR Ready**: [{filename}](#adr-preview)"

    return plan, summary, formatted_text, draft_adr
