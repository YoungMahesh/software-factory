import child_process from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import net from "node:net";
import path from "node:path";

export const CA_DOWNLOAD_PATH = "/api/ca.crt";

export function getPublicPostgresHost(): string {
	return (
		process.env.PUBLIC_POSTGRES_HOST || process.env.PUBLIC_HOST || "localhost"
	);
}

export interface CertificatePaths {
	certsDir: string;
	caKeyPath: string;
	caCertPath: string;
	serverKeyPath: string;
	serverCertPath: string;
	hostMetaPath: string;
}

export function getCertificatePaths(baseDataDir?: string): CertificatePaths {
	const rootDir = process.cwd();
	const dataDir = baseDataDir || process.env.DATA_DIR || path.resolve(rootDir, ".data");
	const certsDir = path.resolve(dataDir, "certs");

	const caKeyPath =
		process.env.POSTGRES_CA_KEY_PATH || path.resolve(certsDir, "ca.key");
	const caCertPath =
		process.env.POSTGRES_CA_CERT_PATH || path.resolve(certsDir, "ca.crt");
	const serverKeyPath =
		process.env.POSTGRES_SERVER_KEY_PATH ||
		path.resolve(certsDir, "server.key");
	const serverCertPath =
		process.env.POSTGRES_SERVER_CERT_PATH ||
		path.resolve(certsDir, "server.crt");
	const hostMetaPath = path.resolve(certsDir, ".cert-host");

	return {
		certsDir,
		caKeyPath,
		caCertPath,
		serverKeyPath,
		serverCertPath,
		hostMetaPath,
	};
}

export function ensureCaCertificate(baseDataDir?: string): string {
	const paths = getCertificatePaths(baseDataDir);
	const hasCustomCaCert = Boolean(process.env.POSTGRES_CA_CERT_PATH);

	if (fs.existsSync(paths.caCertPath)) {
		return fs.readFileSync(paths.caCertPath, "utf8");
	}

	if (!hasCustomCaCert) {
		if (!fs.existsSync(paths.certsDir)) {
			fs.mkdirSync(paths.certsDir, { recursive: true });
		}
		try {
			fs.chownSync(paths.certsDir, 70, 70);
		} catch {}
		fs.chmodSync(paths.certsDir, 0o755);

		if (!fs.existsSync(paths.caKeyPath) || !fs.existsSync(paths.caCertPath)) {
			child_process.execFileSync(
				"openssl",
				[
					"req",
					"-x509",
					"-newkey",
					"rsa:4096",
					"-sha256",
					"-days",
					"3650",
					"-nodes",
					"-keyout",
					paths.caKeyPath,
					"-out",
					paths.caCertPath,
					"-subj",
					"/CN=Neon Local Root CA",
				],
				{ stdio: "pipe" },
			);
			fs.chmodSync(paths.caKeyPath, 0o600);
			fs.chmodSync(paths.caCertPath, 0o644);
		}
	}

	if (!fs.existsSync(paths.caCertPath)) {
		throw new Error(`CA Certificate not found at ${paths.caCertPath}`);
	}
	return fs.readFileSync(paths.caCertPath, "utf8");
}

export function getCaCertificate(baseDataDir?: string): string {
	const { caCertPath } = getCertificatePaths(baseDataDir);
	if (fs.existsSync(caCertPath)) {
		return fs.readFileSync(caCertPath, "utf8");
	}
	return ensureCaCertificate(baseDataDir);
}

export interface EnsureTlsCertificatesOptions {
	baseDataDir?: string;
	publicHost?: string;
	force?: boolean;
}

export interface EnsureTlsCertificatesResult {
	caCertPath: string;
	caKeyPath: string;
	serverCertPath: string;
	serverKeyPath: string;
	regenerated: boolean;
	publicHost: string;
}

export async function ensureTlsCertificates(
	options?: EnsureTlsCertificatesOptions,
): Promise<EnsureTlsCertificatesResult> {
	const paths = getCertificatePaths(options?.baseDataDir);
	const publicHost = options?.publicHost || getPublicPostgresHost();

	// If custom paths are supplied via environment variables, do not auto-generate
	const hasCustomServerCerts = Boolean(
		process.env.POSTGRES_SERVER_CERT_PATH &&
			process.env.POSTGRES_SERVER_KEY_PATH,
	);

	if (!fs.existsSync(paths.certsDir)) {
		fs.mkdirSync(paths.certsDir, { recursive: true });
	}
	try {
		fs.chownSync(paths.certsDir, 70, 70);
	} catch {}
	fs.chmodSync(paths.certsDir, 0o755);

	// 1. Root CA generation
	ensureCaCertificate(options?.baseDataDir);

	// 2. Server Certificate check & generation
	if (hasCustomServerCerts) {
		if (fs.existsSync(paths.serverKeyPath)) {
			fs.chmodSync(paths.serverKeyPath, 0o600);
			try {
				fs.chownSync(paths.serverKeyPath, 70, 70);
			} catch {}
		}
		return {
			caCertPath: paths.caCertPath,
			caKeyPath: paths.caKeyPath,
			serverCertPath: paths.serverCertPath,
			serverKeyPath: paths.serverKeyPath,
			regenerated: false,
			publicHost,
		};
	}

	let needsRegeneration = Boolean(options?.force);

	if (
		!fs.existsSync(paths.serverKeyPath) ||
		!fs.existsSync(paths.serverCertPath)
	) {
		needsRegeneration = true;
	} else if (!needsRegeneration) {
		const recordedHost = fs.existsSync(paths.hostMetaPath)
			? fs.readFileSync(paths.hostMetaPath, "utf8").trim()
			: "";

		if (recordedHost !== publicHost) {
			needsRegeneration = true;
		} else {
			try {
				const certPem = fs.readFileSync(paths.serverCertPath, "utf8");
				const x509 = new crypto.X509Certificate(certPem);
				const sans = x509.subjectAltName || "";

				const isIp = net.isIP(publicHost) !== 0;
				const hostPattern = isIp
					? `IP Address:${publicHost}`
					: `DNS:${publicHost}`;

				const hasIpv6Loopback =
					sans.includes("IP Address:::1") ||
					sans.includes("IP Address:0:0:0:0:0:0:0:1") ||
					sans.includes("::1");

				if (
					!sans.includes("DNS:localhost") ||
					!sans.includes("IP Address:127.0.0.1") ||
					!hasIpv6Loopback ||
					!sans.includes(hostPattern)
				) {
					needsRegeneration = true;
				}
			} catch {
				needsRegeneration = true;
			}
		}
	}

	if (!needsRegeneration) {
		fs.chmodSync(paths.serverKeyPath, 0o600);
		try {
			fs.chownSync(paths.serverKeyPath, 70, 70);
		} catch {}
		return {
			caCertPath: paths.caCertPath,
			caKeyPath: paths.caKeyPath,
			serverCertPath: paths.serverCertPath,
			serverKeyPath: paths.serverKeyPath,
			regenerated: false,
			publicHost,
		};
	}

	// Generate Server Certificate signed by Root CA
	const tempCsr = path.resolve(
		paths.certsDir,
		`server-${Date.now()}-${Math.random().toString(36).slice(2, 8)}.csr`,
	);
	const tempExt = path.resolve(
		paths.certsDir,
		`server-${Date.now()}-${Math.random().toString(36).slice(2, 8)}.ext`,
	);

	try {
		child_process.execFileSync(
			"openssl",
			[
				"req",
				"-newkey",
				"rsa:2048",
				"-nodes",
				"-keyout",
				paths.serverKeyPath,
				"-out",
				tempCsr,
				"-subj",
				`/CN=${publicHost}`,
			],
			{ stdio: "pipe" },
		);

		const sanList: string[] = [];
		if (net.isIP(publicHost) !== 0) {
			sanList.push(`IP:${publicHost}`);
		} else {
			sanList.push(`DNS:${publicHost}`);
		}
		if (!sanList.includes("DNS:localhost")) {
			sanList.push("DNS:localhost");
		}
		if (!sanList.includes("IP:127.0.0.1")) {
			sanList.push("IP:127.0.0.1");
		}
		if (!sanList.includes("IP:::1")) {
			sanList.push("IP:::1");
		}
		if (!sanList.includes("DNS:postgres")) {
			sanList.push("DNS:postgres");
		}
		if (!sanList.includes("DNS:neon-postgres")) {
			sanList.push("DNS:neon-postgres");
		}

		fs.writeFileSync(
			tempExt,
			`subjectAltName = ${sanList.join(", ")}\n`,
			"utf8",
		);

		child_process.execFileSync(
			"openssl",
			[
				"x509",
				"-req",
				"-in",
				tempCsr,
				"-CA",
				paths.caCertPath,
				"-CAkey",
				paths.caKeyPath,
				"-CAcreateserial",
				"-out",
				paths.serverCertPath,
				"-days",
				"365",
				"-sha256",
				"-extfile",
				tempExt,
			],
			{ stdio: "pipe" },
		);

		fs.chmodSync(paths.serverKeyPath, 0o600);
		fs.chmodSync(paths.serverCertPath, 0o644);
		try {
			fs.chownSync(paths.serverKeyPath, 70, 70);
		} catch {}

		fs.writeFileSync(paths.hostMetaPath, publicHost, "utf8");

		return {
			caCertPath: paths.caCertPath,
			caKeyPath: paths.caKeyPath,
			serverCertPath: paths.serverCertPath,
			serverKeyPath: paths.serverKeyPath,
			regenerated: true,
			publicHost,
		};
	} finally {
		if (fs.existsSync(tempCsr)) fs.unlinkSync(tempCsr);
		if (fs.existsSync(tempExt)) fs.unlinkSync(tempExt);
		// Clean up any ca.srl file if created in certsDir
		const srlPath = path.resolve(paths.certsDir, "ca.srl");
		if (fs.existsSync(srlPath)) {
			try {
				fs.unlinkSync(srlPath);
			} catch {}
		}
	}
}
