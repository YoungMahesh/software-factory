import {
	ListObjectsV2Command,
	PutObjectCommand,
	DeleteObjectCommand,
	GetObjectCommand,
} from "@aws-sdk/client-s3";
import { z } from "zod";
import { eq, or } from "drizzle-orm";
import { db } from "../db/index";
import { objectStorages } from "../db/schema";
import { getAdminS3Client } from "./storage";
import { ensureSystemReady } from "./bootstrap";

export interface BucketObject {
	key: string;
	size: number;
	lastModified?: string;
	etag?: string;
}

export interface UploadObjectInput {
	storageId: string;
	key: string;
	content: string | Buffer;
	contentType?: string;
	isBase64?: boolean;
}

export interface UploadObjectResult {
	success: boolean;
	key: string;
	size: number;
	etag?: string;
}

export interface DownloadObjectResult {
	key: string;
	size: number;
	contentType: string;
	base64: string;
	text?: string;
	lastModified?: string;
	etag?: string;
}

/**
 * Resolves an object storage record from neon_control_plane by storageId or bucketName.
 */
export async function resolveStorageRecord(storageIdOrBucketName: string) {
	await ensureSystemReady().catch(() => {});

	const [record] = await db
		.select()
		.from(objectStorages)
		.where(
			or(
				eq(objectStorages.id, storageIdOrBucketName),
				eq(objectStorages.bucketName, storageIdOrBucketName),
			),
		)
		.limit(1);

	if (!record) {
		throw new Error(`Object storage not found for "${storageIdOrBucketName}"`);
	}

	return record;
}

/**
 * Lists all objects stored in a provisioned S3 bucket.
 * Returns an array of BucketObject entries containing key, size, lastModified, and etag.
 */
export async function listBucketObjects(
	storageIdOrBucketName: string,
): Promise<BucketObject[]> {
	const storage = await resolveStorageRecord(storageIdOrBucketName);
	const client = getAdminS3Client(storage.endpoint);

	try {
		const res = await client.send(
			new ListObjectsV2Command({
				Bucket: storage.bucketName,
			}),
		);

		const items: BucketObject[] = (res.Contents || []).map((item) => ({
			key: item.Key || "",
			size: item.Size ?? 0,
			lastModified: item.LastModified?.toISOString(),
			etag: item.ETag ? item.ETag.replace(/^"+|"+$/g, "") : undefined,
		}));

		// Sort alphabetically by key
		items.sort((a, b) => a.key.localeCompare(b.key));

		return items;
	} catch (err: any) {
		if (err.name === "NoSuchBucket" || err.message?.includes("not found")) {
			return [];
		}
		throw new Error(
			`Failed to list objects in bucket "${storage.bucketName}": ${err.message}`,
		);
	}
}

/**
 * Uploads an object to the specified S3 bucket.
 * Supports string content (utf8 or base64 data URLs) or raw Buffer payloads.
 */
export async function uploadBucketObject(
	input: UploadObjectInput,
): Promise<UploadObjectResult> {
	const storage = await resolveStorageRecord(input.storageId);
	const client = getAdminS3Client(storage.endpoint);

	const cleanKey = input.key?.trim();
	if (!cleanKey) {
		throw new Error("Object key is required");
	}

	let buffer: Buffer;
	let detectedContentType = input.contentType || "application/octet-stream";

	if (Buffer.isBuffer(input.content)) {
		buffer = input.content;
	} else if (typeof input.content === "string") {
		if (input.content.startsWith("data:")) {
			// Data URL: data:<mime>;base64,<payload>
			const match = input.content.match(/^data:([^;]+);base64,(.+)$/);
			if (match) {
				if (!input.contentType) {
					detectedContentType = match[1];
				}
				buffer = Buffer.from(match[2], "base64");
			} else {
				buffer = Buffer.from(input.content, "utf8");
			}
		} else if (input.isBase64) {
			buffer = Buffer.from(input.content, "base64");
		} else {
			buffer = Buffer.from(input.content, "utf8");
		}
	} else {
		throw new Error("Unsupported content type for upload");
	}

	try {
		const res = await client.send(
			new PutObjectCommand({
				Bucket: storage.bucketName,
				Key: cleanKey,
				Body: buffer,
				ContentType: detectedContentType,
			}),
		);

		return {
			success: true,
			key: cleanKey,
			size: buffer.length,
			etag: res.ETag ? res.ETag.replace(/^"+|"+$/g, "") : undefined,
		};
	} catch (err: any) {
		throw new Error(
			`Failed to upload object "${cleanKey}" to bucket "${storage.bucketName}": ${err.message}`,
		);
	}
}

/**
 * Deletes an object from the specified S3 bucket.
 */
export async function deleteBucketObject(
	storageIdOrBucketName: string,
	key: string,
): Promise<{ success: boolean; key: string }> {
	const storage = await resolveStorageRecord(storageIdOrBucketName);
	const client = getAdminS3Client(storage.endpoint);

	const cleanKey = key?.trim();
	if (!cleanKey) {
		throw new Error("Object key is required");
	}

	try {
		await client.send(
			new DeleteObjectCommand({
				Bucket: storage.bucketName,
				Key: cleanKey,
			}),
		);

		return {
			success: true,
			key: cleanKey,
		};
	} catch (err: any) {
		throw new Error(
			`Failed to delete object "${cleanKey}" from bucket "${storage.bucketName}": ${err.message}`,
		);
	}
}

/**
 * Retrieves an object's contents from S3, returning base64 encoding and utf-8 text representation.
 */
export async function getObjectContent(
	storageIdOrBucketName: string,
	key: string,
): Promise<DownloadObjectResult> {
	const storage = await resolveStorageRecord(storageIdOrBucketName);
	const client = getAdminS3Client(storage.endpoint);

	const cleanKey = key?.trim();
	if (!cleanKey) {
		throw new Error("Object key is required");
	}

	try {
		const res = await client.send(
			new GetObjectCommand({
				Bucket: storage.bucketName,
				Key: cleanKey,
			}),
		);

		const rawBytes = await res.Body?.transformToByteArray();
		if (!rawBytes) {
			throw new Error(`Empty body returned for object "${cleanKey}"`);
		}

		const buffer = Buffer.from(rawBytes);
		const base64 = buffer.toString("base64");
		const contentType = res.ContentType || "application/octet-stream";

		// Determine if content can be represented as text (e.g. no control characters / plain text)
		let text: string | undefined;
		const isTextMime =
			contentType.startsWith("text/") ||
			contentType.includes("json") ||
			contentType.includes("xml") ||
			contentType.includes("javascript") ||
			contentType.includes("svg");

		if (isTextMime || buffer.length < 500000) {
			try {
				const decoded = buffer.toString("utf8");
				// Check if contains null bytes (binary indicator)
				if (!decoded.includes("\0")) {
					text = decoded;
				}
			} catch {
				// ignore utf8 decoding error
			}
		}

		return {
			key: cleanKey,
			size: buffer.length,
			contentType,
			base64,
			text,
			lastModified: res.LastModified?.toISOString(),
			etag: res.ETag ? res.ETag.replace(/^"+|"+$/g, "") : undefined,
		};
	} catch (err: any) {
		throw new Error(
			`Failed to get object "${cleanKey}" from bucket "${storage.bucketName}": ${err.message}`,
		);
	}
}

// ==========================================
// TanStack Start Server Functions
// ==========================================

export const listBucketObjectsSchema = z.object({
	storageId: z.string().min(1, "Storage identifier is required"),
});

export async function listBucketObjectsFn(input: string | { data: string | { storageId: string } } | { storageId: string }): Promise<BucketObject[]> {
	const storageId = typeof input === "string" ? input : typeof (input as any)?.data === "string" ? (input as any).data : (input as any)?.data?.storageId || (input as any)?.storageId;
	return listBucketObjects(storageId);
}

export async function uploadBucketObjectFn(input: { data: UploadObjectInput } | UploadObjectInput): Promise<UploadObjectResult> {
	const data = "data" in input ? input.data : input;
	return uploadBucketObject(data);
}

export async function deleteBucketObjectFn(input: { data: { storageId: string; key: string } } | { storageId: string; key: string }): Promise<{ success: boolean; key: string }> {
	const data = "data" in input ? input.data : input;
	return deleteBucketObject(data.storageId, data.key);
}

export async function getObjectContentFn(input: { data: { storageId: string; key: string } } | { storageId: string; key: string }): Promise<DownloadObjectResult> {
	const data = "data" in input ? input.data : input;
	return getObjectContent(data.storageId, data.key);
}
