# Spec: Instant Cold Starts and Visual Multimodal QA for Factory Studio

Status: resolved
Triage: resolved

## Problem Statement

Developers and autonomous agents iterating on web applications within Factory Studio face two critical operational bottlenecks:

1. **High Cold-Start Latency on Sandbox Boots**:
   When a Unified Studio Sandbox is provisioned or reactivated for an application, container initialization currently repeats the full workspace preparation lifecycle from scratch: decrypting SOPS secrets, performing a full Git clone of the remote GitHub repository, installing harness dependencies, and running package installations for the target application (`pnpm install`). This cold-start initialization consumes 40 to 55 seconds on every container start, creating unnecessary friction whenever a developer opens an application or resumes after an idle timeout.

2. **Visual Verification Blind Spots in the Assembly Line Quality Gate**:
   The Deterministic Verifier currently relies strictly on command-line test suites and linters (`pnpm test`, `vitest run`). In single-page frontend applications (such as TanStack Start), critical visual regressions—such as blank white screens caused by React mounting errors, broken CSS styling, collapsed containers, or unhandled client-side runtime exceptions—do not fail deterministic unit test suites. Consequently, broken user interfaces pass the quality gate and are delivered to the Feature Pull Request without warning.

## Solution

Address both latency and visual fidelity by implementing an integrated Filesystem Snapshot pipeline and an automated Visual Multimodal Quality Gate:

1. **Instant Sandbox Cold Starts via Filesystem Snapshots**:
   - Capture a non-destructive point-in-time filesystem snapshot of the root container once an application sandbox reaches the active serving state and dependencies are fully hydrated.
   - Persist snapshot image identifiers in the Studio Database associated with the target repository.
   - When launching or reactivating a Unified Studio Sandbox, check for an existing valid snapshot image. If present, instantiate the container directly from the snapshot image ID and signal fast-path resumption, bypassing Git cloning and full package installation to reduce cold-start latency from ~45 seconds to under 3 seconds.
   - Maintain seamless branch switching and incremental dependency installation if `package.json` drifts after snapshot capture.

2. **Visual Multimodal QA Gate via Headless Chrome & Playwright**:
   - Leverage the pre-baked headless Google Chrome tooling inside the sandbox image to run an automated visual inspection against the local development server (port 3000) during the Assembly Line Pipeline.
   - Validate the Clean Canvas Invariant and detect fatal frontend regressions: assert that the root DOM element renders with non-zero dimensions, verify that no uncaught exceptions or error-level console logs occurred during page load, and capture full-page desktop and mobile viewport screenshot artifacts.
   - Integrate visual assertion failures into the Self-Correction Loop, feeding browser stack traces back to the Coder Agent for automatic repair before human review.
   - Surface the captured screenshot artifacts and visual verification status directly within the Delivery Gate Card in Factory Studio, allowing developers to visually confirm UI state before triggering squash merges.

## User Stories

1. As a developer opening an existing application in Factory Studio, I want the Unified Studio Sandbox to boot in under 3 seconds from a warm snapshot, so that I can immediately interact with the live preview without waiting for package installations.
2. As a developer launching an application for the first time, I want the system to seamlessly perform full repository cloning and dependency installation, so that initial setup succeeds without requiring pre-existing snapshots.
3. As a developer whose sandbox has reached a stable serving state, I want the system to automatically capture a non-destructive root filesystem snapshot in the background, so that future sessions benefit from instant cold starts without interrupting my active preview.
4. As a developer working across multiple repositories, I want snapshot image identifiers to be tracked and persisted per repository in the database, so that each application maintains its own cached execution baseline.
5. As an infrastructure administrator, I want snapshots to be registered with a configurable 30-day Time-To-Live (TTL), so that stale or abandoned sandbox images are automatically reclaimed by the cloud platform.
6. As a developer pulling updated commits on a snapshotted sandbox, I want the resumed container to fetch the target branch incrementally rather than re-cloning the entire repository, so that network transfer and latency are minimized.
7. As a developer modifying `package.json` or `pnpm-lock.yaml`, I want the resumed container to detect dependency drift and run incremental package installs, so that newly added packages are installed without corrupting the workspace.
8. As a developer encountering an expired or invalid snapshot image, I want the sandbox spawner to gracefully fall back to a clean full build, so that workspace provisioning never fails due to snapshot cache misses.
9. As an autonomous assembly line agent building a frontend feature, I want the pipeline to verify that the active development server on port 3000 renders cleanly, so that broken builds are detected before opening a pull request.
10. As a developer using Factory Studio, I want the automated verifier to detect unhandled JavaScript runtime exceptions in the browser console, so that syntax errors and undefined variable crashes fail the quality gate.
11. As a developer using Factory Studio, I want the automated verifier to detect blank white screens where the application container failed to mount, so that unrendered views are never marked as completed.
12. As a developer using Factory Studio, I want the visual verification stage to capture standard desktop (1280x800) and mobile (390x844) viewport screenshots, so that responsive layouts are preserved as artifacts.
13. As a Coder Agent whose change caused a browser runtime crash, I want the verifier to capture the browser console error and stack trace and feed it back into the Self-Correction Loop, so that I can diagnose and fix the issue within my retry attempts.
14. As a Reviewer Agent auditing a feature delivery, I want to inspect visual screenshot artifacts alongside code diffs, so that I can evaluate UI styling and adherence to domain specifications.
15. As a developer reviewing a completed work item in Factory Studio chat, I want the Delivery Gate Card to show a visual verification badge and screenshot thumbnail, so that I have immediate visual confidence before merging.
16. As a developer clicking a screenshot thumbnail in the Delivery Gate Card, I want to view an expanded preview of the captured screen, so that I can inspect component layouts without navigating away from the review flow.
17. As an external API client, I want an HTTP endpoint to fetch the latest preview screenshot and verification telemetry for a repository, so that external dashboards or CI tooling can access visual verification results.
18. As a developer switching branches in the live preview, I want visual screenshot telemetry to update with the corresponding branch state, so that visual QA results remain synchronized with active preview code.
19. As a developer rolling back a turn, I want visual artifacts associated with that turn to be archived, so that chat history reflects the reverted state.
20. As a developer executing automated tests, I want visual inspection to run in headless non-interactive mode with strict timeouts, so that the verification stage never hangs indefinitely waiting for network resources.

## Implementation Decisions

- **Persistence Layer & Schema Extension**:
  - Extend the studio database `previews` schema with fields for snapshot tracking:
    ```sql
    snapshot_image_id TEXT,
    snapshot_commit_sha TEXT,
    snapshot_captured_at REAL
    ```
  - Provide database adapter methods to record newly captured snapshot image IDs and retrieve the latest valid snapshot image for any target repository.

- **Background Snapshot Orchestration**:
  - In the preview registry, detect the transition of a sandbox to the active serving state.
  - When reaching active serving, compare the current repository HEAD commit SHA against the recorded snapshot commit SHA.
  - If no snapshot exists or if dependencies/commits have advanced, dispatch a non-blocking asynchronous snapshot task executing filesystem synchronization (`sync`) followed by Modal snapshot capture with a 30-day wire retention.
  - Keep the active container running without teardown during capture. Upon receiving the snapshot image object, record its identifier and commit SHA in the database.

- **Fast-Path Sandbox Provisioning**:
  - When spawning a Unified Studio Sandbox, query the database for an existing snapshot image ID.
  - If a snapshot exists, instantiate the sandbox image directly from the snapshot ID, bypass image build staging, and pass a snapshot resumption flag in the container environment.
  - If snapshot resolution fails or errors occur, fall back immediately to standard image creation.

- **In-Container Startup Resumption**:
  - In the container entrypoint, detect the snapshot resumption flag.
  - When resuming from a snapshot, bypass the `git clone` sequence and full package installation.
  - Execute a fast fetch against the target branch, check out the target ref, and inspect whether dependency manifests (`package.json`, `pnpm-lock.yaml`) changed between the snapshot commit and the current ref.
  - If manifests changed, execute an offline-preferred incremental install; otherwise, immediately launch the development server supervisor.

- **Headless Visual QA Engine**:
  - Implement a dedicated visual verification stage executed within the sandbox after code modifications are committed.
  - Connect via Playwright to the local development server at `http://127.0.0.1:3000` using pre-baked Google Chrome (`/opt/google/chrome/chrome`) with required container flags (`--no-sandbox`, `--disable-dev-shm-usage`).
  - Capture browser console logs, uncaught exceptions, and request failures.
  - Wait for DOM content loaded and network idle with a bounded timeout (maximum 8 seconds).
  - Assert that the root container has positive bounding dimensions and non-empty rendered markup.
  - Capture viewport screenshots saved into a designated artifacts directory (`/root/.factory/artifacts/`).
  - Format any detected browser exceptions into structured verification errors for consumption by the self-correction mechanism.

- **Visual QA Telemetry & Delivery Gate Exposure**:
  - Emit structured visual telemetry events (`__SF_EVENT__:{"type":"visual_qa",...}`) containing verification verdicts, captured error lists, and artifact paths.
  - In the REST API, expose an endpoint to retrieve the visual QA screenshot and metadata for a given repository and branch.
  - Update the Delivery Gate Card in the web frontend to render a visual verification badge and an expandable screenshot modal prior to the in-studio merge control.

## Testing Decisions

- **Testing Philosophy**:
  - Tests must verify external observable behavior across the highest architectural seams rather than asserting internal implementation details or private method calls.
  - Modal platform interactions (snapshot capture and image instantiation) must be tested against simulated response objects asserting correct parameter propagation (TTL, flags, and image IDs).
  - Visual verification tests must validate real browser event processing, DOM presence checks, and error formatting against mock HTTP/Vite responses.

- **Target Modules & Seams**:
  - **Preview Registry & Spawner Seam**: Assert that `launch_preview` properly detects existing snapshots from the database, passes image IDs to the spawner, and triggers background capture when serving without blocking immediate preview availability.
  - **Database Persistence Seam**: Assert that snapshot metadata is saved, queried, and rehydrated correctly without data corruption across database restarts.
  - **Container Startup Logic Seam**: Assert that the startup script correctly branches on the resumption flag, bypassing git clone and dependency install when resuming from a snapshot.
  - **Visual Verifier Seam**: Assert that the visual QA module detects fatal page errors, distinguishes clean canvases from blank screens, enforces execution timeouts, and outputs structured telemetry.
  - **Delivery Gate REST API Seam**: Assert that screenshot endpoints return expected MIME types and metadata, and handle missing screenshot states gracefully.

- **Prior Art in Codebase**:
  - `tests/test_sandbox/test_snapshots.py` — Unit tests for CLI snapshot capture and parameter propagation.
  - `tests/test_ui/test_fastapi_preview.py` — Preview sandbox lifecycle, branch switching, and registry mock testing.
  - `tests/test_ui_db.py` — Database schema migration and CRUD persistence tests.
  - `tests/test_ui/test_pull_requests_endpoints.py` — Delivery gate review and pull request endpoint testing.
  - `sandbox/factory/verifier-core.test.ts` — Command verification, timeout enforcement, and stage telemetry testing.

## Out of Scope

- Cross-browser rendering matrices (testing across Firefox, WebKit, or Safari engines); all automated visual verification strictly uses pre-baked headless Google Chrome.
- Pixel-by-pixel perceptual visual regression thresholding (diffing pixel bitmaps against historical baselines); visual verification focuses on crash detection, DOM mounting, zero console errors, and artifact generation.
- Persistent volume snapshotting for VM Sandbox Docker daemon storage (`/var/lib/docker`); snapshotting targets the root container filesystem.
- Interactive user browser recording or automated user journey scripting.

## Further Notes

- This specification adheres strictly to the Universal File Line Budget (500 physical lines per source file) under ADR 0051 and ADR 0057.
- Builds upon pre-baked Chrome capabilities established in ADR 0012 and snapshot primitives established in ADR 0045.
- The resulting screenshots serve as primary multimodal evidence for both human reviewers and automated Reviewer Agents.
