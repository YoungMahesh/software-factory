# 01: In-Studio File Explorer & Code Viewer with Canvas View Switcher

**What to build:**
A top-level view mode switcher in the right canvas header (`[Live Preview] [Files & Code] [Git Diff]`) and a complete file inspection experience. When "Files & Code" is selected, developers can navigate an expandable directory tree of the target repository and inspect source code in a syntax-highlighted, read-only viewer. Backend file retrieval operates in a hybrid mode: querying the live Unified Studio Sandbox via in-sandbox execution when the container is running (surfacing uncommitted agent edits), and falling back cleanly to the remote GitHub Git Database API when the container is idle or stopped. Server-side ignore filtering excludes standard build and dependency directories, and file payloads are capped at 500KB with binary asset detection.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] Canvas header renders a clean view mode switcher (`[Live Preview] [Files & Code] [Git Diff]`) adhering to the Cohere Editorial Design System.
- [x] Selecting "Files & Code" replaces the preview iframe with a two-pane layout: a collapsible repository file tree on the left and a code viewing panel on the right.
- [x] Selecting a file in the directory tree displays its source code in a read-only viewer with line numbers and syntax styling.
- [x] When the Unified Studio Sandbox is active/serving, file discovery and content inspection query live container state to display uncommitted files and edits.
- [x] When the Unified Studio Sandbox is stopped or absent, file discovery and inspection fall back to the GitHub Git Database API for the active branch.
- [x] Dependency and build artifact directories (`node_modules`, `.git`, `.venv`, `.next`, `dist`, build caches) are filtered out on the server.
- [x] Files larger than 500KB or detected binary files render a safe informational placeholder showing file size and type instead of raw text.
- [x] All new backend and frontend source files strictly adhere to the Universal File Line Budget (<= 500 lines) with automated test coverage.
