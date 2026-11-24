import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

export interface MasterDatabaseCredentials {
	username: string;
	password: string;
}

export interface StorageAdminCredentials {
	accessKeyId: string;
	secretAccessKey: string;
}

export const DEFAULT_ENV_FILE =
	typeof window === "undefined" && typeof process !== "undefined" && process.cwd
		? path.resolve(process.cwd(), ".env.local")
		: ".env.local";

/**
 * Parses simple KEY=VAL or KEY="VAL" pairs from an env file string.
 */
export function parseEnvContent(content: string): Record<string, string> {
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
 * Ensures PostgreSQL Master Database Credentials exist in the target env file
 * (defaulting to .env.local) and in process.env. If missing, generates a cryptographically
 * secure random 32-character hex password and appends to the env file.
 */
export function ensureMasterDatabaseCredentials(
	envFilePath = DEFAULT_ENV_FILE,
): MasterDatabaseCredentials {
	let fileContent = "";
	if (fs.existsSync(envFilePath)) {
		fileContent = fs.readFileSync(envFilePath, "utf-8");
	}

	const parsed = parseEnvContent(fileContent);
	const envUser =
		process.env.POSTGRES_USER ||
		process.env.POSTGRES_MASTER_USER ||
		parsed.POSTGRES_USER ||
		parsed.POSTGRES_MASTER_USER ||
		"postgres";

	const envPass =
		process.env.POSTGRES_PASSWORD ||
		process.env.POSTGRES_MASTER_PASSWORD ||
		parsed.POSTGRES_PASSWORD ||
		parsed.POSTGRES_MASTER_PASSWORD;

	if (envPass?.trim()) {
		const username = envUser.trim();
		const password = envPass.trim();
		process.env.POSTGRES_USER = username;
		process.env.POSTGRES_PASSWORD = password;
		return { username, password };
	}

	const username = envUser.trim();
	const password = crypto.randomBytes(16).toString("hex");

	const appendLines = [
		"",
		"# Neon Master Database Credentials (PostgreSQL Superuser)",
		`POSTGRES_USER="${username}"`,
		`POSTGRES_PASSWORD="${password}"`,
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

	process.env.POSTGRES_USER = username;
	process.env.POSTGRES_PASSWORD = password;

	return { username, password };
}

/**
 * Retrieves the PostgreSQL Master Database Credentials from process.env or .env.local.
 */
export function getMasterDatabaseCredentials(
	envFilePath = DEFAULT_ENV_FILE,
): MasterDatabaseCredentials {
	const envPass =
		process.env.POSTGRES_PASSWORD || process.env.POSTGRES_MASTER_PASSWORD;
	const envUser =
		process.env.POSTGRES_USER || process.env.POSTGRES_MASTER_USER || "postgres";

	if (envPass?.trim()) {
		return {
			username: envUser.trim(),
			password: envPass.trim(),
		};
	}

	return ensureMasterDatabaseCredentials(envFilePath);
}

/**
 * Ensures SeaweedFS Storage Admin Credentials exist in the target env file
 * (defaulting to .env.local) and in process.env. If missing, generates random access/secret keys
 * and appends to the env file.
 */
export function ensureStorageAdminCredentials(
	envFilePath = DEFAULT_ENV_FILE,
): StorageAdminCredentials {
	let fileContent = "";
	if (fs.existsSync(envFilePath)) {
		fileContent = fs.readFileSync(envFilePath, "utf-8");
	}

	const parsed = parseEnvContent(fileContent);
	const envKey =
		process.env.SEAWEEDFS_ADMIN_ACCESS_KEY || parsed.SEAWEEDFS_ADMIN_ACCESS_KEY;
	const envSecret =
		process.env.SEAWEEDFS_ADMIN_SECRET_KEY || parsed.SEAWEEDFS_ADMIN_SECRET_KEY;

	if (envKey?.trim() && envSecret?.trim()) {
		const accessKeyId = envKey.trim();
		const secretAccessKey = envSecret.trim();
		process.env.SEAWEEDFS_ADMIN_ACCESS_KEY = accessKeyId;
		process.env.SEAWEEDFS_ADMIN_SECRET_KEY = secretAccessKey;
		return { accessKeyId, secretAccessKey };
	}

	const accessKeyId =
		envKey?.trim() ||
		"AKIA" + crypto.randomBytes(8).toString("hex").toUpperCase();
	const secretAccessKey =
		envSecret?.trim() || crypto.randomBytes(20).toString("hex");

	const appendLines = [
		"",
		"# SeaweedFS Storage Admin Credentials",
		`SEAWEEDFS_ADMIN_ACCESS_KEY="${accessKeyId}"`,
		`SEAWEEDFS_ADMIN_SECRET_KEY="${secretAccessKey}"`,
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

	process.env.SEAWEEDFS_ADMIN_ACCESS_KEY = accessKeyId;
	process.env.SEAWEEDFS_ADMIN_SECRET_KEY = secretAccessKey;

	return { accessKeyId, secretAccessKey };
}

/**
 * Retrieves the SeaweedFS Storage Admin Credentials from process.env or .env.local.
 */
export function getStorageAdminCredentials(
	envFilePath = DEFAULT_ENV_FILE,
): StorageAdminCredentials {
	const envKey = process.env.SEAWEEDFS_ADMIN_ACCESS_KEY;
	const envSecret = process.env.SEAWEEDFS_ADMIN_SECRET_KEY;

	if (envKey?.trim() && envSecret?.trim()) {
		return {
			accessKeyId: envKey.trim(),
			secretAccessKey: envSecret.trim(),
		};
	}

	return ensureStorageAdminCredentials(envFilePath);
}
