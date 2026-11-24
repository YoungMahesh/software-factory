# Adopt pnpm as Package Manager

To accelerate dependency installation times, enforce strict dependency isolation, and eliminate ghost dependency issues, pnpm is adopted as the canonical package manager for the repository. The project declares `packageManager: pnpm@10.31.0` in `package.json`, replaces `package-lock.json` with `pnpm-lock.yaml`, and standardizes developer documentation, agent guidelines, and tooling configurations on pnpm commands.
