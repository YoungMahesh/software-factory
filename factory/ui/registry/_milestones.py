"""Milestone pattern regexes and stage transition detectors for pipeline and preview logs."""

import re
from factory.ui.registry._models import JobStage, PreviewStage

STAGE_PATTERNS = [
    (re.compile(r"Pre-flight Guard Check|assertPreflight|Stage 0", re.IGNORECASE), JobStage.PREFLIGHT),
    (re.compile(r"Stage 1: Planner Agent|runPlannerAgent|Planning implementation", re.IGNORECASE), JobStage.PLANNER),
    (re.compile(r"Stage 2: Coder Agent|runCoderAgent|Coding implementation", re.IGNORECASE), JobStage.CODER),
    (re.compile(r"Stage 3: Deterministic Verifier|verifyWorkspace|Deterministic Verification", re.IGNORECASE), JobStage.VERIFIER),
    (re.compile(r"Stage 4: Reviewer Agent|runReviewerAgent|Reviewing diff", re.IGNORECASE), JobStage.REVIEWER),
    (re.compile(r"Assembly line pipeline completed successfully|IN-CONTAINER ASSEMBLY LINE PIPELINE PASSED", re.IGNORECASE), JobStage.COMPLETED),
    (re.compile(r"active serving keep-alive state|Dev server running with PID|Launching Dev Preview Keep-Alive Daemon", re.IGNORECASE), JobStage.SERVING),
]

PREVIEW_COMPILATION_ERROR_PATTERN = re.compile(
    r"\[vite:esbuild\]|\[vite\] Internal server error|Failed to compile|SyntaxError:|Compilation failed|error when starting dev server",
    re.IGNORECASE,
)

PREVIEW_STAGE_PATTERNS = [
    (
        re.compile(
            r"PREVIEW_STAGE:SERVING|ready in \d+|Local:\s+http|Network:\s+http|Dev server (?:running|started) on port|started on port",
            re.IGNORECASE,
        ),
        PreviewStage.SERVING,
    ),
    (
        re.compile(
            r"PREVIEW_STAGE:STARTING_DEV|Launching Dev Preview Keep-Alive Daemon|Container entering active serving keep-alive state|pnpm dev|VITE v|vite v|Dev server running with PID",
            re.IGNORECASE,
        ),
        PreviewStage.STARTING_DEV,
    ),
    (
        re.compile(
            r"PREVIEW_STAGE:INSTALLING_DEPS|Installing target repository dependencies|Installing dependencies|pnpm install|npm install|Packages: \+|Progress: resolved",
            re.IGNORECASE,
        ),
        PreviewStage.INSTALLING_DEPS,
    ),
]
