#!/usr/bin/env node

/**
 * Mobile Client Device Sideload Server
 *
 * Ephemeral local HTTP server that exposes the built Android APK over the network,
 * generating a terminal ASCII QR code for camera scanning and outputting
 * copy-pasteable shell commands for instant phone installation.
 */

const http = require("http");
const fs = require("fs");
const path = require("path");
const os = require("os");

const DEFAULT_PORT = 8082;

function loadMobileAppMeta(baseDir = path.resolve(__dirname, "..")) {
  const appJsonPath = path.join(baseDir, "app.json");
  let name = "Mobile App";
  let slug = "mobile-app";
  let basePackageId = "com.app.mobile";

  if (fs.existsSync(appJsonPath)) {
    try {
      const parsed = JSON.parse(fs.readFileSync(appJsonPath, "utf-8"));
      const expo = parsed && parsed.expo ? parsed.expo : {};
      if (expo.name) name = String(expo.name);
      if (expo.slug) slug = String(expo.slug);
      if (expo.android && expo.android.package) {
        basePackageId = String(expo.android.package);
      }
    } catch {
      // Fallback to defaults when app.json cannot be parsed
    }
  }

  return { name, slug, basePackageId };
}

function parseArgs(argv = process.argv.slice(2)) {
  const options = {
    port: DEFAULT_PORT,
    host: "",
    env: "dev",
    variant: "",
    file: "",
    noQr: false,
    help: false,
  };

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "-h" || arg === "--help") {
      options.help = true;
    } else if (arg === "-p" || arg === "--port") {
      options.port = parseInt(argv[++i], 10) || DEFAULT_PORT;
    } else if (arg.startsWith("--port=")) {
      options.port = parseInt(arg.split("=")[1], 10) || DEFAULT_PORT;
    } else if (arg === "-H" || arg === "--host") {
      options.host = argv[++i] || "";
    } else if (arg.startsWith("--host=")) {
      options.host = arg.split("=")[1] || "";
    } else if (arg === "-e" || arg === "--env") {
      options.env = (argv[++i] || "dev").toLowerCase();
    } else if (arg.startsWith("--env=")) {
      options.env = (arg.split("=")[1] || "dev").toLowerCase();
    } else if (arg === "-v" || arg === "--variant") {
      options.variant = (argv[++i] || "").toLowerCase();
    } else if (arg.startsWith("--variant=")) {
      options.variant = (arg.split("=")[1] || "").toLowerCase();
    } else if (arg === "-f" || arg === "--file") {
      options.file = argv[++i] || "";
    } else if (arg.startsWith("--file=")) {
      options.file = arg.split("=")[1] || "";
    } else if (arg === "--no-qr") {
      options.noQr = true;
    }
  }

  if (options.env === "development") {
    options.env = "dev";
  } else if (options.env === "production") {
    options.env = "prod";
  }

  if (!options.variant) {
    options.variant = options.env === "prod" ? "release" : "debug";
  }

  if (!options.host && process.env.PUBLIC_URL) {
    try {
      const parsed = new URL(process.env.PUBLIC_URL);
      options.host = parsed.host;
    } catch {
      options.host = process.env.PUBLIC_URL;
    }
  } else if (!options.host && process.env.HOST) {
    options.host = process.env.HOST;
  }

  return options;
}

function resolveNetworkHost(customHost) {
  if (customHost && customHost.trim().length > 0) {
    return customHost.trim();
  }

  const interfaces = os.networkInterfaces();
  const candidates = [];

  for (const name of Object.keys(interfaces)) {
    for (const net of interfaces[name] || []) {
      if (net.family === "IPv4" && !net.internal) {
        if (net.address.startsWith("192.168.")) {
          return net.address;
        }
        candidates.push(net.address);
      }
    }
  }

  if (candidates.length > 0) {
    return candidates[0];
  }

  return "localhost";
}

function findApkFile(variant = "debug", customPath = "", baseDir = path.resolve(__dirname, ".."), env = "dev") {
  if (customPath) {
    const resolved = path.isAbsolute(customPath) ? customPath : path.resolve(process.cwd(), customPath);
    if (fs.existsSync(resolved)) {
      return resolved;
    }
    return null;
  }

  const { slug } = loadMobileAppMeta(baseDir);
  const distDir = path.join(baseDir, "dist");
  const candidates = [
    path.join(distDir, `${slug}-${env}.apk`),
    path.join(distDir, `app-${env}.apk`),
    path.join(distDir, `${slug}-${variant}.apk`),
    path.join(distDir, `app-${variant}.apk`),
    path.join(distDir, "app.apk"),
    path.join(distDir, "app-debug.apk"),
    path.join(baseDir, "android/app/build/outputs/apk", env, variant, `app-${env}-${variant}.apk`),
    path.join(baseDir, "android/app/build/outputs/apk", env, variant, `app-${env}-${variant}-unsigned.apk`),
    path.join(baseDir, "android/app/build/outputs/apk", variant, `app-${variant}.apk`),
    path.join(baseDir, "android/app/build/outputs/apk/debug/app-debug.apk"),
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }

  return null;
}

function formatBytes(bytes) {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

function renderHtmlLandingPage({ filename, fileSizeFormatted, variant, env = "dev", downloadUrl, appTitle, packageId }) {
  const isDev = env === "dev" || env === "development";
  const targetEnvLabel = isDev ? "Development" : "Production";

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${appTitle} · APK Sideload</title>
  <style>
    :root {
      --canvas: #faf9f5;
      --card: #f5f2eb;
      --card-border: #e6dfd8;
      --ink: #141413;
      --ink-muted: #827f79;
      --primary: #cc785c;
      --primary-hover: #b8694f;
      --serif: "Newsreader", "Charter", "Georgia", serif;
      --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--canvas);
      color: var(--ink);
      font-family: var(--sans);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1.5rem;
    }
    .container {
      background: var(--card);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      max-width: 480px;
      width: 100%;
      padding: 2rem;
      box-shadow: 0 4px 24px rgba(20, 20, 19, 0.04);
    }
    .badge {
      display: inline-block;
      background: rgba(204, 120, 92, 0.12);
      color: var(--primary);
      padding: 4px 10px;
      border-radius: 20px;
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 1rem;
    }
    h1 {
      font-family: var(--serif);
      font-size: 1.85rem;
      font-weight: 500;
      line-height: 1.25;
      margin-bottom: 0.5rem;
    }
    p.lead {
      color: var(--ink-muted);
      font-size: 0.95rem;
      line-height: 1.5;
      margin-bottom: 1.75rem;
    }
    .meta-box {
      background: #ffffff;
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 1rem;
      margin-bottom: 1.75rem;
      font-size: 0.85rem;
    }
    .meta-row {
      display: flex;
      justify-content: space-between;
      padding: 4px 0;
    }
    .meta-label { color: var(--ink-muted); }
    .meta-value { font-family: monospace; font-weight: 600; }
    .btn-download {
      display: block;
      width: 100%;
      text-align: center;
      background: var(--primary);
      color: #ffffff;
      text-decoration: none;
      padding: 14px 20px;
      border-radius: 10px;
      font-weight: 600;
      font-size: 1rem;
      transition: background-color 0.15s ease;
    }
    .btn-download:hover { background: var(--primary-hover); }
    .instructions {
      margin-top: 1.75rem;
      border-top: 1px solid var(--card-border);
      padding-top: 1.25rem;
      font-size: 0.8rem;
      color: var(--ink-muted);
      line-height: 1.6;
    }
    .instructions ol { margin-left: 1.25rem; margin-top: 0.5rem; }
  </style>
</head>
<body>
  <div class="container">
    <span class="badge">${env.toUpperCase()} · ${variant} build</span>
    <h1>${appTitle}</h1>
    <p class="lead">Native Android Mobile Client ready for direct installation.</p>

    <div class="meta-box">
      <div class="meta-row">
        <span class="meta-label">Artifact</span>
        <span class="meta-value">${filename}</span>
      </div>
      <div class="meta-row">
        <span class="meta-label">Environment</span>
        <span class="meta-value">${targetEnvLabel}</span>
      </div>
      <div class="meta-row">
        <span class="meta-label">File Size</span>
        <span class="meta-value">${fileSizeFormatted}</span>
      </div>
      <div class="meta-row">
        <span class="meta-label">Package</span>
        <span class="meta-value">${packageId}</span>
      </div>
    </div>

    <a href="${downloadUrl}" class="btn-download" download="${filename}">Download &amp; Install APK</a>

    <div class="instructions">
      <strong>Installation Instructions:</strong>
      <ol>
        <li>Tap the download button above on your Android device.</li>
        <li>When prompted by Android, grant permission to "Install unknown apps" for your browser.</li>
        <li>Open the completed APK download and tap <strong>Install</strong>.</li>
      </ol>
    </div>
  </div>
</body>
</html>`;
}

function createServer(apkPath, options = {}) {
  const stat = fs.statSync(apkPath);
  const filename = path.basename(apkPath);
  const variant = options.variant || "debug";
  const env = options.env || "dev";
  const isDev = env === "dev" || env === "development";
  const meta = loadMobileAppMeta(options.baseDir);
  const appName = isDev ? `${meta.name} Dev` : meta.name;
  const packageId = isDev ? `${meta.basePackageId}.dev` : meta.basePackageId;
  const port = options.port || DEFAULT_PORT;
  const host = options.host || "localhost";

  const baseProtocol = host.startsWith("https://") ? "https://" : (host.startsWith("http://") ? "http://" : "http://");
  const cleanedHost = host.replace(/^https?:\/\//, "");
  const baseUrl = host.startsWith("http://") || host.startsWith("https://")
    ? host.replace(/\/$/, "")
    : `${baseProtocol}${cleanedHost.includes(":") ? cleanedHost : `${cleanedHost}:${port}`}`;

  const apkUrl = `${baseUrl}/${filename}`;

  const server = http.createServer((req, res) => {
    const parsedUrl = new URL(req.url, `http://${req.headers.host || "localhost"}`);
    const pathname = parsedUrl.pathname;

    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS");

    if (req.method === "OPTIONS") {
      res.writeHead(204);
      res.end();
      return;
    }

    if (pathname === "/health" || pathname === "/status") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(
        JSON.stringify({
          status: "ok",
          env,
          variant,
          apk: filename,
          appName,
          packageId,
          sizeBytes: stat.size,
          sizeFormatted: formatBytes(stat.size),
          downloadUrl: apkUrl,
        })
      );
      return;
    }

    const acceptHeader = req.headers.accept || "";
    if ((pathname === "/" || pathname === "/index.html") && req.method === "GET" && acceptHeader.includes("text/html")) {
      const html = renderHtmlLandingPage({
        filename,
        fileSizeFormatted: formatBytes(stat.size),
        variant,
        env,
        downloadUrl: apkUrl,
        appTitle: appName,
        packageId,
      });
      res.writeHead(200, {
        "Content-Type": "text/html; charset=utf-8",
        "Content-Length": Buffer.byteLength(html),
      });
      res.end(html);
      return;
    }

    if (
      pathname === "/" ||
      pathname === "/download" ||
      pathname === `/${filename}` ||
      pathname === "/app.apk" ||
      pathname === `/app-${variant}.apk` ||
      pathname === `/app-${env}.apk` ||
      pathname === `/${meta.slug}.apk` ||
      pathname === `/${meta.slug}-${variant}.apk` ||
      pathname === `/${meta.slug}-${env}.apk`
    ) {
      if (req.method === "HEAD") {
        res.writeHead(200, {
          "Content-Type": "application/vnd.android.package-archive",
          "Content-Length": stat.size,
          "Content-Disposition": `attachment; filename="${filename}"`,
        });
        res.end();
        return;
      }

      if (req.method === "GET") {
        res.writeHead(200, {
          "Content-Type": "application/vnd.android.package-archive",
          "Content-Length": stat.size,
          "Content-Disposition": `attachment; filename="${filename}"`,
          "Cache-Control": "no-cache",
        });

        const fileStream = fs.createReadStream(apkPath);
        fileStream.pipe(res);
        fileStream.on("error", (err) => {
          if (!res.headersSent) {
            res.writeHead(500, { "Content-Type": "text/plain" });
            res.end(`Internal Server Error: ${err.message}`);
          }
        });
        return;
      }
    }

    res.writeHead(404, { "Content-Type": "text/plain" });
    res.end(`Not Found: ${pathname}`);
  });

  return { server, apkUrl, filename, stat, appName, packageId };
}

function startServer(args = process.argv.slice(2)) {
  const options = parseArgs(args);

  if (options.help) {
    console.log(`Mobile Device Sideload Server

Usage:
  node serve-apk.js [options]

Options:
  -e, --env <dev|prod>    Target environment to serve (default: dev)
  -v, --variant <string>  Target build variant to serve (default: debug for dev, release for prod)
  -p, --port <number>     Port to listen on (default: ${DEFAULT_PORT})
  -H, --host <string>     Host IP or domain override for download URL and QR code
  -f, --file <path>       Direct path to custom APK binary
      --no-qr             Suppress terminal ASCII QR code
  -h, --help              Display this help message
`);
    process.exit(0);
  }

  const baseDir = path.resolve(__dirname, "..");
  const apkPath = findApkFile(options.variant, options.file, baseDir, options.env);
  if (!apkPath) {
    console.error(`\x1b[31m[ERROR] No installable APK artifact found for environment "${options.env}" (variant "${options.variant}").\x1b[0m`);
    console.error(`Please compile an APK first with:`);
    console.error(`   \x1b[33mpnpm mobile:build-apk\x1b[0m\n`);
    process.exit(1);
  }

  const host = resolveNetworkHost(options.host);
  const { server, apkUrl, filename, stat, appName, packageId } = createServer(apkPath, {
    port: options.port,
    host,
    variant: options.variant,
    env: options.env,
    baseDir,
  });

  server.listen(options.port, "0.0.0.0", () => {
    const sizeStr = formatBytes(stat.size);
    const targetEnvLabel = options.env === "prod" ? "Production" : "Development";

    console.log("\n\x1b[1m\x1b[38;2;204;120;92m┌────────────────────────────────────────────────────────┐\x1b[0m");
    console.log("\x1b[1m\x1b[38;2;204;120;92m│             Mobile Device Sideload Server              │\x1b[0m");
    console.log("\x1b[1m\x1b[38;2;204;120;92m└────────────────────────────────────────────────────────┘\x1b[0m");
    console.log(` \x1b[36mArtifact\x1b[0m     : ${filename} (${sizeStr})`);
    console.log(` \x1b[36mEnvironment\x1b[0m  : ${targetEnvLabel} (${options.env})`);
    console.log(` \x1b[36mApp Name\x1b[0m     : ${appName}`);
    console.log(` \x1b[36mVariant\x1b[0m      : ${options.variant}`);
    console.log(` \x1b[36mPackage\x1b[0m      : ${packageId}`);
    console.log(` \x1b[36mListen Port\x1b[0m  : ${options.port} (0.0.0.0)`);
    console.log(` \x1b[36mResolved URL\x1b[0m : \x1b[4m${apkUrl}\x1b[0m\n`);

    if (!options.noQr) {
      const qrcode = require("qrcode-terminal");
      console.log("\x1b[1m📱 Scan QR Code with your phone camera to download:\x1b[0m");
      qrcode.generate(apkUrl, { small: true }, (qr) => {
        console.log(qr);
      });
    }

    console.log("\x1b[1m💻 Direct Browser Link:\x1b[0m");
    console.log(`   ${apkUrl}\n`);

    console.log("\x1b[1m🚀 Phone Shell / Termux One-Line Command:\x1b[0m");
    console.log(`   curl -fSL "${apkUrl}" -o ${filename} && termux-open ${filename}\n`);

    console.log("\x1b[1m🔌 Direct ADB Sideload Command (if attached via USB/Wi-Fi):\x1b[0m");
    console.log(`   adb install -r "${apkPath}"\n`);

    console.log("\x1b[90mPress Ctrl+C to stop the server.\x1b[0m\n");
  });

  const cleanup = () => {
    console.log("\nStopping Device Sideload Server...");
    server.close(() => {
      process.exit(0);
    });
  };

  process.on("SIGINT", cleanup);
  process.on("SIGTERM", cleanup);

  return server;
}

if (require.main === module) {
  startServer();
}

module.exports = {
  loadMobileAppMeta,
  parseArgs,
  resolveNetworkHost,
  findApkFile,
  formatBytes,
  renderHtmlLandingPage,
  createServer,
  startServer,
};
