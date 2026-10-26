import * as fs from "node:fs";
import * as path from "node:path";
import * as net from "node:net";
import { chromium, type Browser, type Page } from "playwright-core";
import { emitTelemetryEvent } from "./events.ts";

export const CHROME_CONTAINER_FLAGS = [
  "--no-sandbox",
  "--disable-dev-shm-usage",
  "--disable-gpu",
];

export const DEFAULT_VIEWPORTS = {
  desktop: { width: 1280, height: 800 },
  mobile: { width: 390, height: 844 },
};

export interface VisualQaBrowserError {
  type: "pageerror" | "console.error";
  message: string;
  stack?: string;
  location?: string;
  timestamp: number;
}

export interface CleanCanvasDetails {
  selector?: string;
  width?: number;
  height?: number;
  hasRenderedMarkup: boolean;
  domSnippet?: string;
}

export interface VisualQaScreenshots {
  desktop?: string;
  mobile?: string;
}

export interface VisualQaResult {
  passed: boolean;
  url: string;
  durationMs: number;
  cleanCanvas: boolean;
  cleanCanvasDetails?: CleanCanvasDetails;
  errors: VisualQaBrowserError[];
  screenshots?: VisualQaScreenshots;
  summary: string;
}

export interface BrowserLauncher {
  launch(options: {
    executablePath?: string;
    args?: string[];
    headless?: boolean;
    timeout?: number;
  }): Promise<any>;
}

export interface VisualQaOptions {
  url?: string;
  timeoutMs?: number;
  rootSelector?: string;
  artifactsDir?: string;
  chromePath?: string;
  browserLauncher?: BrowserLauncher;
  stream?: { write: (chunk: string) => any };
  emitTelemetry?: boolean;
  captureScreenshots?: boolean;
}

export function resolveChromeExecutablePath(override?: string): string {
  if (override && override.trim().length > 0) {
    return override.trim();
  }
  if (process.env.CHROME_PATH && process.env.CHROME_PATH.trim().length > 0) {
    return process.env.CHROME_PATH.trim();
  }
  const candidatePaths = [
    "/opt/google/chrome/chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
  ];
  for (const p of candidatePaths) {
    if (fs.existsSync(p)) {
      return p;
    }
  }
  return candidatePaths[0];
}

export function formatVisualQaDiagnostics(result: VisualQaResult): string {
  const parts: string[] = [
    `### Visual QA Verification: FAILED`,
    `**Target URL**: ${result.url}`,
    `**Execution Duration**: ${result.durationMs}ms`,
  ];

  if (!result.cleanCanvas) {
    const details = result.cleanCanvasDetails;
    const dims = details ? `${details.width}x${details.height}` : "0x0";
    const selector = details?.selector || "#root";
    parts.push(
      `#### Clean Canvas Invariant Violated\n` +
      `The application root container (\`${selector}\`) failed the Clean Canvas Invariant.\n` +
      `- Dimensions: ${dims} (positive width and height required)\n` +
      `- Rendered Markup: ${details?.hasRenderedMarkup ? "Yes" : "Empty / White Screen"}\n` +
      (details?.domSnippet ? `- DOM Snippet: \`${details.domSnippet}\`` : "")
    );
  }

  if (result.errors.length > 0) {
    parts.push(
      `#### Browser Runtime Crashes Detected (${result.errors.length} fatal error${result.errors.length === 1 ? "" : "s"})`
    );
    for (const err of result.errors) {
      const errHeader = `- [${err.type}] ${err.message}${err.location ? `\n  Location: ${err.location}` : ""}`;
      const stackBlock = err.stack ? `\n  Stack:\n    ${err.stack.split("\n").join("\n    ")}` : "";
      parts.push(`${errHeader}${stackBlock}`);
    }
  }

  if (result.summary && !parts.some((p) => p.includes(result.summary))) {
    parts.push(`**Summary**: ${result.summary}`);
  }

  parts.push(
    `**Action Required**: Fix the browser exceptions or blank screen above so the application cleanly mounts and renders visible elements without runtime errors.`
  );

  return parts.join("\n\n");
}

export function isDevServerAvailable(
  urlOrPort: string | number = "http://127.0.0.1:3000",
  timeoutMs: number = 500
): Promise<boolean> {
  let port = 3000;
  let host = "127.0.0.1";
  if (typeof urlOrPort === "number") {
    port = urlOrPort;
  } else {
    try {
      const parsed = new URL(urlOrPort);
      port = parseInt(parsed.port || (parsed.protocol === "https:" ? "443" : "80"), 10);
      host = parsed.hostname || "127.0.0.1";
    } catch {
      port = 3000;
    }
  }

  return new Promise((resolve) => {
    const socket = new net.Socket();
    socket.setTimeout(timeoutMs);
    socket.once("connect", () => {
      socket.destroy();
      resolve(true);
    });
    socket.once("timeout", () => {
      socket.destroy();
      resolve(false);
    });
    socket.once("error", () => {
      socket.destroy();
      resolve(false);
    });
    socket.connect(port, host);
  });
}

export async function runVisualQA(options?: VisualQaOptions): Promise<VisualQaResult> {
  const startTime = Date.now();
  const url = options?.url ?? "http://127.0.0.1:3000";
  const timeoutMs = options?.timeoutMs ?? 8000;
  const rootSelector = options?.rootSelector;
  const artifactsDir =
    options?.artifactsDir || process.env.FACTORY_ARTIFACTS_DIR || "/root/.factory/artifacts";
  const captureScreenshots = options?.captureScreenshots ?? true;
  const emitTelemetry = options?.emitTelemetry ?? true;

  const browserErrors: VisualQaBrowserError[] = [];
  let cleanCanvasDetails: CleanCanvasDetails | undefined = undefined;
  let screenshots: VisualQaScreenshots | undefined = undefined;
  let browser: any = null;
  let page: any = null;
  let timedOut = false;

  const launcher: BrowserLauncher =
    options?.browserLauncher ?? {
      launch: (opts) => chromium.launch(opts),
    };

  const executablePath = resolveChromeExecutablePath(options?.chromePath);

  try {
    const launchPromise = launcher.launch({
      executablePath,
      args: [...CHROME_CONTAINER_FLAGS],
      headless: true,
      timeout: timeoutMs,
    });

    const timeoutPromise = new Promise<never>((_, reject) => {
      const t = setTimeout(() => {
        timedOut = true;
        reject(new Error(`Visual QA execution timed out after ${timeoutMs}ms waiting for ${url}`));
      }, timeoutMs);
      if (typeof t.unref === "function") t.unref();
    });

    browser = await Promise.race([launchPromise, timeoutPromise]);
    page = await browser.newPage();

    if (typeof page.setDefaultTimeout === "function") {
      page.setDefaultTimeout(timeoutMs);
    }

    // Attach runtime exception traps
    page.on("pageerror", (err: any) => {
      browserErrors.push({
        type: "pageerror",
        message: err?.message || String(err),
        stack: err?.stack,
        timestamp: Date.now(),
      });
    });

    page.on("console", (msg: any) => {
      const msgType = typeof msg.type === "function" ? msg.type() : msg.type;
      if (msgType === "error") {
        const text = typeof msg.text === "function" ? msg.text() : String(msg);
        let locationStr: string | undefined = undefined;
        if (typeof msg.location === "function") {
          const loc = msg.location();
          if (loc?.url) {
            locationStr = `${loc.url}:${loc.lineNumber ?? 0}:${loc.columnNumber ?? 0}`;
          }
        }
        browserErrors.push({
          type: "console.error",
          message: text,
          location: locationStr,
          timestamp: Date.now(),
        });
      }
    });

    page.on("crash", () => {
      browserErrors.push({
        type: "pageerror",
        message: "Browser page crashed unexpectedly",
        timestamp: Date.now(),
      });
    });

    // Navigate to page
    await Promise.race([
      page.goto(url, { waitUntil: "domcontentloaded", timeout: timeoutMs }),
      timeoutPromise,
    ]);

    // Give asynchronous rendering or React hydration a brief tick
    await new Promise((r) => setTimeout(r, 100));

    // Evaluate Clean Canvas Invariant
    cleanCanvasDetails = await Promise.race([
      page.evaluate((targetSelector?: string) => {
        const selectors = targetSelector
          ? [targetSelector]
          : ["#root", "#app", "[data-root]", "main", "body > div:first-of-type", "body"];

        let foundEl: Element | null = null;
        let matchedSelector = "";
        for (const sel of selectors) {
          const candidate = document.querySelector(sel);
          if (candidate) {
            foundEl = candidate;
            matchedSelector = sel;
            break;
          }
        }

        if (!foundEl) {
          return {
            selector: targetSelector || "none",
            width: 0,
            height: 0,
            hasRenderedMarkup: false,
            domSnippet: document.body ? document.body.innerHTML.slice(0, 200) : "",
          };
        }

        const rect = foundEl.getBoundingClientRect();
        const style = window.getComputedStyle(foundEl);
        const isVisible =
          style.display !== "none" && style.visibility !== "hidden" && style.opacity !== "0";
        const innerHtml = foundEl.innerHTML ? foundEl.innerHTML.trim() : "";
        const text = foundEl.textContent ? foundEl.textContent.trim() : "";
        const childCount = foundEl.childElementCount;
        const hasMarkup = innerHtml.length > 0 && (childCount > 0 || text.length > 0);
        const positiveDims = rect.width > 0 && rect.height > 0 && isVisible;

        return {
          selector: matchedSelector,
          width: Math.round(rect.width),
          height: Math.round(rect.height),
          hasRenderedMarkup: hasMarkup && positiveDims,
          domSnippet: innerHtml.slice(0, 200),
        };
      }, rootSelector),
      timeoutPromise,
    ]);

    // Capture screenshots if requested
    if (captureScreenshots) {
      const outputDir = path.join(artifactsDir, "visual-qa");
      if (!fs.existsSync(outputDir)) {
        fs.mkdirSync(outputDir, { recursive: true });
      }
      const desktopPath = path.join(outputDir, "desktop.png");
      const mobilePath = path.join(outputDir, "mobile.png");

      if (typeof page.setViewportSize === "function") {
        await page.setViewportSize(DEFAULT_VIEWPORTS.desktop);
        await new Promise((r) => setTimeout(r, 50));
        await page.screenshot({ path: desktopPath, fullPage: true });

        await page.setViewportSize(DEFAULT_VIEWPORTS.mobile);
        await new Promise((r) => setTimeout(r, 50));
        await page.screenshot({ path: mobilePath, fullPage: true });

        screenshots = {
          desktop: desktopPath,
          mobile: mobilePath,
        };
      }
    }
  } catch (err: any) {
    const errorMsg = err?.message || String(err);
    browserErrors.push({
      type: "pageerror",
      message: errorMsg,
      stack: err?.stack,
      timestamp: Date.now(),
    });
  } finally {
    if (page && typeof page.close === "function") {
      try {
        await page.close();
      } catch {
        // Ignore page close errors
      }
    }
    if (browser && typeof browser.close === "function") {
      try {
        await browser.close();
      } catch {
        // Ignore browser close errors
      }
    }
  }

  const durationMs = Date.now() - startTime;
  const cleanCanvas = Boolean(
    cleanCanvasDetails &&
      cleanCanvasDetails.width !== undefined &&
      cleanCanvasDetails.width > 0 &&
      cleanCanvasDetails.height !== undefined &&
      cleanCanvasDetails.height > 0 &&
      cleanCanvasDetails.hasRenderedMarkup
  );

  const passed = cleanCanvas && browserErrors.length === 0;

  let summary = "";
  if (passed) {
    summary = `Visual QA passed: Clean Canvas verified on ${cleanCanvasDetails?.selector ?? "#root"} (${cleanCanvasDetails?.width}x${cleanCanvasDetails?.height}), 0 console errors, viewports captured.`;
  } else if (!cleanCanvas) {
    const dims = cleanCanvasDetails
      ? `${cleanCanvasDetails.width}x${cleanCanvasDetails.height}`
      : "0x0";
    const selector = cleanCanvasDetails?.selector ?? "#root";
    summary = `Clean Canvas Invariant failed: root element (${selector}) has zero dimensions (${dims}) or empty rendered markup.`;
    if (browserErrors.length > 0) {
      summary += ` (${browserErrors.length} fatal browser error(s) detected)`;
    }
  } else {
    summary = `Visual QA failed: ${browserErrors.length} fatal browser error(s) detected.`;
  }

  const result: VisualQaResult = {
    passed,
    url,
    durationMs,
    cleanCanvas,
    cleanCanvasDetails,
    errors: browserErrors,
    screenshots,
    summary,
  };

  try {
    const outputDir = path.join(artifactsDir, "visual-qa");
    if (!fs.existsSync(outputDir)) {
      fs.mkdirSync(outputDir, { recursive: true });
    }
    fs.writeFileSync(
      path.join(outputDir, "metadata.json"),
      JSON.stringify(
        {
          passed,
          status: passed ? "passed" : "failed",
          cleanCanvas,
          cleanCanvasDetails,
          errors: browserErrors,
          screenshots,
          url,
          durationMs,
          summary,
          captured_at: Date.now() / 1000,
        },
        null,
        2
      )
    );
  } catch {
    // Ignore metadata write errors
  }

  if (emitTelemetry) {
    emitTelemetryEvent(
      {
        type: "visual_qa",
        stage: "VERIFIER",
        data: {
          passed,
          cleanCanvas,
          cleanCanvasDetails,
          errors: browserErrors,
          screenshots,
          url,
          durationMs,
          summary,
        },
      },
      { stream: options?.stream }
    );
  }

  return result;
}
