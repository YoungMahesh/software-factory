# Pi Agent Harness and Stage Specialization

To execute software factory jobs reliably inside ephemeral Modal sandboxes, we decided to adopt the Pi Agent SDK (`@earendil-works/pi-agent-core`) as the in-sandbox execution harness, enforcing strict least-privilege role boundaries across the assembly line (read-only Planner, read-write-bash Coder, deterministic non-agentic Verifier, and read-only Reviewer) powered by a homogeneous flagship model, and delivering verified code to a dedicated remote feature branch (`factory/<feature>-<issue>`).

## Considered Options

- **Bespoke Python Agent Runner**: Write custom tool-calling and diff-applying loops in Python. Rejected because building robust multi-turn file editing, diffing, and shell process sandboxing from scratch is error-prone and reinvents established primitives.
- **Vercel AI SDK**: Use Vercel's `ai` SDK. Rejected because while excellent for generic LLM tool calling, it lacks pre-built coding tools (file editing, ast/diff patchers, terminal execution) which would have to be written manually.
- **Uniform Agent Permissions Across All Stages**: Give all stages full write and bash access. Rejected because letting Planners or Reviewers edit files or run arbitrary commands introduces scope creep and risks LLM-hallucinated test passes; deterministic test execution and read-only gates guarantee objectivity.
- **Heterogeneous Model Tiering**: Split models into fast coder and deep reviewer. Rejected in favor of a homogeneous flagship model across all stages to guarantee consistent reasoning depth, eliminate failure modes caused by weaker coding models, and simplify provider credential configuration.

## Consequences

- In-sandbox assembly line stages are orchestrated via TypeScript scripts utilizing `@earendil-works/pi-agent-core` and `@earendil-works/pi-ai` on the pre-baked Node.js 24 runtime.
- The Planner and Reviewer stages operate strictly read-only.
- The Verifier stage runs as a deterministic execution script with zero LLM intervention.
- The Coder has full edit and bash permissions to write code and test cases.
- All stages use the same configured flagship model.
- Upon passing all quality gates, the sandbox pushes branch `factory/<feature>-<issue>` to the target remote using the decrypted `GH_TOKEN`.
