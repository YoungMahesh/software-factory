import test from "node:test";
import * as assert from "node:assert/strict";
import * as http from "node:http";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import {
  runVisualQA,
  formatVisualQaDiagnostics,
  resolveChromeExecutablePath,
  CHROME_CONTAINER_FLAGS,
  type VisualQaResult,
  type VisualQaBrowserError,
  type VisualQaOptions,
} from "./visual-qa.ts";
import { parseTelemetryEnvelope } from "./events.ts";

test("resolveChromeExecutablePath: resolves /opt/google/chrome/chrome or override", () => {
  const custom = "/custom/path/to/chrome";
  assert.equal(resolveChromeExecutablePath(custom), custom);

  const resolved = resolveChromeExecutablePath();
  assert.ok(resolved.length > 0);
  assert.ok(
    resolved === "/opt/google/chrome/chrome" ||
    resolved === "/usr/bin/google-chrome" ||
    resolved === "/usr/bin/chromium" ||
    fs.existsSync(resolved)
  );
});

test("CHROME_CONTAINER_FLAGS: includes required sandbox-free flags", () => {
  assert.ok(CHROME_CONTAINER_FLAGS.includes("--no-sandbox"));
  assert.ok(CHROME_CONTAINER_FLAGS.includes("--disable-dev-shm-usage"));
  assert.ok(CHROME_CONTAINER_FLAGS.includes("--disable-gpu"));
});

test("formatVisualQaDiagnostics: formats clean canvas invariant failure into structured diagnostics", () => {
  const result: VisualQaResult = {
    passed: false,
    url: "http://127.0.0.1:3000",
    durationMs: 42,
    cleanCanvas: false,
    cleanCanvasDetails: {
      selector: "#root",
      width: 0,
      height: 0,
      hasRenderedMarkup: false,
      domSnippet: '<div id="root"></div>',
    },
    errors: [],
    summary: "Clean Canvas Invariant failed: root element (#root) has zero dimensions (0x0) or empty rendered markup.",
  };

  const diagnostics = formatVisualQaDiagnostics(result);
  assert.ok(diagnostics.includes("Clean Canvas Invariant Violated"));
  assert.ok(diagnostics.includes("#root"));
  assert.ok(diagnostics.includes("0x0"));
});

test("formatVisualQaDiagnostics: formats browser runtime exceptions and stack traces", () => {
  const result: VisualQaResult = {
    passed: false,
    url: "http://127.0.0.1:3000",
    durationMs: 120,
    cleanCanvas: true,
    errors: [
      {
        type: "pageerror",
        message: "ReferenceError: activeTab is not defined",
        stack: "ReferenceError: activeTab is not defined\n    at App (http://127.0.0.1:3000/src/App.tsx:24:5)",
        timestamp: 123456789,
      },
      {
        type: "console.error",
        message: "Warning: Each child in a list should have a unique 'key' prop.",
        location: "http://127.0.0.1:3000/src/components/List.tsx:12:3",
        timestamp: 123456790,
      },
    ],
    summary: "Visual QA failed: 2 browser runtime error(s) detected.",
  };

  const diagnostics = formatVisualQaDiagnostics(result);
  assert.ok(diagnostics.includes("Browser Runtime Crashes Detected"));
  assert.ok(diagnostics.includes("ReferenceError: activeTab is not defined"));
  assert.ok(diagnostics.includes("http://127.0.0.1:3000/src/App.tsx:24:5"));
  assert.ok(diagnostics.includes("Warning: Each child in a list should have a unique 'key' prop."));
});

test("runVisualQA: passes Clean Canvas with positive dimensions, markup, and no errors", async () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "vqa-test-artifacts-"));
  const telemetryLogs: string[] = [];
  const mockStream = {
    write: (chunk: string) => {
      telemetryLogs.push(chunk);
    },
  };

  try {
    const mockLauncher = {
      launch: async () => {
        return {
          newPage: async () => {
            return {
              on: (_event: string, _handler: any) => {},
              goto: async () => {},
              evaluate: async () => ({
                selector: "#root",
                width: 1280,
                height: 800,
                hasRenderedMarkup: true,
                domSnippet: '<div id="root"><h1>Loaded Application</h1></div>',
              }),
              setViewportSize: async () => {},
              screenshot: async ({ path: filePath }: { path: string }) => {
                fs.writeFileSync(filePath, "fake-png-data");
              },
              close: async () => {},
            };
          },
          close: async () => {},
        };
      },
    };

    const result = await runVisualQA({
      url: "http://127.0.0.1:3000",
      artifactsDir: tmpDir,
      browserLauncher: mockLauncher as any,
      stream: mockStream,
    });

    assert.equal(result.passed, true);
    assert.equal(result.cleanCanvas, true);
    assert.equal(result.errors.length, 0);
    assert.ok(result.screenshots?.desktop);
    assert.ok(result.screenshots?.mobile);
    assert.ok(fs.existsSync(result.screenshots.desktop));
    assert.ok(fs.existsSync(result.screenshots.mobile));

    // Verify visual_qa telemetry marker was emitted
    const rawEnvelope = telemetryLogs.find((l) => l.includes('"type":"visual_qa"'));
    assert.ok(rawEnvelope, "Expected visual_qa telemetry event in stdout");
    const parsed = parseTelemetryEnvelope(rawEnvelope.trim());
    assert.ok(parsed);
    assert.equal(parsed.type, "visual_qa");
    assert.equal(parsed.data.passed, true);
    assert.equal(parsed.data.cleanCanvas, true);
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

test("runVisualQA: fails Clean Canvas Invariant when root element has 0 dimensions", async () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "vqa-test-artifacts-"));
  try {
    const mockLauncher = {
      launch: async () => ({
        newPage: async () => ({
          on: () => {},
          goto: async () => {},
          evaluate: async () => ({
            selector: "#root",
            width: 0,
            height: 0,
            hasRenderedMarkup: true,
            domSnippet: '<div id="root">collapsed</div>',
          }),
          setViewportSize: async () => {},
          screenshot: async () => {},
          close: async () => {},
        }),
        close: async () => {},
      }),
    };

    const result = await runVisualQA({
      url: "http://127.0.0.1:3000",
      artifactsDir: tmpDir,
      browserLauncher: mockLauncher as any,
    });

    assert.equal(result.passed, false);
    assert.equal(result.cleanCanvas, false);
    assert.ok(result.summary.includes("Clean Canvas Invariant failed"));
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

test("runVisualQA: fails Clean Canvas Invariant when root element has empty markup", async () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "vqa-test-artifacts-"));
  try {
    const mockLauncher = {
      launch: async () => ({
        newPage: async () => ({
          on: () => {},
          goto: async () => {},
          evaluate: async () => ({
            selector: "#root",
            width: 1280,
            height: 800,
            hasRenderedMarkup: false,
            domSnippet: '<div id="root"></div>',
          }),
          setViewportSize: async () => {},
          screenshot: async () => {},
          close: async () => {},
        }),
        close: async () => {},
      }),
    };

    const result = await runVisualQA({
      url: "http://127.0.0.1:3000",
      artifactsDir: tmpDir,
      browserLauncher: mockLauncher as any,
    });

    assert.equal(result.passed, false);
    assert.equal(result.cleanCanvas, false);
    assert.ok(result.summary.includes("Clean Canvas Invariant failed"));
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

test("runVisualQA: traps browser uncaught exceptions and console.error", async () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "vqa-test-artifacts-"));
  try {
    const mockLauncher = {
      launch: async () => ({
        newPage: async () => {
          const listeners: Record<string, Function[]> = {};
          return {
            on: (event: string, handler: Function) => {
              listeners[event] = listeners[event] || [];
              listeners[event].push(handler);
            },
            goto: async () => {
              // Simulate page errors during load
              if (listeners["pageerror"]) {
                const err = new Error("Uncaught TypeError: Cannot read property 'map' of undefined");
                err.stack = "TypeError: Cannot read property 'map' of undefined\n    at Render (main.js:10:5)";
                listeners["pageerror"].forEach((h) => h(err));
              }
              if (listeners["console"]) {
                listeners["console"].forEach((h) =>
                  h({
                    type: () => "error",
                    text: () => "Failed to load resource: 404 Not Found",
                    location: () => ({ url: "http://127.0.0.1:3000/api/data", lineNumber: 1, columnNumber: 1 }),
                  })
                );
              }
              if (listeners["requestfailed"]) {
                listeners["requestfailed"].forEach((h) =>
                  h({
                    url: () => "http://127.0.0.1:3000/assets/missing.js",
                    failure: () => ({ errorText: "net::ERR_FILE_NOT_FOUND" }),
                    method: () => "GET",
                  })
                );
              }
            },
            waitForLoadState: async () => {},
            evaluate: async () => ({
              selector: "#root",
              width: 1280,
              height: 800,
              hasRenderedMarkup: true,
              domSnippet: '<div id="root">content</div>',
            }),
            setViewportSize: async () => {},
            screenshot: async () => {},
            close: async () => {},
          };
        },
        close: async () => {},
      }),
    };

    const result = await runVisualQA({
      url: "http://127.0.0.1:3000",
      artifactsDir: tmpDir,
      browserLauncher: mockLauncher as any,
    });

    assert.equal(result.passed, false);
    assert.equal(result.cleanCanvas, true);
    assert.equal(result.errors.length, 3);
    assert.equal(result.errors[0].type, "pageerror");
    assert.ok(result.errors[0].message.includes("Cannot read property 'map'"));
    assert.equal(result.errors[1].type, "console.error");
    assert.ok(result.errors[1].message.includes("Failed to load resource"));
    assert.equal(result.errors[2].type, "requestfailed");
    assert.ok(result.errors[2].message.includes("missing.js"));
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

test("runVisualQA: enforces timeout bounds when page load hangs", async () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "vqa-test-artifacts-"));
  try {
    const mockLauncher = {
      launch: async () => ({
        newPage: async () => ({
          on: () => {},
          goto: async () => {
            // Simulate hanging forever
            await new Promise((resolve) => setTimeout(resolve, 5000));
          },
          evaluate: async () => ({}),
          setViewportSize: async () => {},
          screenshot: async () => {},
          close: async () => {},
        }),
        close: async () => {},
      }),
    };

    const startTime = Date.now();
    const result = await runVisualQA({
      url: "http://127.0.0.1:3000",
      artifactsDir: tmpDir,
      browserLauncher: mockLauncher as any,
      timeoutMs: 150, // Short timeout
    });

    const elapsed = Date.now() - startTime;
    assert.ok(elapsed < 1000, `Expected timeout under 1000ms, took ${elapsed}ms`);
    assert.equal(result.passed, false);
    assert.ok(result.summary.includes("timed out") || result.errors.some((e) => e.message.includes("timed out")));
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

test("runVisualQA [E2E with real headless Chrome]: verifies Clean Canvas, screenshots, and crash detection", async () => {
  // Start a local test HTTP server
  let mode: "good" | "error" | "blank" = "good";
  const server = http.createServer((req, res) => {
    res.setHeader("Content-Type", "text/html");
    if (mode === "good") {
      res.end(`
        <!DOCTYPE html>
        <html>
          <head><title>Test App</title></head>
          <body style="margin: 0; padding: 0;">
            <div id="root" style="width: 100vw; height: 100vh; background-color: #f0f0f0;">
              <h1>App Mounted Successfully</h1>
              <p>Welcome to Visual QA verification.</p>
            </div>
          </body>
        </html>
      `);
    } else if (mode === "error") {
      res.end(`
        <!DOCTYPE html>
        <html>
          <head><title>Crashing App</title></head>
          <body>
            <div id="root" style="width: 200px; height: 200px;">Before crash</div>
            <script>
              throw new Error("Fatal React hydration error: undefined variable accessed");
            </script>
          </body>
        </html>
      `);
    } else {
      // Clean Canvas Invariant violation
      res.end(`
        <!DOCTYPE html>
        <html>
          <head><title>Blank App</title></head>
          <body>
            <div id="root" style="width: 0; height: 0;"></div>
          </body>
        </html>
      `);
    }
  });

  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = (server.address() as any).port;
  const testUrl = `http://127.0.0.1:${port}`;
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "vqa-e2e-artifacts-"));

  try {
    // 1. Good mode
    mode = "good";
    const goodResult = await runVisualQA({
      url: testUrl,
      artifactsDir: tmpDir,
      timeoutMs: 6000,
    });

    assert.equal(goodResult.passed, true);
    assert.equal(goodResult.cleanCanvas, true);
    assert.equal(goodResult.errors.length, 0);
    assert.ok(goodResult.screenshots?.desktop);
    assert.ok(goodResult.screenshots?.mobile);
    assert.ok(fs.existsSync(goodResult.screenshots.desktop));
    assert.ok(fs.existsSync(goodResult.screenshots.mobile));
    const desktopSize = fs.statSync(goodResult.screenshots.desktop).size;
    const mobileSize = fs.statSync(goodResult.screenshots.mobile).size;
    assert.ok(desktopSize > 1000, `Desktop screenshot size ${desktopSize} should be > 1000 bytes`);
    assert.ok(mobileSize > 1000, `Mobile screenshot size ${mobileSize} should be > 1000 bytes`);

    // 2. Error mode
    mode = "error";
    const errorResult = await runVisualQA({
      url: testUrl,
      artifactsDir: tmpDir,
      timeoutMs: 6000,
    });
    assert.equal(errorResult.passed, false);
    assert.ok(errorResult.errors.length > 0);
    assert.ok(errorResult.errors.some((e) => e.message.includes("Fatal React hydration error")));

    // 3. Blank mode
    mode = "blank";
    const blankResult = await runVisualQA({
      url: testUrl,
      artifactsDir: tmpDir,
      timeoutMs: 6000,
    });
    assert.equal(blankResult.passed, false);
    assert.equal(blankResult.cleanCanvas, false);
  } finally {
    server.close();
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});
