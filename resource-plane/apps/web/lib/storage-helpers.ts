export interface ObjectStorage {
	id: string;
	projectId: string;
	bucketName: string;
	accessKeyId: string;
	secretAccessKey: string;
	endpoint: string;
	region: string;
	createdAt: Date;
}

export interface StorageCredentials {
	id: string;
	projectId: string;
	bucketName: string;
	accessKeyId: string;
	secretAccessKey: string;
	endpoint: string;
	region: string;
}

export interface FormattedCredentials {
	env: string;
	awsCli: string;
	nodeSdk: string;
}

export function validateBucketName(name: string): {
	valid: boolean;
	error?: string;
} {
	const trimmed = name?.trim() || "";
	if (!trimmed) {
		return { valid: false, error: "Bucket name cannot be empty" };
	}
	if (trimmed.length < 3 || trimmed.length > 63) {
		return {
			valid: false,
			error: "Bucket name must be between 3 and 63 characters",
		};
	}
	if (!/^[a-z0-9][a-z0-9-]*[a-z0-9]$/.test(trimmed)) {
		return {
			valid: false,
			error:
				"Bucket name must start and end with a lowercase letter or number and contain only lowercase letters, numbers, and hyphens",
		};
	}
	return { valid: true };
}

export function formatStorageCredentials(
	creds: StorageCredentials,
): FormattedCredentials {
	const env = [
		`AWS_ACCESS_KEY_ID=${creds.accessKeyId}`,
		`AWS_SECRET_ACCESS_KEY=${creds.secretAccessKey}`,
		`AWS_ENDPOINT_URL_S3=${creds.endpoint}`,
		`AWS_REGION=${creds.region}`,
		`S3_BUCKET_NAME=${creds.bucketName}`,
	].join("\n");

	const awsCli = [
		`aws configure set aws_access_key_id ${creds.accessKeyId}`,
		`aws configure set aws_secret_access_key ${creds.secretAccessKey}`,
		`aws configure set default.region ${creds.region}`,
		`# List bucket contents:`,
		`aws s3 ls s3://${creds.bucketName} --endpoint-url ${creds.endpoint}`,
	].join("\n");

	const nodeSdk = `import { S3Client, ListObjectsV2Command, PutObjectCommand } from "@aws-sdk/client-s3";

export const s3 = new S3Client({
  endpoint: "${creds.endpoint}",
  region: "${creds.region}",
  credentials: {
    accessKeyId: "${creds.accessKeyId}",
    secretAccessKey: "${creds.secretAccessKey}",
  },
  forcePathStyle: true,
});`;

	return { env, awsCli, nodeSdk };
}
