export * from "../lib/storage-helpers";
import { validateBucketName, formatStorageCredentials, type ObjectStorage, type StorageCredentials } from "../lib/storage-helpers";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import {
	S3Client,
	CreateBucketCommand,
	DeleteBucketCommand,
	HeadBucketCommand,
	ListObjectsV2Command,
	DeleteObjectsCommand,
} from "@aws-sdk/client-s3";
import { eq, desc } from "drizzle-orm";
import { z } from "zod";
import { db } from "../db/index";
import { objectStorages, projects } from "../db/schema";
import { dockerRequest, inspectContainer } from "./docker";
import { ensureSystemReady, SEAWEEDFS_CONTAINER_NAME } from "./bootstrap";
import { getStorageAdminCredentials } from "./master-credentials";

export const DEFAULT_S3_ENDPOINT =
	process.env.AWS_ENDPOINT_URL_S3 ||
	(process.env.PUBLIC_POSTGRES_HOST
		? `http://${process.env.PUBLIC_POSTGRES_HOST}:8333`
		: "http://localhost:8333");
export const DEFAULT_S3_REGION = process.env.AWS_REGION || "us-east-1";

export const getAdminAccessKey = (): string =>
	getStorageAdminCredentials().accessKeyId;
export const getAdminSecretKey = (): string =>
	getStorageAdminCredentials().secretAccessKey;

export const ADMIN_ACCESS_KEY =
	process.env.SEAWEEDFS_ADMIN_ACCESS_KEY ||
	(typeof window === "undefined" ? getAdminAccessKey() : "");
export const ADMIN_SECRET_KEY =
	process.env.SEAWEEDFS_ADMIN_SECRET_KEY ||
	(typeof window === "undefined" ? getAdminSecretKey() : "");





export interface CreateObjectStorageInput {
	projectId: string;
	bucketName: string;
	endpoint?: string;
	region?: string;
}

export interface S3IdentityCredential {
	accessKey: string;
	secretKey: string;
}

export interface S3Identity {
	name: string;
	credentials: S3IdentityCredential[];
	actions: string[];
}

export interface S3Config {
	identities: S3Identity[];
}

/**
 * Validates an S3 bucket name according to standard rules:
 * - 3 to 63 characters
 * - lowercase alphanumeric characters and hyphens only
 * - must start and end with a lowercase letter or number
 */


export function generateS3Credentials(): {
	accessKeyId: string;
	secretAccessKey: string;
} {
	const accessKeyId =
		"AKIA" + crypto.randomBytes(8).toString("hex").toUpperCase();
	const secretAccessKey = crypto.randomBytes(20).toString("hex");
	return { accessKeyId, secretAccessKey };
}

export function getAdminS3Client(endpoint = DEFAULT_S3_ENDPOINT): S3Client {
	const creds = getStorageAdminCredentials();
	let targetEndpoint = endpoint;
	if (process.env.SEAWEEDFS_HOST) {
		const internalHost = process.env.SEAWEEDFS_HOST;
		try {
			const url = new URL(targetEndpoint);
			if (
				url.hostname === "localhost" ||
				url.hostname === "127.0.0.1" ||
				url.hostname === process.env.PUBLIC_POSTGRES_HOST ||
				url.hostname === process.env.PUBLIC_HOST
			) {
				url.hostname = internalHost;
				targetEndpoint = url.toString();
			}
		} catch {
			// ignore URL parse error
		}
	}
	return new S3Client({
		endpoint: targetEndpoint,
		region: DEFAULT_S3_REGION,
		credentials: {
			accessKeyId: creds.accessKeyId,
			secretAccessKey: creds.secretAccessKey,
		},
		forcePathStyle: true,
	});
}

/**
 * Resolves all candidate paths on the host where SeaweedFS s3.json might reside:
 * 1. Current working directory .data/seaweedfs/s3.json
 * 2. Host bound directory of the running neon-seaweedfs container
 * 3. /root/neon/.data/seaweedfs/s3.json
 */
export async function getS3ConfigFilePaths(): Promise<string[]> {
	const paths: string[] = [];
	if (process.env.DATA_DIR) {
		const envDataPath = path.resolve(
			process.env.DATA_DIR,
			"seaweedfs",
			"s3.json",
		);
		if (!paths.includes(envDataPath)) {
			paths.push(envDataPath);
		}
	}

	const cwdPath = path.resolve(process.cwd(), ".data", "seaweedfs", "s3.json");
	if (!paths.includes(cwdPath)) {
		paths.push(cwdPath);
	}

	const parentCwdPath = path.resolve(
		process.cwd(),
		"..",
		"..",
		".data",
		"seaweedfs",
		"s3.json",
	);
	if (!paths.includes(parentCwdPath)) {
		paths.push(parentCwdPath);
	}

	try {
		const inspect = await inspectContainer(SEAWEEDFS_CONTAINER_NAME);
		const binds = inspect?.HostConfig?.Binds || [];
		for (const bind of binds) {
			if (bind.includes(":/data")) {
				const hostDir = bind.slice(0, bind.indexOf(":/data"));
				const hostPath = path.resolve(hostDir, "s3.json");
				if (!paths.includes(hostPath)) {
					paths.push(hostPath);
				}
			}
		}
	} catch {
		// container inspection optional
	}

	const rootNeonPath = path.resolve(
		"/root/neon",
		".data",
		"seaweedfs",
		"s3.json",
	);
	if (!paths.includes(rootNeonPath)) {
		paths.push(rootNeonPath);
	}

	return paths;
}

export async function readS3Config(): Promise<S3Config> {
	const candidatePaths = await getS3ConfigFilePaths();
	for (const filePath of candidatePaths) {
		if (fs.existsSync(filePath)) {
			try {
				const raw = fs.readFileSync(filePath, "utf8");
				const parsed = JSON.parse(raw);
				if (Array.isArray(parsed.identities)) {
					return parsed as S3Config;
				}
			} catch {
				// try next candidate
			}
		}
	}
	return { identities: [] };
}

export function ensureAdminIdentity(config: S3Config): void {
	const creds = getStorageAdminCredentials();
	const admin = config.identities.find((id) => id.name === "admin");
	if (!admin) {
		config.identities.unshift({
			name: "admin",
			credentials: [
				{
					accessKey: creds.accessKeyId,
					secretKey: creds.secretAccessKey,
				},
			],
			actions: ["Admin", "Read", "List", "Tagging", "Write"],
		});
	} else {
		admin.credentials = [
			{
				accessKey: creds.accessKeyId,
				secretKey: creds.secretAccessKey,
			},
		];
		admin.actions = ["Admin", "Read", "List", "Tagging", "Write"];
	}
}

export async function writeS3ConfigAndReload(config: S3Config): Promise<void> {
	ensureAdminIdentity(config);
	const candidatePaths = await getS3ConfigFilePaths();
	const payload = JSON.stringify(config, null, 2);

	for (const filePath of candidatePaths) {
		try {
			const parentDir = path.dirname(filePath);
			if (!fs.existsSync(parentDir)) {
				fs.mkdirSync(parentDir, { recursive: true });
			}
			fs.writeFileSync(filePath, payload, "utf8");
		} catch {
			// Continue writing to other candidate paths
		}
	}

	// Trigger SIGHUP on SeaweedFS container to reload credentials instantly
	try {
		await dockerRequest(
			`/containers/${SEAWEEDFS_CONTAINER_NAME}/kill?signal=SIGHUP`,
			"POST",
		);
	} catch {
		// SIGHUP may fail if container is not running (e.g. in mocked test env)
	}
}

/**
 * Creates a new S3-compatible bucket on SeaweedFS with discrete IAM credentials
 * restricted exclusively to the allocated bucket.
 */
export async function createObjectStorage(
	input: CreateObjectStorageInput,
): Promise<ObjectStorage> {
	await ensureSystemReady().catch(() => {});

	const validation = validateBucketName(input.bucketName);
	if (!validation.valid) {
		throw new Error(validation.error);
	}
	const bucketName = input.bucketName.trim().toLowerCase();

	// Verify project exists
	const [project] = await db
		.select({ id: projects.id })
		.from(projects)
		.where(eq(projects.id, input.projectId))
		.limit(1);

	if (!project) {
		throw new Error(`Project with ID ${input.projectId} does not exist`);
	}

	// Check if bucket already exists in object_storages table
	const [existingStorage] = await db
		.select({ id: objectStorages.id })
		.from(objectStorages)
		.where(eq(objectStorages.bucketName, bucketName))
		.limit(1);

	if (existingStorage) {
		throw new Error(`Bucket "${bucketName}" already exists`);
	}

	const endpoint = input.endpoint?.trim() || DEFAULT_S3_ENDPOINT;
	const region = input.region?.trim() || DEFAULT_S3_REGION;

	// Check if bucket already exists in SeaweedFS
	const adminClient = getAdminS3Client(endpoint);
	try {
		await adminClient.send(new HeadBucketCommand({ Bucket: bucketName }));
		throw new Error(`Bucket "${bucketName}" already exists`);
	} catch (err: any) {
		if (err.message === `Bucket "${bucketName}" already exists`) {
			throw err;
		}
		// NotFound / 404 is expected when bucket doesn't exist
	}

	// Generate discrete credentials
	const { accessKeyId, secretAccessKey } = generateS3Credentials();

	// 1. Configure IAM identity in s3.json
	const config = await readS3Config();
	const identityName = `storage_${bucketName}_${Date.now()}`;

	config.identities.push({
		name: identityName,
		credentials: [
			{
				accessKey: accessKeyId,
				secretKey: secretAccessKey,
			},
		],
		actions: [
			`Read:${bucketName}`,
			`List:${bucketName}`,
			`Tagging:${bucketName}`,
			`Write:${bucketName}`,
		],
	});

	await writeS3ConfigAndReload(config);

	// 2. Create the bucket via S3 API using admin credentials
	try {
		await adminClient.send(new CreateBucketCommand({ Bucket: bucketName }));
	} catch (err: any) {
		if (
			err.name === "BucketAlreadyExists" ||
			err.name === "BucketAlreadyOwnedByYou" ||
			err.message?.includes("already exists")
		) {
			throw new Error(`Bucket "${bucketName}" already exists`);
		}
		throw new Error(
			`Failed to create S3 bucket "${bucketName}": ${err.message}`,
		);
	}

	// 3. Persist metadata in object_storages table
	const [created] = await db
		.insert(objectStorages)
		.values({
			projectId: input.projectId,
			bucketName,
			accessKeyId,
			secretAccessKey,
			endpoint,
			region,
		})
		.returning();

	return created;
}

/**
 * Lists all Object Storages for a project.
 */
export async function listObjectStorages(
	projectId: string,
): Promise<ObjectStorage[]> {
	await ensureSystemReady().catch(() => {});

	return await db
		.select()
		.from(objectStorages)
		.where(eq(objectStorages.projectId, projectId))
		.orderBy(desc(objectStorages.createdAt));
}

/**
 * Retrieves credentials for a given Object Storage.
 */
export async function getStorageCredentials(
	id: string,
): Promise<StorageCredentials | null> {
	await ensureSystemReady().catch(() => {});

	const [record] = await db
		.select()
		.from(objectStorages)
		.where(eq(objectStorages.id, id))
		.limit(1);

	if (!record) {
		return null;
	}

	return {
		id: record.id,
		projectId: record.projectId,
		bucketName: record.bucketName,
		accessKeyId: record.accessKeyId,
		secretAccessKey: record.secretAccessKey,
		endpoint: record.endpoint,
		region: record.region,
	};
}

/**
 * Safely deletes an Object Storage bucket, revokes its IAM credentials,
 * reloads SeaweedFS, and deletes the database record.
 */
export async function deleteObjectStorage(id: string): Promise<boolean> {
	await ensureSystemReady().catch(() => {});

	const [record] = await db
		.select()
		.from(objectStorages)
		.where(eq(objectStorages.id, id))
		.limit(1);

	if (!record) {
		return false;
	}

	const { bucketName, accessKeyId, endpoint } = record;

	// 1. Delete bucket and any contents via S3 API with admin client
	const adminClient = getAdminS3Client(endpoint);
	try {
		const listRes = await adminClient.send(
			new ListObjectsV2Command({ Bucket: bucketName }),
		);
		if (listRes.Contents && listRes.Contents.length > 0) {
			const objectsToDelete = listRes.Contents.map((obj) => ({ Key: obj.Key }));
			await adminClient.send(
				new DeleteObjectsCommand({
					Bucket: bucketName,
					Delete: { Objects: objectsToDelete },
				}),
			);
		}
		await adminClient.send(new DeleteBucketCommand({ Bucket: bucketName }));
	} catch (err: any) {
		// Ignore NoSuchBucket or 404
		if (
			err.name !== "NoSuchBucket" &&
			err.$metadata?.httpStatusCode !== 404 &&
			!err.message?.includes("not found")
		) {
			console.warn(`Warning deleting bucket "${bucketName}":`, err.message);
		}
	}

	// 2. Remove IAM identity from s3.json and reload
	const config = await readS3Config();
	config.identities = config.identities.filter((identity) => {
		const matchesAccessKey = identity.credentials?.some(
			(c) => c.accessKey === accessKeyId,
		);
		const matchesBucketAction = identity.actions?.some(
			(a) =>
				a === `Read:${bucketName}` ||
				a === `Write:${bucketName}` ||
				a === `List:${bucketName}` ||
				a === `Tagging:${bucketName}`,
		);
		return !matchesAccessKey && !matchesBucketAction;
	});

	await writeS3ConfigAndReload(config);

	// 3. Delete database record
	await db.delete(objectStorages).where(eq(objectStorages.id, id));

	return true;
}

export interface FormattedCredentials {
	env: string;
	awsCli: string;
	nodeSdk: string;
}

/**
 * Formats storage credentials into standard developer snippets:
 * - .env snippet
 * - AWS CLI configuration commands
 * - Node AWS SDK (@aws-sdk/client-s3) client initialization
 */


// Validation schemas for Server Functions
export async function createObjectStorageFn(opts: { data: { projectId: string; bucketName: string } }): Promise<ObjectStorage> {
	return createObjectStorage(opts.data);
}
export async function listObjectStoragesFn(opts: { data: string } | string): Promise<ObjectStorage[]> {
	const projectId = typeof opts === "string" ? opts : opts.data;
	return listObjectStorages(projectId);
}
export async function getStorageCredentialsFn(opts: { data: string } | string): Promise<StorageCredentials | null> {
	const storageId = typeof opts === "string" ? opts : opts.data;
	return getStorageCredentials(storageId);
}
export async function deleteObjectStorageFn(opts: { data: { id: string } } | string): Promise<boolean> {
	const storageId = typeof opts === "string" ? opts : opts.data.id;
	return deleteObjectStorage(storageId);
}
