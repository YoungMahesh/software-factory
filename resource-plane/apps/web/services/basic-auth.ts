import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

export interface BasicAuthCredentials {
	username: string;
	password: string;
}

export const DEFAULT_ENV_FILE =
	typeof window === "undefined" && typeof process !== "undefined" && process.cwd
		? path.resolve(process.cwd(), ".env.local")
		: ".env.local";

/**
 * Extracts username and password from an Authorization header value.
 * Supports "Basic <base64>" or "basic <base64>".
 */
export function extractBasicAuthCredentials(
	authHeader?: string | null,
): BasicAuthCredentials | null {
	if (!authHeader) {
		return null;
	}

	const parts = authHeader.trim().split(/\s+/);
	if (parts.length !== 2 || parts[0].toLowerCase() !== "basic") {
		return null;
	}

	const base64Payload = parts[1];
	if (!/^[A-Za-z0-9+/=]+$/.test(base64Payload)) {
		return null;
	}

	try {
		const decoded = Buffer.from(base64Payload, "base64").toString("utf-8");
		const colonIndex = decoded.indexOf(":");
		if (colonIndex === -1) {
			return null;
		}

		const username = decoded.slice(0, colonIndex);
		const password = decoded.slice(colonIndex + 1);

		return { username, password };
	} catch {
		return null;
	}
}

/**
 * Parses simple KEY=VAL or KEY="VAL" pairs from an env file string.
 */
function parseEnvContent(content: string): Record<string, string> {
	const result: Record<string, string> = {};
	const lines = content.split("\n");
	for (const line of lines) {
		const trimmed = line.trim();
		if (!trimmed || trimmed.startsWith("#")) continue;
		const eqIdx = trimmed.indexOf("=");
		if (eqIdx === -1) continue;
		const key = trimmed.slice(0, eqIdx).trim();
		let val = trimmed.slice(eqIdx + 1).trim();
		if (
			(val.startsWith('"') && val.endsWith('"')) ||
			(val.startsWith("'") && val.endsWith("'"))
		) {
			val = val.slice(1, -1);
		}
		result[key] = val;
	}
	return result;
}

/**
 * Ensures Control Plane basic auth credentials exist in the target env file (defaulting to .env.local)
 * and in process.env. If missing, generates a secure random password, appends to the file, and logs to terminal stdout.
 */
export function ensureControlPlaneCredentialsInEnv(
	envFilePath = DEFAULT_ENV_FILE,
): BasicAuthCredentials {
	let fileContent = "";
	if (fs.existsSync(envFilePath)) {
		fileContent = fs.readFileSync(envFilePath, "utf-8");
	}

	const parsed = parseEnvContent(fileContent);
	const envUser =
		process.env.BASIC_AUTH_USERNAME ||
		process.env.CONTROL_PLANE_USERNAME ||
		parsed.BASIC_AUTH_USERNAME ||
		parsed.CONTROL_PLANE_USERNAME;

	const envPass =
		process.env.BASIC_AUTH_PASSWORD ||
		process.env.CONTROL_PLANE_PASSWORD ||
		parsed.BASIC_AUTH_PASSWORD ||
		parsed.CONTROL_PLANE_PASSWORD;

	if (envPass?.trim()) {
		const username = envUser?.trim() || "admin";
		const password = envPass.trim();
		process.env.BASIC_AUTH_USERNAME = username;
		process.env.BASIC_AUTH_PASSWORD = password;
		return { username, password };
	}

	// Generate new random credentials
	const username = envUser?.trim() || "admin";
	const password = crypto.randomBytes(16).toString("hex");

	const appendLines = [
		"",
		"# Neon Control Plane Basic Authentication",
		`BASIC_AUTH_USERNAME="${username}"`,
		`BASIC_AUTH_PASSWORD="${password}"`,
		"",
	].join("\n");

	try {
		const newContent = fileContent
			? `${fileContent.trimEnd()}\n${appendLines}`
			: appendLines;
		fs.writeFileSync(envFilePath, newContent, "utf-8");
	} catch (err) {
		console.warn(
			`Warning: Could not write credentials to ${envFilePath}:`,
			err,
		);
	}

	process.env.BASIC_AUTH_USERNAME = username;
	process.env.BASIC_AUTH_PASSWORD = password;

	return { username, password };
}

/**
 * Retrieves the Control Plane credentials from process.env or .env.local.
 * Strictly decoupled from the system database.
 */
export function getOrCreateControlPlaneCredentials(
	envFilePath = DEFAULT_ENV_FILE,
): BasicAuthCredentials {
	const envPass =
		process.env.BASIC_AUTH_PASSWORD || process.env.CONTROL_PLANE_PASSWORD;
	const envUser =
		process.env.BASIC_AUTH_USERNAME || process.env.CONTROL_PLANE_USERNAME;

	if (envPass?.trim()) {
		return {
			username: envUser?.trim() || "admin",
			password: envPass.trim(),
		};
	}

	return ensureControlPlaneCredentialsInEnv(envFilePath);
}

/**
 * Validates candidate credentials against the active Control Plane credentials
 * using constant-time timing-safe comparison.
 */
export function validateControlPlaneCredentials(
	candidate?: { username?: string | null; password?: string | null } | null,
	envFilePath = DEFAULT_ENV_FILE,
): boolean {
	if (
		!candidate ||
		typeof candidate.username !== "string" ||
		typeof candidate.password !== "string"
	) {
		return false;
	}

	const active = getOrCreateControlPlaneCredentials(envFilePath);
	if (!active || !active.username || !active.password) {
		return false;
	}

	const candUserBuf = Buffer.from(candidate.username.trim());
	const activeUserBuf = Buffer.from(active.username.trim());
	const candPassBuf = Buffer.from(candidate.password.trim());
	const activePassBuf = Buffer.from(active.password.trim());

	if (
		candUserBuf.length !== activeUserBuf.length ||
		candPassBuf.length !== activePassBuf.length
	) {
		return false;
	}

	const userMatch = crypto.timingSafeEqual(candUserBuf, activeUserBuf);
	const passMatch = crypto.timingSafeEqual(candPassBuf, activePassBuf);

	return userMatch && passMatch;
}

/**
 * Constructs an RFC 7617 401 Unauthorized Response prompting the browser for Basic Auth.
 */
export function createBasicAuthChallengeResponse(): Response {
	return new Response(
		"Unauthorized: Neon Control Plane requires authentication.\n",
		{
			status: 401,
			headers: {
				"WWW-Authenticate": 'Basic realm="Neon Control Plane", charset="UTF-8"',
				"Content-Type": "text/plain; charset=utf-8",
			},
		},
	);
}

/**
 * Checks if a requested path or URL should be exempted from Basic Authentication.
 * Exemptions include:
 * - /mcp (secured independently via Bearer Admin Token)
 * - Internal Vite and development static assets (/@vite, /@fs, /@id, /favicon.ico)
 */
export function isExemptFromBasicAuth(urlOrPath: string | URL): boolean {
	let pathname: string;

	if (typeof urlOrPath === "string") {
		if (urlOrPath.startsWith("http://") || urlOrPath.startsWith("https://")) {
			try {
				pathname = new URL(urlOrPath).pathname;
			} catch {
				pathname = urlOrPath.split("?")[0];
			}
		} else {
			pathname = urlOrPath.split("?")[0];
		}
	} else {
		pathname = urlOrPath.pathname;
	}

	// MCP endpoint is protected separately via Bearer Admin Token
	if (pathname === "/mcp" || pathname.startsWith("/mcp/")) {
		return true;
	}

	// Public Root CA Certificate endpoint
	if (pathname === "/api/ca.crt") {
		return true;
	}

	// Vite development and static asset requests
	if (
		pathname.startsWith("/@vite") ||
		pathname.startsWith("/@fs") ||
		pathname.startsWith("/@id") ||
		pathname === "/favicon.ico"
	) {
		return true;
	}

	return false;
}
