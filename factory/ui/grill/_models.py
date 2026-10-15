"""Data structures, dataclasses, enums, and constants for the Grilling Assistant."""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

OPENCODE_GO_DEFAULT_URL = "https://opencode.ai/zen/go/v1"
OPENCODE_GO_DEFAULT_MODEL = "deepseek-v4.1-flash"

PromptArchetype = Literal["deletion", "component_modification", "styling", "new_feature"]


@dataclass
class GrillQuestion:
    """Represents a structured grilling question on the requirement frontier."""

    id: str
    title: str
    question: str
    recommended: str
    options: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def format_markdown(self) -> str:
        options_text = ""
        if self.options:
            options_text = "\n" + "\n".join(f"- {opt}" for opt in self.options)
        return f"❓ **{self.id}** - **{self.title}**: {self.question}{options_text}\n\n➡️ {self.recommended}"


@dataclass
class DraftADR:
    """Represents an Architectural Decision Record drafted during grilling."""

    title: str
    filename: str
    content: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DomainTermSharpening:
    """Represents a term clarified against CONTEXT.md."""

    fuzzy_term: str
    canonical_term: str
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CodebaseGroundingContext:
    """Encapsulates autonomous codebase facts discovered for grilling."""

    branch: str = "main"
    file_tree: list[str] = field(default_factory=list)
    candidate_contents: dict[str, str] = field(default_factory=dict)


@dataclass
class GrillTurnResult:
    """Structured response for a conversational grilling turn."""

    type: Literal["grill_round", "ready_for_approval", "error"]
    round: int = 1
    questions: list[GrillQuestion] = field(default_factory=list)
    formatted_text: str = ""
    summary: str = ""
    plan: str | None = None
    draft_adr: DraftADR | None = None
    sharpened_terms: list[DomainTermSharpening] = field(default_factory=list)
    context_update: str | None = None
    error_message: str | None = None
    error_details: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "round": self.round,
            "questions": [q.to_dict() if isinstance(q, GrillQuestion) else q for q in self.questions],
            "formatted_text": self.formatted_text,
            "summary": self.summary,
            "plan": self.plan,
            "draft_adr": self.draft_adr.to_dict() if isinstance(self.draft_adr, DraftADR) else self.draft_adr,
            "sharpened_terms": [t.to_dict() if isinstance(t, DomainTermSharpening) else t for t in self.sharpened_terms],
            "context_update": self.context_update,
            "error_message": self.error_message,
            "error_details": self.error_details,
        }
