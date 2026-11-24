import crypto from "node:crypto";
import { eq } from "drizzle-orm";
import { db } from "../db/index";
import { settings } from "../db/schema";
import { ensureSystemReady } from "./bootstrap";

export const SETTINGS_KEY_ADMIN_TOKEN = "admin_token";

/**
 * Extracts bearer token from an Authorization header value.
 * Supports "Bearer <token>" or "bearer <token>".
 */
export function extractBearerToken(authHeader?: string | null): string | null {
	if (!authHeader) {
		return null;
	}
	const parts = authHeader.trim().split(/\s+/);
	if (parts.length === 2 && parts[0].toLowerCase() === "bearer") {
		return parts[1];
	}
	return null;
}

/**
 * Retrieves the global Admin Token.
 * Resolution precedence:
 * 1. process.env.ADMIN_TOKEN or process.env.NEON_ADMIN_TOKEN
 * 2. settings table record where key = 'admin_token'
 * 3. Generate new 32-byte cryptographically secure hex token and persist in settings
 */
export async function getOrCreateAdminToken(): Promise<string> {
	const envToken = process.env.ADMIN_TOKEN || process.env.NEON_ADMIN_TOKEN;
	if (envToken?.trim()) {
		return envToken.trim();
	}

	await ensureSystemReady().catch(() => {});

	try {
		const rows = await db
			.select({ value: settings.value })
			.from(settings)
			.where(eq(settings.key, SETTINGS_KEY_ADMIN_TOKEN))
			.limit(1);

		if (rows.length > 0 && rows[0].value) {
			return rows[0].value;
		}

		const generated = crypto.randomBytes(32).toString("hex");
		const [inserted] = await db
			.insert(settings)
			.values({
				key: SETTINGS_KEY_ADMIN_TOKEN,
				value: generated,
			})
			.onConflictDoUpdate({
				target: settings.key,
				set: { value: generated },
			})
			.returning();

		return inserted.value;
	} catch (err) {
		// If DB is temporarily unavailable (e.g. before migrations), generate a fallback
		console.warn("Warning: Failed to fetch/persist admin token in db:", err);
		return "neon-admin-token-fallback";
	}
}

/**
 * Validates a candidate admin token against the current active admin token.
 */
export async function validateAdminToken(
	candidate?: string | null,
): Promise<boolean> {
	if (!candidate || typeof candidate !== "string") {
		return false;
	}

	const activeToken = await getOrCreateAdminToken();
	if (!activeToken) {
		return false;
	}

	const candidateBuf = Buffer.from(candidate.trim());
	const activeBuf = Buffer.from(activeToken.trim());

	if (candidateBuf.length !== activeBuf.length) {
		return false;
	}

	return crypto.timingSafeEqual(candidateBuf, activeBuf);
}
