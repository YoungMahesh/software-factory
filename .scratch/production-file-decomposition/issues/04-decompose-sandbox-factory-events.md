# 04: Decompose sandbox/factory/events.ts

**What to build:**
Decompose `sandbox/factory/events.ts` (1,164 physical lines) into a cohesive directory package `sandbox/factory/events/` adhering to deep module principles:
- Create `sandbox/factory/events/`:
  - `types.ts`: Telemetry event interfaces, event payload types (`TelemetryEnvelope`, `TelemetryEventType`, `TelemetryStage`), and constants (`EVENT_PREFIX`).
  - `formatter.ts`: Payload serialization, JSON stringification, timestamp injection, and diff/patch formatting.
  - `emitter.ts`: Synchronous stream writing (`process.stdout`), blocking socket controls, and buffer flush management.
  - `parser.ts`: In-stream event line extraction, prefix stripping, error parsing, and event reconstruction.
  - `index.ts`: Re-export all public symbols and functions so existing imports (`from "./events.ts"`) remain compatible (via export mapping or `events/index.ts`).
- Invariant: Each internal file must be $\le 500$ physical lines (`wc -l`).
- Verification: Run `pnpm test` in `sandbox/factory` (`events.test.ts`, `pipeline.test.ts`) to ensure all existing tests pass with zero modifications.

**Blocked by:** 03-decompose-factory-ui-grill

**Status:** resolved
**Triage:** ready-for-agent

- [x] Create `sandbox/factory/events/` directory and internal sub-modules (`types.ts`, `formatter.ts`, `emitter.ts`, `parser.ts`).
- [x] Move logic into respective sub-modules ensuring each file is $\le 500$ physical lines.
- [x] Create `sandbox/factory/events/index.ts` re-exporting all symbols.
- [x] Replace or proxy `sandbox/factory/events.ts` to export from `./events/index.ts`.
- [x] Verify `pnpm test` passes in `sandbox/factory` without test modifications.

## Comments

- Decomposed `sandbox/factory/events.ts` into package directory `sandbox/factory/events/` with 4 internal submodules (`types.ts`, `formatter.ts`, `emitter.ts`, `parser.ts`), `index.ts`, and proxy `sandbox/factory/events.ts`.
- All newly created files strictly adhere to the line budget ($\le 500$ physical lines):
  - `sandbox/factory/events.ts`: 5 lines
  - `sandbox/factory/events/emitter.ts`: 461 lines
  - `sandbox/factory/events/formatter.ts`: 361 lines
  - `sandbox/factory/events/index.ts`: 12 lines
  - `sandbox/factory/events/parser.ts`: 244 lines
  - `sandbox/factory/events/types.ts`: 93 lines
- All 166 tests across 10 test suites in `sandbox/factory` pass without test modifications (`events.test.ts`, `pipeline.test.ts`, etc.).

