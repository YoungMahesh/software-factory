import { describe, it, expect } from "vitest";
import { classifyBottleneck } from "./classification";

describe("classifyBottleneck", () => {
  it("classifies LLM thinking blocks as 'LLM Thinking'", () => {
    expect(classifyBottleneck({ type: "thinking" })).toBe("LLM Thinking");
    expect(
      classifyBottleneck({
        type: "thinking",
        command: "Drafting implementation plan",
        stage: "PLANNER",
      })
    ).toBe("LLM Thinking");
  });

  describe("Package Install classification", () => {
    const installCommands = [
      "pnpm install",
      "pnpm install --frozen-lockfile",
      "pnpm add axios lucide-react",
      "pnpm i",
      "npm install",
      "npm i react",
      "npm add lodash",
      "yarn add tailwindcss",
      "yarn install",
      "pip install -r requirements.txt",
      "pip3 install modal fastapi",
      "uv pip install pytest",
      "poetry install",
      "poetry add httpx",
      "cargo add serde",
      "cargo install ripgrep",
    ];

    installCommands.forEach((cmd) => {
      it(`classifies '${cmd}' as 'Package Install'`, () => {
        expect(classifyBottleneck({ type: "command", command: cmd })).toBe("Package Install");
      });
    });
  });

  describe("Test Suite classification", () => {
    const testCommands = [
      "pytest tests/",
      "pytest tests/test_ui -v",
      "vitest run",
      "vitest --coverage",
      "jest --watchAll=false",
      "pnpm test",
      "pnpm run test",
      "npm test",
      "yarn test",
      "python -m pytest",
      "python3 -m pytest tests/",
      "go test ./...",
      "cargo test",
    ];

    testCommands.forEach((cmd) => {
      it(`classifies '${cmd}' as 'Test Suite'`, () => {
        expect(classifyBottleneck({ type: "command", command: cmd })).toBe("Test Suite");
      });
    });

    it("classifies operations in VERIFIER stage as 'Test Suite'", () => {
      expect(
        classifyBottleneck({
          type: "command",
          command: "node test-runner.js",
          stage: "VERIFIER",
        })
      ).toBe("Test Suite");
    });
  });

  describe("Build / Compile classification", () => {
    const buildCommands = [
      "pnpm build",
      "pnpm run build",
      "npm run build",
      "yarn build",
      "tsc",
      "tsc --noEmit",
      "vite build",
      "webpack --mode production",
      "cargo build --release",
      "make all",
    ];

    buildCommands.forEach((cmd) => {
      it(`classifies '${cmd}' as 'Build / Compile'`, () => {
        expect(classifyBottleneck({ type: "command", command: cmd })).toBe("Build / Compile");
      });
    });
  });

  describe("Git / VCS classification", () => {
    const gitCommands = [
      "git clone https://github.com/org/repo.git",
      "git fetch origin",
      "git checkout -b feature-1",
      "git status",
      "git diff HEAD~1",
      "git add .",
      "git commit -m 'feat: add tab'",
      "git push origin main",
      "git pull",
      "git switch -c fix-bug",
      "git merge main",
      "git log -n 5",
      "git reset --hard",
    ];

    gitCommands.forEach((cmd) => {
      it(`classifies '${cmd}' as 'Git / VCS'`, () => {
        expect(classifyBottleneck({ type: "command", command: cmd })).toBe("Git / VCS");
      });
    });
  });

  describe("General Command classification", () => {
    const genericCommands = [
      "ls -la",
      "cat README.md",
      "mkdir -p src/components",
      "echo 'hello world'",
      "python script.py",
      "node server.js",
    ];

    genericCommands.forEach((cmd) => {
      it(`classifies '${cmd}' as 'Command'`, () => {
        expect(classifyBottleneck({ type: "command", command: cmd })).toBe("Command");
      });
    });
  });
});
