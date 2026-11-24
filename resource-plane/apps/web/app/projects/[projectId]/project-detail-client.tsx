"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import React, {
	useState,
	useTransition,
	useId,
	useEffect,
	Suspense,
} from "react";
import {
	Database,
	HardDrive,
	Terminal,
	Settings,
	Globe,
	Calendar,
	Home,
	Plus,
	ArrowLeft,
	Key,
	RotateCw,
	Trash2,
	Copy,
	Check,
	Eye,
	EyeOff,
	AlertTriangle,
	X,
	ShieldCheck,
	ShieldAlert,
	Loader2,
	CheckCircle2,
	FolderTree,
	Download,
} from "lucide-react";

import type { DatabaseCredentials } from "@/lib/database-helpers";
import {
	formatStorageCredentials,
	validateBucketName,
	type ObjectStorage,
	type StorageCredentials,
} from "@/lib/storage-helpers";
import {
	createDatabaseFn,
	listDatabasesFn,
	resetDatabasePasswordFn,
	deleteDatabaseFn,
	createObjectStorageFn,
	listObjectStoragesFn,
	getStorageCredentialsFn,
	deleteObjectStorageFn,
} from "@/app/actions";
import { HydratedButton } from "@/components/HydratedButton";

const LazySqlScratchpadPanel = React.lazy(
	() => import("@/components/SqlScratchpadPanel"),
);
const LazyObjectBrowserPanel = React.lazy(
	() => import("@/components/ObjectBrowserPanel"),
);

function TabPanelSkeleton({ title }: { title: string }) {
	return (
		<div className="island-shell rounded-2xl p-6 sm:p-8 animate-pulse">
			<div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-6 border-b border-[var(--line)] gap-4">
				<div>
					<div className="h-6 w-48 bg-[var(--line)] rounded-lg mb-2" />
					<div className="h-4 w-96 max-w-full bg-[var(--line)]/60 rounded-md" />
				</div>
				<div className="h-9 w-32 bg-[var(--line)]/50 rounded-xl" />
			</div>
			<div className="py-16 text-center">
				<div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-[rgba(0,229,153,0.08)] border border-[rgba(0,229,153,0.2)] text-[#009b67] dark:text-[#00e599]">
					<Loader2 className="h-6 w-6 animate-spin text-[#00e599]" />
				</div>
				<p className="text-sm font-medium text-[var(--sea-ink-soft)]">
					{title}
				</p>
			</div>
		</div>
	);
}

export interface CaCertificateSectionProps {
	onCopyPem?: () => void;
	copied?: boolean;
	isHydrated?: boolean;
}

export function CaCertificateSection({
	onCopyPem,
	copied,
	isHydrated,
}: CaCertificateSectionProps) {
	return (
		<div
			data-testid="ca-certificate-section"
			className="rounded-xl border border-[var(--line)] bg-[var(--foam)] p-3.5"
		>
			<div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
				<div className="flex items-center gap-2.5">
					<div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[rgba(0,229,153,0.12)] text-[#009b67] dark:text-[#00e599]">
						<ShieldCheck className="h-4 w-4" />
					</div>
					<div>
						<h4 className="text-xs font-bold uppercase tracking-wider text-[var(--sea-ink)] m-0">
							Root CA Certificate
						</h4>
						<p className="text-xs text-[var(--sea-ink-soft)] m-0 mt-0.5">
							Required for TLS certificate and hostname verification (
							<code className="font-mono text-[11px]">sslmode=verify-full</code>
							).
						</p>
					</div>
				</div>

				<div className="flex items-center gap-2 shrink-0">
					<a
						href="/api/ca.crt"
						download="ca.crt"
						className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-1.5 text-xs font-semibold text-[var(--sea-ink)] hover:bg-[var(--chip-bg)] hover:text-[#00e599] transition no-underline shadow-xs cursor-pointer"
					>
						<Download className="h-3.5 w-3.5 text-[#00e599]" />
						<span>Download ca.crt</span>
					</a>
					<HydratedButton
						type="button"
						onClick={onCopyPem}
						isHydrated={isHydrated}
						className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-1.5 text-xs font-semibold text-[var(--sea-ink)] hover:bg-[var(--chip-bg)] transition shadow-xs"
					>
						{copied ? (
							<>
								<Check className="h-3.5 w-3.5 text-[#00e599]" />
								<span>Copied!</span>
							</>
						) : (
							<>
								<Copy className="h-3.5 w-3.5" />
								<span>Copy PEM</span>
							</>
						)}
					</HydratedButton>
				</div>
			</div>
		</div>
	);
}

function ProjectNotFound() {
	return (
		<main className="page-wrap px-4 py-16 text-center">
			<div className="island-shell mx-auto max-w-lg rounded-2xl p-8">
				<h2 className="mb-2 text-2xl font-bold text-[var(--sea-ink)]">
					Project Not Found
				</h2>
				<p className="mb-6 text-[var(--sea-ink-soft)]">
					The project you are looking for does not exist or may have been
					deleted.
				</p>
				<Link
					href="/"
					className="inline-flex items-center gap-2 rounded-full bg-[#00e599] px-5 py-2.5 text-sm font-semibold text-[#0a1418] no-underline shadow-[0_0_12px_rgba(0,229,153,0.3)] transition hover:bg-[#00c985]"
				>
					<ArrowLeft className="h-4 w-4" />
					Back to Projects
				</Link>
			</div>
		</main>
	);
}

type TabKey = "databases" | "storage" | "scratchpad" | "browser" | "settings";
type DbCredentialTab = "uri" | "env" | "psql" | "drizzle" | "prisma";
type StorageCredentialTab = "env" | "cli" | "sdk";

export interface ProjectDetailClientProps {
	project: any;
	initialDatabases: DatabaseCredentials[];
	initialStorages: ObjectStorage[];
}

export default function ProjectDetailPage({
	project,
	initialDatabases,
	initialStorages,
}: ProjectDetailClientProps) {
	const [databases, setDatabases] = useState<DatabaseCredentials[]>(initialDatabases);
	const [storages, setStorages] = useState<ObjectStorage[]>(initialStorages);
	useEffect(() => { setDatabases(initialDatabases); }, [initialDatabases]);
	useEffect(() => { setStorages(initialStorages); }, [initialStorages]);
	const router = useRouter();
	const [activeTab, setActiveTab] = useState<TabKey>("databases");
	const [, startTransition] = useTransition();

	// ----------------------------------------------------
	// Databases State (Ticket 03)
	// ----------------------------------------------------
	const [isCreateDbOpen, setIsCreateDbOpen] = useState(false);
	const [newDbName, setNewDbName] = useState("");
	const [isCreatingDb, setIsCreatingDb] = useState(false);
	const [createDbError, setCreateDbError] = useState<string | null>(null);

	const [credsModalDb, setCredsModalDb] = useState<DatabaseCredentials | null>(
		null,
	);
	const [dbCredTab, setDbCredTab] = useState<DbCredentialTab>("uri");
	const [copiedKey, setCopiedKey] = useState<string | null>(null);

	const [resetModalDb, setResetModalDb] = useState<DatabaseCredentials | null>(
		null,
	);
	const [isResettingDb, setIsResettingDb] = useState(false);
	const [resetSuccessCreds, setResetSuccessCreds] =
		useState<DatabaseCredentials | null>(null);

	const [deleteModalDb, setDeleteModalDb] =
		useState<DatabaseCredentials | null>(null);
	const [deleteDbConfirmText, setDeleteDbConfirmText] = useState("");
	const [isDeletingDb, setIsDeletingDb] = useState(false);
	const [deleteDbError, setDeleteDbError] = useState<string | null>(null);

	// ----------------------------------------------------
	// Object Storage State (Ticket 04)
	// ----------------------------------------------------
	const [isCreateStorageOpen, setIsCreateStorageOpen] = useState(false);
	const [bucketName, setBucketName] = useState("");
	const [createStorageError, setCreateStorageError] = useState<string | null>(
		null,
	);
	const [isCreatingStorage, setIsCreatingStorage] = useState(false);
	const bucketInputId = useId();

	const [selectedStorage, setSelectedStorage] = useState<ObjectStorage | null>(
		null,
	);
	const [storageCredentials, setStorageCredentials] =
		useState<StorageCredentials | null>(null);
	const [isLoadingStorageCreds, setIsLoadingStorageCreds] = useState(false);
	const [storageCredTab, setStorageCredTab] =
		useState<StorageCredentialTab>("env");
	const [isSecretVisible, setIsSecretVisible] = useState(false);

	const [storageToDelete, setStorageToDelete] = useState<ObjectStorage | null>(
		null,
	);
	const [typedConfirmName, setTypedConfirmName] = useState("");
	const [deleteStorageError, setDeleteStorageError] = useState<string | null>(
		null,
	);
	const [isDeletingStorage, setIsDeletingStorage] = useState(false);
	const deleteConfirmInputId = useId();

	// ----------------------------------------------------
	// Selected Storage for Object Browser Tab
	// ----------------------------------------------------
	const [browserStorageId, setBrowserStorageId] = useState<string>(
		storages[0]?.id || "",
	);

	useEffect(() => {
		if (!browserStorageId && storages.length > 0) {
			setBrowserStorageId(storages[0].id);
		}
	}, [storages, browserStorageId]);

	// ----------------------------------------------------
	// Clipboard Helper
	// ----------------------------------------------------
	const copyToClipboard = async (text: string, key: string) => {
		try {
			await navigator.clipboard.writeText(text);
			setCopiedKey(key);
			setTimeout(() => setCopiedKey(null), 2000);
		} catch (err) {
			console.error("Failed to copy to clipboard", err);
		}
	};

	const handleCopyCaPem = async () => {
		try {
			const res = await fetch("/api/ca.crt");
			if (!res.ok) throw new Error("Failed to fetch certificate");
			const pem = await res.text();
			await navigator.clipboard.writeText(pem);
			setCopiedKey("ca-pem");
			setTimeout(() => setCopiedKey(null), 2000);
		} catch (err) {
			console.error("Failed to copy CA certificate", err);
		}
	};

	// ----------------------------------------------------
	// Database Handlers (Ticket 03)
	// ----------------------------------------------------
	const handleCreateDatabase = async (e: React.FormEvent) => {
		e.preventDefault();
		if (!newDbName.trim()) {
			setCreateDbError("Database name is required");
			return;
		}

		setIsCreatingDb(true);
		setCreateDbError(null);

		try {
			const created = await createDatabaseFn({
				data: { projectId: project.id, name: newDbName.trim() },
			});
			setIsCreateDbOpen(false);
			setNewDbName("");
			startTransition(async () => {
				router.refresh();
			});
			setCredsModalDb(created);
			setDbCredTab("uri");
		} catch (err: any) {
			setCreateDbError(err.message || "Failed to create database");
		} finally {
			setIsCreatingDb(false);
		}
	};

	const handleResetPassword = async () => {
		if (!resetModalDb) return;
		setIsResettingDb(true);
		try {
			const updated = await resetDatabasePasswordFn({
				data: { databaseId: resetModalDb.id },
			});
			setResetSuccessCreds(updated);
			startTransition(async () => {
				router.refresh();
			});
		} catch (err: any) {
			alert(err.message || "Failed to reset password");
		} finally {
			setIsResettingDb(false);
		}
	};

	const handleDeleteDatabase = async () => {
		if (!deleteModalDb) return;
		if (deleteDbConfirmText !== deleteModalDb.name) return;

		setIsDeletingDb(true);
		setDeleteDbError(null);

		try {
			await deleteDatabaseFn({
				data: { databaseId: deleteModalDb.id },
			});
			setDeleteModalDb(null);
			setDeleteDbConfirmText("");
			startTransition(async () => {
				router.refresh();
			});
		} catch (err: any) {
			setDeleteDbError(err.message || "Failed to delete database");
		} finally {
			setIsDeletingDb(false);
		}
	};

	// ----------------------------------------------------
	// Storage Handlers (Ticket 04)
	// ----------------------------------------------------
	const openCreateStorageModal = () => {
		setBucketName("");
		setCreateStorageError(null);
		setIsCreateStorageOpen(true);
	};

	const closeCreateStorageModal = () => {
		setIsCreateStorageOpen(false);
		setCreateStorageError(null);
		setBucketName("");
	};

	const handleCreateStorage = async (e: React.FormEvent) => {
		e.preventDefault();
		const validation = validateBucketName(bucketName);
		if (!validation.valid) {
			setCreateStorageError(validation.error || "Invalid bucket name");
			return;
		}

		setCreateStorageError(null);
		setIsCreatingStorage(true);
		try {
			await createObjectStorageFn({
				data: {
					projectId: project.id,
					bucketName: bucketName.trim().toLowerCase(),
				},
			});

			closeCreateStorageModal();
			startTransition(async () => {
				router.refresh();
			});
		} catch (err: any) {
			setCreateStorageError(err.message || "Failed to create storage bucket");
		} finally {
			setIsCreatingStorage(false);
		}
	};

	const openStorageCredentialsModal = async (storage: ObjectStorage) => {
		setSelectedStorage(storage);
		setIsSecretVisible(false);
		setStorageCredTab("env");
		setCopiedKey(null);
		setIsLoadingStorageCreds(true);

		try {
			const creds = await getStorageCredentialsFn({ data: storage.id });
			setStorageCredentials(creds);
		} catch (err) {
			console.error("Failed to load credentials:", err);
			setStorageCredentials({
				id: storage.id,
				projectId: storage.projectId,
				bucketName: storage.bucketName,
				accessKeyId: storage.accessKeyId,
				secretAccessKey: storage.secretAccessKey,
				endpoint: storage.endpoint,
				region: storage.region,
			});
		} finally {
			setIsLoadingStorageCreds(false);
		}
	};

	const closeStorageCredentialsModal = () => {
		setSelectedStorage(null);
		setStorageCredentials(null);
		setCopiedKey(null);
	};

	const openDeleteStorageModal = (storage: ObjectStorage) => {
		setStorageToDelete(storage);
		setTypedConfirmName("");
		setDeleteStorageError(null);
	};

	const closeDeleteStorageModal = () => {
		setStorageToDelete(null);
		setTypedConfirmName("");
		setDeleteStorageError(null);
	};

	const handleDeleteStorage = async (e: React.FormEvent) => {
		e.preventDefault();
		if (!storageToDelete) return;

		if (typedConfirmName !== storageToDelete.bucketName) {
			setDeleteStorageError(
				`Bucket name does not match "${storageToDelete.bucketName}"`,
			);
			return;
		}

		setDeleteStorageError(null);
		setIsDeletingStorage(true);

		try {
			await deleteObjectStorageFn({
				data: { id: storageToDelete.id },
			});

			closeDeleteStorageModal();
			startTransition(async () => {
				router.refresh();
			});
		} catch (err: any) {
			setDeleteStorageError(err.message || "Failed to delete storage bucket");
		} finally {
			setIsDeletingStorage(false);
		}
	};

	const tabs: Array<{
		id: TabKey;
		label: string;
		icon: any;
		count?: number;
	}> = [
		{
			id: "databases",
			label: "Databases",
			icon: Database,
			count: databases.length,
		},
		{
			id: "storage",
			label: "Object Storage",
			icon: HardDrive,
			count: storages.length,
		},
		{
			id: "scratchpad",
			label: "SQL Scratchpad",
			icon: Terminal,
		},
		{
			id: "browser",
			label: "Object Browser",
			icon: FolderTree,
		},
		{
			id: "settings",
			label: "Settings",
			icon: Settings,
		},
	];

	const createdDate = new Date(project.createdAt).toLocaleDateString(
		undefined,
		{
			year: "numeric",
			month: "short",
			day: "numeric",
		},
	);

	const formattedStorageCreds = storageCredentials
		? formatStorageCredentials(storageCredentials)
		: null;

	return (
		<main className="page-wrap px-4 pb-16 pt-8">
			{/* Breadcrumbs */}
			<nav
				aria-label="Breadcrumbs"
				className="mb-6 flex items-center gap-2 text-sm text-[var(--sea-ink-soft)]"
			>
				<Link
					href="/"
					className="inline-flex items-center gap-1.5 font-medium transition hover:text-[var(--sea-ink)] no-underline"
				>
					<Home className="h-4 w-4" />
					Projects
				</Link>
				<span className="text-[var(--line)]">/</span>
				<span className="font-semibold text-[var(--sea-ink)] truncate max-w-xs">
					{project.name}
				</span>
			</nav>

			{/* Project Header */}
			<div className="island-shell mb-8 rounded-2xl p-6 sm:p-8">
				<div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
					<div>
						<div className="flex flex-wrap items-center gap-2.5 mb-2">
							<h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-[var(--sea-ink)] m-0">
								{project.name}
							</h1>
							<span className="font-mono text-xs px-2.5 py-1 rounded-full border border-[var(--chip-line)] bg-[var(--chip-bg)] text-[var(--sea-ink-soft)]">
								{project.slug}
							</span>
							<span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full bg-[rgba(0,229,153,0.12)] text-[#009b67] dark:text-[#00e599] border border-[rgba(0,229,153,0.3)] font-semibold">
								<Globe className="h-3 w-3" />
								{project.region}
							</span>
						</div>
						<div className="flex flex-wrap items-center gap-4 text-xs text-[var(--sea-ink-soft)]">
							<span className="inline-flex items-center gap-1.5">
								<Calendar className="h-3.5 w-3.5" />
								Created {createdDate}
							</span>
							<span>•</span>
							<span>
								ID: <code className="text-[11px] font-mono">{project.id}</code>
							</span>
						</div>
					</div>

					<div className="flex items-center gap-3">
						<div className="flex items-center gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3.5 py-2 text-xs font-medium text-[var(--sea-ink)] shadow-xs">
							<Database className="h-4 w-4 text-[var(--lagoon-deep)]" />
							<span>{databases.length} Databases</span>
						</div>
						<div className="flex items-center gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3.5 py-2 text-xs font-medium text-[var(--sea-ink)] shadow-xs">
							<HardDrive className="h-4 w-4 text-[var(--palm)]" />
							<span>{storages.length} Storages</span>
						</div>
					</div>
				</div>
			</div>

			{/* Tab Navigation */}
			<div className="mb-6 flex border-b border-[var(--line)] gap-1 overflow-x-auto">
				{tabs.map((tab) => {
					const Icon = tab.icon;
					const isActive = activeTab === tab.id;
					return (
						<HydratedButton
							key={tab.id}
							type="button"
							onClick={() => setActiveTab(tab.id)}
							className={`flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-semibold transition-all whitespace-nowrap ${
								isActive
									? "border-[#00e599] text-[var(--sea-ink)] bg-[rgba(0,229,153,0.06)] rounded-t-lg"
									: "border-transparent text-[var(--sea-ink-soft)] hover:text-[var(--sea-ink)] hover:border-[var(--line)]"
							}`}
						>
							<Icon className={`h-4 w-4 ${isActive ? "text-[#00e599]" : ""}`} />
							<span>{tab.label}</span>
							{typeof tab.count === "number" && (
								<span
									className={`ml-1 rounded-full px-2 py-0.5 text-xs font-mono font-bold ${
										isActive
											? "bg-[#00e599] text-[#0a1418]"
											: "bg-[var(--chip-bg)] border border-[var(--chip-line)] text-[var(--sea-ink-soft)]"
									}`}
								>
									{tab.count}
								</span>
							)}
						</HydratedButton>
					);
				})}
			</div>

			{/* Tab Panels */}
			<div>
				{/* ======================================================== */}
				{/* Databases Tab Panel (Ticket 03)                          */}
				{/* ======================================================== */}
				{activeTab === "databases" && (
					<div className="space-y-6">
						<div className="island-shell rounded-2xl p-6 sm:p-8">
							<div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-6 border-b border-[var(--line)] gap-4">
								<div>
									<h3 className="text-lg font-bold text-[var(--sea-ink)] m-0">
										PostgreSQL Databases
									</h3>
									<p className="text-sm text-[var(--sea-ink-soft)] m-0 mt-1">
										Isolated PostgreSQL logical databases with dedicated
										resource roles and connection strings.
									</p>
								</div>
								<HydratedButton
									type="button"
									onClick={() => {
										setNewDbName("");
										setCreateDbError(null);
										setIsCreateDbOpen(true);
									}}
									className="inline-flex items-center gap-2 rounded-xl bg-[#00e599] px-4 py-2.5 text-sm font-bold text-[#0a1418] shadow-[0_0_12px_rgba(0,229,153,0.3)] hover:bg-[#00c985] transition self-start sm:self-auto"
								>
									<Plus className="h-4 w-4" />
									New Database
								</HydratedButton>
							</div>

							{databases.length === 0 ? (
								<div className="py-14 text-center">
									<div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-[rgba(0,229,153,0.12)] border border-[rgba(0,229,153,0.25)] text-[#009b67] dark:text-[#00e599]">
										<Database className="h-8 w-8" />
									</div>
									<h4 className="text-base font-bold text-[var(--sea-ink)] m-0">
										No databases provisioned yet
									</h4>
									<p className="mx-auto mt-2 max-w-md text-sm text-[var(--sea-ink-soft)]">
										Provision an isolated PostgreSQL database with dedicated
										credentials and strict role isolation for this project.
									</p>
									<HydratedButton
										type="button"
										onClick={() => {
											setNewDbName("");
											setCreateDbError(null);
											setIsCreateDbOpen(true);
										}}
										className="mt-5 inline-flex items-center gap-2 rounded-xl bg-[#00e599] px-4 py-2 text-sm font-bold text-[#0a1418] shadow-[0_0_12px_rgba(0,229,153,0.3)] hover:bg-[#00c985] transition"
									>
										<Plus className="h-4 w-4" />
										Provision Database
									</HydratedButton>
								</div>
							) : (
								<div className="pt-6 grid grid-cols-1 gap-4">
									{databases.map((dbItem) => (
										<div
											key={dbItem.id}
											className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-5 transition hover:border-[#00e599]/40 shadow-xs"
										>
											<div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
												<div>
													<div className="flex flex-wrap items-center gap-2.5">
														<span className="font-mono text-base font-bold text-[var(--sea-ink)]">
															{dbItem.name}
														</span>
														<span className="inline-flex items-center gap-1.5 text-xs px-2.5 py-0.5 rounded-full bg-[rgba(0,229,153,0.12)] text-[#009b67] dark:text-[#00e599] border border-[rgba(0,229,153,0.3)] font-semibold">
															<span className="h-1.5 w-1.5 rounded-full bg-[#00e599] animate-pulse" />
															Active
														</span>
														<span className="text-xs px-2.5 py-0.5 rounded-full bg-[var(--chip-bg)] border border-[var(--chip-line)] text-[var(--sea-ink-soft)] font-mono">
															{dbItem.host}:{dbItem.port}
														</span>
													</div>

													<div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-[var(--sea-ink-soft)]">
														<span>
															Role:{" "}
															<code className="font-mono font-medium text-[var(--sea-ink)]">
																{dbItem.username}
															</code>
														</span>
														<span>•</span>
														<span>
															Created{" "}
															{new Date(dbItem.createdAt).toLocaleDateString()}
														</span>
													</div>
												</div>

												<div className="flex flex-wrap items-center gap-2 self-start sm:self-auto">
													<HydratedButton
														type="button"
														onClick={() => {
															setCredsModalDb(dbItem);
															setDbCredTab("uri");
														}}
														className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 py-1.5 text-xs font-semibold text-[var(--sea-ink)] hover:bg-[var(--chip-bg)] hover:border-[#00e599]/50 transition"
													>
														<Key className="h-3.5 w-3.5 text-[#00e599]" />
														Connection Details
													</HydratedButton>
													<HydratedButton
														type="button"
														onClick={() => {
															setResetModalDb(dbItem);
															setResetSuccessCreds(null);
														}}
														className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 py-1.5 text-xs font-semibold text-[var(--sea-ink)] hover:bg-[var(--chip-bg)] transition"
													>
														<RotateCw className="h-3.5 w-3.5 text-[var(--lagoon-deep)]" />
														Reset Password
													</HydratedButton>
													<HydratedButton
														type="button"
														onClick={() => {
															setDeleteModalDb(dbItem);
															setDeleteDbConfirmText("");
															setDeleteDbError(null);
														}}
														className="inline-flex items-center gap-1.5 rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-1.5 text-xs font-semibold text-red-500 hover:bg-red-500/10 hover:border-red-500/40 transition"
													>
														<Trash2 className="h-3.5 w-3.5" />
														Delete
													</HydratedButton>
												</div>
											</div>

											{/* Quick connection string preview bar */}
											<div className="mt-4 flex items-center justify-between rounded-lg border border-[var(--line)] bg-[var(--foam)] px-3.5 py-2 font-mono text-xs text-[var(--sea-ink-soft)]">
												<span className="truncate mr-2">
													postgresql://{dbItem.username}:••••••••@{dbItem.host}:
													{dbItem.port}/{dbItem.name}
													?sslmode=verify-full&sslrootcert=ca.crt
												</span>
												<HydratedButton
													type="button"
													title="Copy full connection URI"
													onClick={() =>
														copyToClipboard(
															dbItem.connectionString,
															`card-${dbItem.id}`,
														)
													}
													className="flex shrink-0 items-center gap-1 font-sans text-xs font-semibold text-[#009b67] dark:text-[#00e599] hover:underline"
												>
													{copiedKey === `card-${dbItem.id}` ? (
														<>
															<Check className="h-3.5 w-3.5" />
															<span>Copied!</span>
														</>
													) : (
														<>
															<Copy className="h-3.5 w-3.5" />
															<span>Copy URI</span>
														</>
													)}
												</HydratedButton>
											</div>
										</div>
									))}
								</div>
							)}
						</div>
					</div>
				)}

				{/* ======================================================== */}
				{/* Storage Tab Panel (Ticket 04)                            */}
				{/* ======================================================== */}
				{activeTab === "storage" && (
					<div className="island-shell rounded-2xl p-6 sm:p-8">
						<div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-6 border-b border-[var(--line)] gap-4">
							<div>
								<h3 className="text-lg font-bold text-[var(--sea-ink)] m-0">
									S3 Object Storage
								</h3>
								<p className="text-sm text-[var(--sea-ink-soft)] m-0 mt-1">
									S3-compatible buckets backed by SeaweedFS with scoped IAM
									policies.
								</p>
							</div>
							<HydratedButton
								type="button"
								onClick={openCreateStorageModal}
								className="inline-flex items-center gap-2 rounded-xl bg-[#00e599] px-4 py-2 text-sm font-bold text-[#0a1418] shadow-[0_0_12px_rgba(0,229,153,0.3)] hover:bg-[#00c985] transition self-start sm:self-auto"
							>
								<Plus className="h-4 w-4" />
								New Storage Bucket
							</HydratedButton>
						</div>

						{storages.length === 0 ? (
							<div className="py-12 text-center">
								<div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-[rgba(0,229,153,0.12)] border border-[rgba(0,229,153,0.25)] text-[#009b67] dark:text-[#00e599]">
									<HardDrive className="h-7 w-7" />
								</div>
								<h4 className="text-base font-bold text-[var(--sea-ink)] m-0">
									No storage buckets provisioned yet
								</h4>
								<p className="mx-auto mt-1 max-w-sm text-sm text-[var(--sea-ink-soft)]">
									Provision an S3-compatible bucket with dedicated IAM
									credentials for file and media storage.
								</p>
								<HydratedButton
									type="button"
									onClick={openCreateStorageModal}
									className="mt-5 inline-flex items-center gap-2 rounded-xl bg-[#00e599] px-4 py-2 text-sm font-bold text-[#0a1418] shadow-[0_0_12px_rgba(0,229,153,0.3)] hover:bg-[#00c985] transition"
								>
									<Plus className="h-4 w-4" />
									Provision S3 Storage
								</HydratedButton>
							</div>
						) : (
							<div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-6">
								{storages.map((storage) => (
									<div
										key={storage.id}
										className="rounded-2xl border border-[var(--line)] bg-[var(--surface-strong)] p-5 transition hover:border-[#00e599]/50 shadow-xs flex flex-col justify-between"
									>
										<div>
											<div className="flex items-start justify-between gap-2 mb-3">
												<div className="flex items-center gap-2.5">
													<div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[rgba(0,229,153,0.12)] text-[#009b67] dark:text-[#00e599]">
														<HardDrive className="h-5 w-5" />
													</div>
													<div>
														<h4 className="text-base font-bold text-[var(--sea-ink)] m-0 font-mono">
															{storage.bucketName}
														</h4>
														<span className="text-xs text-[var(--sea-ink-soft)]">
															Region: {storage.region}
														</span>
													</div>
												</div>
												<span className="inline-flex items-center gap-1.5 rounded-full border border-[rgba(0,229,153,0.3)] bg-[rgba(0,229,153,0.1)] px-2.5 py-0.5 text-[11px] font-semibold text-[#009b67] dark:text-[#00e599]">
													<span className="h-1.5 w-1.5 rounded-full bg-[#00e599] animate-pulse" />
													Ready
												</span>
											</div>

											<div className="space-y-1.5 my-4 text-xs font-mono bg-[var(--sand)]/40 p-3 rounded-xl border border-[var(--line)]">
												<div className="flex justify-between items-center text-[var(--sea-ink-soft)]">
													<span>Endpoint:</span>
													<span className="text-[var(--sea-ink)] truncate max-w-[200px]">
														{storage.endpoint}
													</span>
												</div>
												<div className="flex justify-between items-center text-[var(--sea-ink-soft)]">
													<span>Access Key:</span>
													<span className="text-[var(--sea-ink)]">
														{storage.accessKeyId}
													</span>
												</div>
											</div>
										</div>

										<div className="flex items-center justify-between pt-3 border-t border-[var(--line)] gap-2">
											<div className="flex items-center gap-2">
												<HydratedButton
													type="button"
													onClick={() => openStorageCredentialsModal(storage)}
													className="inline-flex items-center gap-1.5 rounded-xl border border-[var(--line)] px-3 py-1.5 text-xs font-semibold text-[var(--sea-ink)] hover:bg-[var(--chip-bg)] hover:text-[#00e599] transition"
												>
													<Key className="h-3.5 w-3.5" />
													Credentials
												</HydratedButton>
												<HydratedButton
													type="button"
													onClick={() => {
														setBrowserStorageId(storage.id);
														setActiveTab("browser");
													}}
													className="inline-flex items-center gap-1.5 rounded-xl border border-[var(--line)] px-3 py-1.5 text-xs font-semibold text-[var(--sea-ink)] hover:bg-[var(--chip-bg)] hover:text-[#00e599] transition"
												>
													<FolderTree className="h-3.5 w-3.5 text-[#00e599]" />
													Browse
												</HydratedButton>
											</div>
											<HydratedButton
												type="button"
												onClick={() => openDeleteStorageModal(storage)}
												className="inline-flex items-center gap-1.5 rounded-xl border border-red-500/20 bg-red-500/5 px-3 py-1.5 text-xs font-semibold text-red-500 hover:bg-red-500/10 hover:border-red-500/40 transition"
											>
												<Trash2 className="h-3.5 w-3.5" />
												Delete
											</HydratedButton>
										</div>
									</div>
								))}
							</div>
						)}
					</div>
				)}

				{/* ======================================================== */}
				{/* SQL Scratchpad Tab Panel (Lazy Loaded)                   */}
				{/* ======================================================== */}
				{activeTab === "scratchpad" && (
					<Suspense
						fallback={<TabPanelSkeleton title="Loading SQL Scratchpad..." />}
					>
						<LazySqlScratchpadPanel
							databases={databases}
							onProvisionDatabase={() => {
								setNewDbName("");
								setCreateDbError(null);
								setIsCreateDbOpen(true);
							}}
						/>
					</Suspense>
				)}

				{/* ======================================================== */}
				{/* Object Browser Tab Panel (Lazy Loaded)                   */}
				{/* ======================================================== */}
				{activeTab === "browser" && (
					<Suspense
						fallback={<TabPanelSkeleton title="Loading Object Browser..." />}
					>
						<LazyObjectBrowserPanel
							storages={storages}
							initialStorageId={browserStorageId}
							onProvisionStorage={openCreateStorageModal}
						/>
					</Suspense>
				)}

				{/* ======================================================== */}
				{/* Settings Tab Panel                                       */}
				{/* ======================================================== */}
				{activeTab === "settings" && (
					<div className="island-shell rounded-2xl p-6 sm:p-8">
						<div className="pb-6 border-b border-[var(--line)]">
							<h3 className="text-lg font-bold text-[var(--sea-ink)] m-0">
								Project Settings
							</h3>
							<p className="text-sm text-[var(--sea-ink-soft)] m-0 mt-1">
								Configuration and metadata for this project.
							</p>
						</div>
						<div className="mt-6 space-y-4 max-w-2xl">
							<div>
								<label className="block text-xs font-bold uppercase tracking-wider text-[var(--sea-ink-soft)] mb-1">
									Project ID
								</label>
								<div className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3.5 py-2.5 font-mono text-sm text-[var(--sea-ink)] select-all">
									{project.id}
								</div>
							</div>

							<div>
								<label className="block text-xs font-bold uppercase tracking-wider text-[var(--sea-ink-soft)] mb-1">
									Project Name
								</label>
								<div className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3.5 py-2.5 text-sm text-[var(--sea-ink)]">
									{project.name}
								</div>
							</div>

							<div>
								<label className="block text-xs font-bold uppercase tracking-wider text-[var(--sea-ink-soft)] mb-1">
									Project Slug
								</label>
								<div className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3.5 py-2.5 font-mono text-sm text-[var(--sea-ink)]">
									{project.slug}
								</div>
							</div>

							<div>
								<label className="block text-xs font-bold uppercase tracking-wider text-[var(--sea-ink-soft)] mb-1">
									Default Region
								</label>
								<div className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3.5 py-2.5 text-sm text-[var(--sea-ink)]">
									{project.region}
								</div>
							</div>

							<div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
								<div>
									<label className="block text-xs font-bold uppercase tracking-wider text-[var(--sea-ink-soft)] mb-1">
										Created At
									</label>
									<div className="text-sm text-[var(--sea-ink)]">
										{new Date(project.createdAt).toLocaleString()}
									</div>
								</div>
								<div>
									<label className="block text-xs font-bold uppercase tracking-wider text-[var(--sea-ink-soft)] mb-1">
										Last Updated
									</label>
									<div className="text-sm text-[var(--sea-ink)]">
										{new Date(project.updatedAt).toLocaleString()}
									</div>
								</div>
							</div>
						</div>
					</div>
				)}
			</div>

			{/* ======================================================== */}
			{/* 1. Database Creation Modal (Ticket 03)                   */}
			{/* ======================================================== */}
			{isCreateDbOpen && (
				<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
					<div className="island-shell w-full max-w-md rounded-2xl p-6 sm:p-7 shadow-2xl animate-in fade-in zoom-in-95 duration-150">
						<div className="flex items-center justify-between pb-4 border-b border-[var(--line)]">
							<div className="flex items-center gap-2.5">
								<div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[rgba(0,229,153,0.14)] text-[#009b67] dark:text-[#00e599]">
									<Database className="h-5 w-5" />
								</div>
								<h3 className="text-lg font-bold text-[var(--sea-ink)] m-0">
									Provision Database
								</h3>
							</div>
							<button
								type="button"
								onClick={() => setIsCreateDbOpen(false)}
								className="rounded-lg p-1 text-[var(--sea-ink-soft)] hover:bg-[var(--chip-bg)] hover:text-[var(--sea-ink)] cursor-pointer"
							>
								<X className="h-5 w-5" />
							</button>
						</div>

						<form onSubmit={handleCreateDatabase} className="mt-5 space-y-4">
							<div>
								<label className="block text-xs font-bold uppercase tracking-wider text-[var(--sea-ink-soft)] mb-1.5">
									Database Name
								</label>
								<input
									type="text"
									required
									autoFocus
									value={newDbName}
									onChange={(e) => setNewDbName(e.target.value)}
									placeholder="e.g. production_db"
									className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3.5 py-2.5 text-sm text-[var(--sea-ink)] placeholder-[var(--sea-ink-soft)]/50 focus:border-[#00e599] focus:outline-hidden"
								/>
								<p className="mt-1.5 text-xs text-[var(--sea-ink-soft)]">
									Only lowercase letters, numbers, and underscores are allowed.
									A dedicated role and cryptographic password will be
									automatically generated.
								</p>
							</div>

							{createDbError && (
								<div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-500 font-medium">
									{createDbError}
								</div>
							)}

							<div className="flex items-center justify-end gap-3 pt-3 border-t border-[var(--line)]">
								<button
									type="button"
									onClick={() => setIsCreateDbOpen(false)}
									className="rounded-xl border border-[var(--line)] bg-transparent px-4 py-2 text-sm font-semibold text-[var(--sea-ink-soft)] hover:bg-[var(--chip-bg)] cursor-pointer"
								>
									Cancel
								</button>
								<button
									type="submit"
									disabled={isCreatingDb}
									className="inline-flex items-center gap-2 rounded-xl bg-[#00e599] px-4 py-2 text-sm font-bold text-[#0a1418] shadow-[0_0_12px_rgba(0,229,153,0.3)] hover:bg-[#00c985] disabled:opacity-50 transition cursor-pointer"
								>
									{isCreatingDb ? (
										<>
											<Loader2 className="h-4 w-4 animate-spin" />
											Provisioning...
										</>
									) : (
										"Provision Database"
									)}
								</button>
							</div>
						</form>
					</div>
				</div>
			)}

			{/* ======================================================== */}
			{/* 2. Database Credential Modal (Ticket 03)                 */}
			{/* ======================================================== */}
			{credsModalDb && (
				<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
					<div className="island-shell w-full max-w-2xl rounded-2xl p-6 sm:p-7 shadow-2xl animate-in fade-in zoom-in-95 duration-150">
						<div className="flex items-center justify-between pb-4 border-b border-[var(--line)]">
							<div className="flex items-center gap-2.5">
								<div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[rgba(0,229,153,0.14)] text-[#009b67] dark:text-[#00e599]">
									<Key className="h-5 w-5" />
								</div>
								<div>
									<h3 className="text-lg font-bold text-[var(--sea-ink)] m-0">
										Connection Details
									</h3>
									<p className="text-xs text-[var(--sea-ink-soft)] m-0 font-mono">
										{credsModalDb.name}
									</p>
								</div>
							</div>
							<button
								type="button"
								onClick={() => setCredsModalDb(null)}
								className="rounded-lg p-1 text-[var(--sea-ink-soft)] hover:bg-[var(--chip-bg)] hover:text-[var(--sea-ink)] cursor-pointer"
							>
								<X className="h-5 w-5" />
							</button>
						</div>

						{/* Parameters Breakdown */}
						<div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-2.5 rounded-xl border border-[var(--line)] bg-[var(--foam)] p-3.5 text-xs">
							<div>
								<span className="block text-[var(--sea-ink-soft)] font-medium">
									Host
								</span>
								<span className="font-mono font-semibold text-[var(--sea-ink)]">
									{credsModalDb.host}
								</span>
							</div>
							<div>
								<span className="block text-[var(--sea-ink-soft)] font-medium">
									Port
								</span>
								<span className="font-mono font-semibold text-[var(--sea-ink)]">
									{credsModalDb.port}
								</span>
							</div>
							<div>
								<span className="block text-[var(--sea-ink-soft)] font-medium">
									Database
								</span>
								<span className="font-mono font-semibold text-[var(--sea-ink)] truncate block">
									{credsModalDb.name}
								</span>
							</div>
							<div>
								<span className="block text-[var(--sea-ink-soft)] font-medium">
									User
								</span>
								<span className="font-mono font-semibold text-[var(--sea-ink)] truncate block">
									{credsModalDb.username}
								</span>
							</div>
						</div>

						{/* Credential Tabs */}
						<div className="mt-5">
							<div className="flex border-b border-[var(--line)] gap-1 overflow-x-auto text-xs font-semibold">
								<button
									type="button"
									onClick={() => setDbCredTab("uri")}
									className={`px-3.5 py-2 border-b-2 cursor-pointer transition ${
										dbCredTab === "uri"
											? "border-[#00e599] text-[var(--sea-ink)] bg-[rgba(0,229,153,0.08)] rounded-t-lg"
											: "border-transparent text-[var(--sea-ink-soft)] hover:text-[var(--sea-ink)]"
									}`}
								>
									Connection URI
								</button>
								<button
									type="button"
									onClick={() => setDbCredTab("env")}
									className={`px-3.5 py-2 border-b-2 cursor-pointer transition ${
										dbCredTab === "env"
											? "border-[#00e599] text-[var(--sea-ink)] bg-[rgba(0,229,153,0.08)] rounded-t-lg"
											: "border-transparent text-[var(--sea-ink-soft)] hover:text-[var(--sea-ink)]"
									}`}
								>
									.env Snippet
								</button>
								<button
									type="button"
									onClick={() => setDbCredTab("psql")}
									className={`px-3.5 py-2 border-b-2 cursor-pointer transition ${
										dbCredTab === "psql"
											? "border-[#00e599] text-[var(--sea-ink)] bg-[rgba(0,229,153,0.08)] rounded-t-lg"
											: "border-transparent text-[var(--sea-ink-soft)] hover:text-[var(--sea-ink)]"
									}`}
								>
									psql CLI
								</button>
								<button
									type="button"
									onClick={() => setDbCredTab("drizzle")}
									className={`px-3.5 py-2 border-b-2 cursor-pointer transition ${
										dbCredTab === "drizzle"
											? "border-[#00e599] text-[var(--sea-ink)] bg-[rgba(0,229,153,0.08)] rounded-t-lg"
											: "border-transparent text-[var(--sea-ink-soft)] hover:text-[var(--sea-ink)]"
									}`}
								>
									Drizzle ORM
								</button>
								<button
									type="button"
									onClick={() => setDbCredTab("prisma")}
									className={`px-3.5 py-2 border-b-2 cursor-pointer transition ${
										dbCredTab === "prisma"
											? "border-[#00e599] text-[var(--sea-ink)] bg-[rgba(0,229,153,0.08)] rounded-t-lg"
											: "border-transparent text-[var(--sea-ink-soft)] hover:text-[var(--sea-ink)]"
									}`}
								>
									Prisma
								</button>
							</div>

							{/* Snippet Content */}
							<div className="mt-3 relative">
								<div className="rounded-xl border border-[var(--line)] bg-[#071013] p-4 text-xs font-mono text-[#e7f3ec] overflow-x-auto min-h-[90px] flex items-center">
									<pre className="m-0 whitespace-pre-wrap break-all w-full">
										{dbCredTab === "uri" && credsModalDb.connectionString}
										{dbCredTab === "env" && credsModalDb.envSnippet}
										{dbCredTab === "psql" && credsModalDb.psqlCommand}
										{dbCredTab === "drizzle" && credsModalDb.drizzleSnippet}
										{dbCredTab === "prisma" && credsModalDb.prismaSnippet}
									</pre>
								</div>

								<button
									type="button"
									onClick={() => {
										const text =
											dbCredTab === "uri"
												? credsModalDb.connectionString
												: dbCredTab === "env"
													? credsModalDb.envSnippet
													: dbCredTab === "psql"
														? credsModalDb.psqlCommand
														: dbCredTab === "drizzle"
															? credsModalDb.drizzleSnippet
															: credsModalDb.prismaSnippet;
										copyToClipboard(text, dbCredTab);
									}}
									className="absolute top-2.5 right-2.5 inline-flex items-center gap-1.5 rounded-lg bg-[rgba(255,255,255,0.12)] hover:bg-[rgba(255,255,255,0.2)] px-2.5 py-1.5 text-xs font-sans font-semibold text-[#00e599] transition cursor-pointer backdrop-blur-xs"
								>
									{copiedKey === dbCredTab ? (
										<>
											<Check className="h-3.5 w-3.5" />
											<span>Copied!</span>
										</>
									) : (
										<>
											<Copy className="h-3.5 w-3.5" />
											<span>Copy</span>
										</>
									)}
								</button>
							</div>
						</div>

						{/* CA Certificate Section */}
						<div className="mt-5">
							<CaCertificateSection
								onCopyPem={handleCopyCaPem}
								copied={copiedKey === "ca-pem"}
							/>
						</div>

						<div className="mt-6 flex items-center justify-end">
							<button
								type="button"
								onClick={() => setCredsModalDb(null)}
								className="rounded-xl bg-[#00e599] px-5 py-2 text-sm font-bold text-[#0a1418] hover:bg-[#00c985] transition cursor-pointer shadow-[0_0_12px_rgba(0,229,153,0.3)]"
							>
								Done
							</button>
						</div>
					</div>
				</div>
			)}

			{/* ======================================================== */}
			{/* 3. Database Password Reset Modal (Ticket 03)             */}
			{/* ======================================================== */}
			{resetModalDb && (
				<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
					<div className="island-shell w-full max-w-md rounded-2xl p-6 sm:p-7 shadow-2xl animate-in fade-in zoom-in-95 duration-150">
						<div className="flex items-center justify-between pb-4 border-b border-[var(--line)]">
							<div className="flex items-center gap-2.5">
								<div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[rgba(79,184,178,0.14)] text-[var(--lagoon-deep)]">
									<RotateCw className="h-5 w-5" />
								</div>
								<h3 className="text-lg font-bold text-[var(--sea-ink)] m-0">
									Reset Password
								</h3>
							</div>
							<button
								type="button"
								onClick={() => setResetModalDb(null)}
								className="rounded-lg p-1 text-[var(--sea-ink-soft)] hover:bg-[var(--chip-bg)] hover:text-[var(--sea-ink)] cursor-pointer"
							>
								<X className="h-5 w-5" />
							</button>
						</div>

						{resetSuccessCreds ? (
							<div className="mt-5 space-y-4">
								<div className="flex items-center gap-2 text-xs font-semibold text-[#009b67] dark:text-[#00e599]">
									<CheckCircle2 className="h-4 w-4" />
									<span>Password rotated successfully!</span>
								</div>

								<div>
									<label className="block text-xs font-bold uppercase tracking-wider text-[var(--sea-ink-soft)] mb-1">
										New Password
									</label>
									<div className="flex items-center justify-between rounded-xl border border-[var(--line)] bg-[var(--foam)] p-3 font-mono text-xs text-[var(--sea-ink)]">
										<span className="truncate">
											{resetSuccessCreds.password}
										</span>
										<button
											type="button"
											onClick={() =>
												copyToClipboard(
													resetSuccessCreds.password,
													"reset-pass",
												)
											}
											className="ml-2 inline-flex items-center gap-1 font-sans text-xs font-semibold text-[#009b67] dark:text-[#00e599] hover:underline cursor-pointer"
										>
											{copiedKey === "reset-pass" ? (
												<Check className="h-3 w-3" />
											) : (
												<Copy className="h-3 w-3" />
											)}
											<span>
												{copiedKey === "reset-pass" ? "Copied" : "Copy"}
											</span>
										</button>
									</div>
								</div>

								<div>
									<label className="block text-xs font-bold uppercase tracking-wider text-[var(--sea-ink-soft)] mb-1">
										Updated Connection URI
									</label>
									<div className="flex items-center justify-between rounded-xl border border-[var(--line)] bg-[var(--foam)] p-3 font-mono text-xs text-[var(--sea-ink)]">
										<span className="truncate mr-2">
											{resetSuccessCreds.connectionString}
										</span>
										<button
											type="button"
											onClick={() =>
												copyToClipboard(
													resetSuccessCreds.connectionString,
													"reset-uri",
												)
											}
											className="inline-flex items-center gap-1 font-sans text-xs font-semibold text-[#009b67] dark:text-[#00e599] hover:underline cursor-pointer"
										>
											{copiedKey === "reset-uri" ? (
												<Check className="h-3 w-3" />
											) : (
												<Copy className="h-3 w-3" />
											)}
											<span>
												{copiedKey === "reset-uri" ? "Copied" : "Copy"}
											</span>
										</button>
									</div>
								</div>

								{/* CA Certificate Section */}
								<CaCertificateSection
									onCopyPem={handleCopyCaPem}
									copied={copiedKey === "ca-pem"}
								/>

								<div className="pt-3 border-t border-[var(--line)] flex justify-end">
									<button
										type="button"
										onClick={() => setResetModalDb(null)}
										className="rounded-xl bg-[#00e599] px-4 py-2 text-sm font-bold text-[#0a1418] hover:bg-[#00c985] transition cursor-pointer"
									>
										Done
									</button>
								</div>
							</div>
						) : (
							<div className="mt-5 space-y-4">
								<div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3.5 text-xs text-amber-600 dark:text-amber-400">
									<div className="flex items-start gap-2">
										<AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
										<span>
											Rotating this password will immediately update the
											PostgreSQL user role (<code>{resetModalDb.username}</code>
											) and terminate existing connections. Any running client
											apps must reconnect with the new password.
										</span>
									</div>
								</div>

								<div className="flex items-center justify-end gap-3 pt-3 border-t border-[var(--line)]">
									<button
										type="button"
										onClick={() => setResetModalDb(null)}
										className="rounded-xl border border-[var(--line)] bg-transparent px-4 py-2 text-sm font-semibold text-[var(--sea-ink-soft)] hover:bg-[var(--chip-bg)] cursor-pointer"
									>
										Cancel
									</button>
									<button
										type="button"
										disabled={isResettingDb}
										onClick={handleResetPassword}
										className="inline-flex items-center gap-2 rounded-xl bg-[var(--lagoon-deep)] px-4 py-2 text-sm font-bold text-white hover:opacity-90 disabled:opacity-50 transition cursor-pointer"
									>
										{isResettingDb ? (
											<>
												<Loader2 className="h-4 w-4 animate-spin" />
												Rotating...
											</>
										) : (
											"Rotate Password"
										)}
									</button>
								</div>
							</div>
						)}
					</div>
				</div>
			)}

			{/* ======================================================== */}
			{/* 4. Database Deletion Modal with Typed Confirmation (ADR 0014) */}
			{/* ======================================================== */}
			{deleteModalDb && (
				<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
					<div className="island-shell w-full max-w-md rounded-2xl p-6 sm:p-7 shadow-2xl animate-in fade-in zoom-in-95 duration-150 border-red-500/30">
						<div className="flex items-center justify-between pb-4 border-b border-[var(--line)]">
							<div className="flex items-center gap-2.5">
								<div className="flex h-9 w-9 items-center justify-center rounded-xl bg-red-500/15 text-red-500">
									<ShieldAlert className="h-5 w-5" />
								</div>
								<h3 className="text-lg font-bold text-[var(--sea-ink)] m-0">
									Delete Database
								</h3>
							</div>
							<button
								type="button"
								onClick={() => setDeleteModalDb(null)}
								className="rounded-lg p-1 text-[var(--sea-ink-soft)] hover:bg-[var(--chip-bg)] hover:text-[var(--sea-ink)] cursor-pointer"
							>
								<X className="h-5 w-5" />
							</button>
						</div>

						<div className="mt-5 space-y-4">
							<div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3.5 text-xs text-red-600 dark:text-red-400">
								<p className="font-semibold m-0 mb-1">
									Warning: Irreversible Action
								</p>
								<p className="m-0">
									This will permanently terminate active connections, drop the
									database <strong>{deleteModalDb.name}</strong>, and drop the
									user role <strong>{deleteModalDb.username}</strong>. All
									tables and data will be erased immediately.
								</p>
							</div>

							<div>
								<label className="block text-xs font-bold uppercase tracking-wider text-[var(--sea-ink-soft)] mb-1.5">
									Type{" "}
									<span className="font-mono text-red-500 select-all font-bold">
										{deleteModalDb.name}
									</span>{" "}
									to confirm:
								</label>
								<input
									type="text"
									autoFocus
									value={deleteDbConfirmText}
									onChange={(e) => setDeleteDbConfirmText(e.target.value)}
									placeholder={deleteModalDb.name}
									className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3.5 py-2.5 font-mono text-sm text-[var(--sea-ink)] focus:border-red-500 focus:outline-hidden"
								/>
							</div>

							{deleteDbError && (
								<div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-500 font-medium">
									{deleteDbError}
								</div>
							)}

							<div className="flex items-center justify-end gap-3 pt-3 border-t border-[var(--line)]">
								<button
									type="button"
									onClick={() => setDeleteModalDb(null)}
									className="rounded-xl border border-[var(--line)] bg-transparent px-4 py-2 text-sm font-semibold text-[var(--sea-ink-soft)] hover:bg-[var(--chip-bg)] cursor-pointer"
								>
									Cancel
								</button>
								<button
									type="button"
									disabled={
										deleteDbConfirmText !== deleteModalDb.name || isDeletingDb
									}
									onClick={handleDeleteDatabase}
									className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2 text-sm font-bold text-white hover:bg-red-700 disabled:opacity-40 disabled:cursor-not-allowed transition cursor-pointer shadow-[0_0_12px_rgba(239,68,68,0.3)]"
								>
									{isDeletingDb ? (
										<>
											<Loader2 className="h-4 w-4 animate-spin" />
											Deleting...
										</>
									) : (
										"Delete Database"
									)}
								</button>
							</div>
						</div>
					</div>
				</div>
			)}

			{/* ======================================================== */}
			{/* 5. S3 Storage Creation Modal (Ticket 04)                 */}
			{/* ======================================================== */}
			{isCreateStorageOpen && (
				<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-xs">
					<div className="island-shell w-full max-w-lg rounded-2xl p-6 sm:p-8 shadow-2xl animate-in fade-in zoom-in-95 duration-150">
						<div className="flex items-center justify-between pb-4 border-b border-[var(--line)]">
							<div className="flex items-center gap-2.5">
								<div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[rgba(0,229,153,0.12)] text-[#009b67] dark:text-[#00e599]">
									<HardDrive className="h-5 w-5" />
								</div>
								<div>
									<h3 className="text-lg font-bold text-[var(--sea-ink)] m-0">
										Provision S3 Storage
									</h3>
									<p className="text-xs text-[var(--sea-ink-soft)] m-0">
										Create an isolated S3 bucket on SeaweedFS
									</p>
								</div>
							</div>
							<button
								type="button"
								onClick={closeCreateStorageModal}
								className="rounded-lg p-1 text-[var(--sea-ink-soft)] hover:text-[var(--sea-ink)] hover:bg-[var(--line)] transition cursor-pointer"
							>
								<X className="h-5 w-5" />
							</button>
						</div>

						{createStorageError && (
							<div className="mt-4 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-500">
								{createStorageError}
							</div>
						)}

						<form onSubmit={handleCreateStorage} className="mt-5 space-y-4">
							<div>
								<label
									htmlFor={bucketInputId}
									className="block text-xs font-bold uppercase tracking-wider text-[var(--sea-ink-soft)] mb-1.5"
								>
									Bucket Name <span className="text-[#ff5c5c]">*</span>
								</label>
								<input
									id={bucketInputId}
									type="text"
									required
									autoFocus
									placeholder="e.g. app-media-production"
									value={bucketName}
									onChange={(e) => setBucketName(e.target.value.toLowerCase())}
									className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3.5 py-2.5 font-mono text-sm text-[var(--sea-ink)] placeholder-[var(--sea-ink-soft)] focus:outline-none focus:border-[#00e599] focus:ring-1 focus:ring-[#00e599]"
								/>
								<p className="mt-1.5 text-[11px] text-[var(--sea-ink-soft)]">
									3-63 characters, lowercase letters, numbers, and hyphens only.
								</p>
							</div>

							<div className="grid grid-cols-2 gap-3">
								<div>
									<label className="block text-xs font-bold uppercase tracking-wider text-[var(--sea-ink-soft)] mb-1">
										Region
									</label>
									<div className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3.5 py-2 text-xs font-medium text-[var(--sea-ink)]">
										{project.region}
									</div>
								</div>
								<div>
									<label className="block text-xs font-bold uppercase tracking-wider text-[var(--sea-ink-soft)] mb-1">
										Endpoint
									</label>
									<div className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3.5 py-2 text-xs font-mono text-[var(--sea-ink)] truncate">
										http://localhost:8333
									</div>
								</div>
							</div>

							<div className="rounded-xl border border-[rgba(0,229,153,0.25)] bg-[rgba(0,229,153,0.06)] p-3 text-xs text-[var(--sea-ink)] flex items-start gap-2">
								<ShieldCheck className="h-4 w-4 text-[#00e599] shrink-0 mt-0.5" />
								<span>
									SeaweedFS IAM will automatically configure dedicated
									credentials restricted exclusively to this bucket.
								</span>
							</div>

							<div className="flex items-center justify-end gap-3 pt-3 border-t border-[var(--line)]">
								<button
									type="button"
									onClick={closeCreateStorageModal}
									className="rounded-xl border border-[var(--line)] px-4 py-2.5 text-xs font-semibold text-[var(--sea-ink-soft)] hover:text-[var(--sea-ink)] hover:bg-[var(--line)] transition cursor-pointer"
								>
									Cancel
								</button>
								<button
									type="submit"
									disabled={isCreatingStorage || !bucketName.trim()}
									className="inline-flex items-center gap-2 rounded-xl bg-[#00e599] px-5 py-2.5 text-xs font-bold text-[#0a1418] shadow-[0_0_12px_rgba(0,229,153,0.3)] transition hover:bg-[#00c985] disabled:opacity-50 cursor-pointer"
								>
									{isCreatingStorage ? "Provisioning..." : "Provision Bucket"}
								</button>
							</div>
						</form>
					</div>
				</div>
			)}

			{/* ======================================================== */}
			{/* 6. S3 Credential Modal (Ticket 04)                       */}
			{/* ======================================================== */}
			{selectedStorage && (
				<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-xs">
					<div className="island-shell w-full max-w-2xl rounded-2xl p-6 sm:p-8 shadow-2xl animate-in fade-in zoom-in-95 duration-150 max-h-[90vh] overflow-y-auto">
						<div className="flex items-center justify-between pb-4 border-b border-[var(--line)]">
							<div className="flex items-center gap-2.5">
								<div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[rgba(0,229,153,0.12)] text-[#009b67] dark:text-[#00e599]">
									<Key className="h-5 w-5" />
								</div>
								<div>
									<h3 className="text-lg font-bold text-[var(--sea-ink)] m-0">
										S3 Credentials
									</h3>
									<p className="text-xs text-[var(--sea-ink-soft)] m-0 font-mono">
										{selectedStorage.bucketName}
									</p>
								</div>
							</div>
							<button
								type="button"
								onClick={closeStorageCredentialsModal}
								className="rounded-lg p-1 text-[var(--sea-ink-soft)] hover:text-[var(--sea-ink)] hover:bg-[var(--line)] transition cursor-pointer"
							>
								<X className="h-5 w-5" />
							</button>
						</div>

						{isLoadingStorageCreds ? (
							<div className="py-12 text-center text-sm text-[var(--sea-ink-soft)]">
								Loading credentials...
							</div>
						) : (
							<div className="mt-5 space-y-5">
								<div className="grid grid-cols-1 md:grid-cols-2 gap-3">
									<div className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-3">
										<span className="block text-[11px] font-bold uppercase tracking-wider text-[var(--sea-ink-soft)] mb-1">
											Endpoint URL
										</span>
										<span className="font-mono text-xs text-[var(--sea-ink)] select-all">
											{selectedStorage.endpoint}
										</span>
									</div>

									<div className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-3">
										<span className="block text-[11px] font-bold uppercase tracking-wider text-[var(--sea-ink-soft)] mb-1">
											Bucket Name
										</span>
										<span className="font-mono text-xs text-[var(--sea-ink)] select-all">
											{selectedStorage.bucketName}
										</span>
									</div>

									<div className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-3">
										<span className="block text-[11px] font-bold uppercase tracking-wider text-[var(--sea-ink-soft)] mb-1">
											Access Key ID
										</span>
										<span className="font-mono text-xs text-[var(--sea-ink)] select-all">
											{selectedStorage.accessKeyId}
										</span>
									</div>

									<div className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-3">
										<div className="flex items-center justify-between mb-1">
											<span className="text-[11px] font-bold uppercase tracking-wider text-[var(--sea-ink-soft)]">
												Secret Access Key
											</span>
											<button
												type="button"
												onClick={() => setIsSecretVisible(!isSecretVisible)}
												className="text-[11px] text-[#009b67] dark:text-[#00e599] hover:underline flex items-center gap-1 cursor-pointer"
											>
												{isSecretVisible ? (
													<>
														<EyeOff className="h-3 w-3" /> Hide
													</>
												) : (
													<>
														<Eye className="h-3 w-3" /> Show
													</>
												)}
											</button>
										</div>
										<span className="font-mono text-xs text-[var(--sea-ink)] select-all">
											{isSecretVisible
												? selectedStorage.secretAccessKey
												: "••••••••••••••••••••••••••••••••"}
										</span>
									</div>
								</div>

								<div className="space-y-3">
									<div className="flex border-b border-[var(--line)] gap-3">
										<button
											type="button"
											onClick={() => setStorageCredTab("env")}
											className={`pb-2 text-xs font-bold border-b-2 transition cursor-pointer ${
												storageCredTab === "env"
													? "border-[#00e599] text-[#00e599]"
													: "border-transparent text-[var(--sea-ink-soft)] hover:text-[var(--sea-ink)]"
											}`}
										>
											.env Snippet
										</button>
										<button
											type="button"
											onClick={() => setStorageCredTab("cli")}
											className={`pb-2 text-xs font-bold border-b-2 transition cursor-pointer ${
												storageCredTab === "cli"
													? "border-[#00e599] text-[#00e599]"
													: "border-transparent text-[var(--sea-ink-soft)] hover:text-[var(--sea-ink)]"
											}`}
										>
											AWS CLI
										</button>
										<button
											type="button"
											onClick={() => setStorageCredTab("sdk")}
											className={`pb-2 text-xs font-bold border-b-2 transition cursor-pointer ${
												storageCredTab === "sdk"
													? "border-[#00e599] text-[#00e599]"
													: "border-transparent text-[var(--sea-ink-soft)] hover:text-[var(--sea-ink)]"
											}`}
										>
											Node AWS SDK
										</button>
									</div>

									{formattedStorageCreds && (
										<div className="relative rounded-xl border border-[var(--line)] bg-[#0a1418] p-4 font-mono text-xs text-[#00e599]">
											<div className="absolute right-3 top-3">
												<button
													type="button"
													onClick={() => {
														const text =
															storageCredTab === "env"
																? formattedStorageCreds.env
																: storageCredTab === "cli"
																	? formattedStorageCreds.awsCli
																	: formattedStorageCreds.nodeSdk;
														copyToClipboard(text, "storage-snippet");
													}}
													className="inline-flex items-center gap-1.5 rounded-lg border border-[rgba(0,229,153,0.3)] bg-[rgba(0,229,153,0.12)] px-2.5 py-1 text-xs font-semibold text-[#00e599] hover:bg-[rgba(0,229,153,0.2)] transition cursor-pointer"
												>
													{copiedKey === "storage-snippet" ? (
														<>
															<Check className="h-3.5 w-3.5" />
															Copied!
														</>
													) : (
														<>
															<Copy className="h-3.5 w-3.5" />
															Copy
														</>
													)}
												</button>
											</div>

											<pre className="overflow-x-auto whitespace-pre-wrap pr-16 m-0 leading-relaxed text-[#cde9dd]">
												{storageCredTab === "env" && formattedStorageCreds.env}
												{storageCredTab === "cli" &&
													formattedStorageCreds.awsCli}
												{storageCredTab === "sdk" &&
													formattedStorageCreds.nodeSdk}
											</pre>
										</div>
									)}
								</div>

								<div className="flex items-center justify-end pt-3 border-t border-[var(--line)]">
									<button
										type="button"
										onClick={closeStorageCredentialsModal}
										className="rounded-xl border border-[var(--line)] px-4 py-2 text-xs font-semibold text-[var(--sea-ink)] hover:bg-[var(--line)] transition cursor-pointer"
									>
										Done
									</button>
								</div>
							</div>
						)}
					</div>
				</div>
			)}

			{/* ======================================================== */}
			{/* 7. S3 Deletion Modal with Typed Confirmation (ADR 0014)  */}
			{/* ======================================================== */}
			{storageToDelete && (
				<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-xs">
					<div className="island-shell w-full max-w-lg rounded-2xl p-6 sm:p-8 shadow-2xl animate-in fade-in zoom-in-95 duration-150">
						<div className="flex items-center justify-between pb-4 border-b border-[var(--line)]">
							<div className="flex items-center gap-2.5">
								<div className="flex h-9 w-9 items-center justify-center rounded-xl bg-red-500/10 text-red-500">
									<AlertTriangle className="h-5 w-5" />
								</div>
								<div>
									<h3 className="text-lg font-bold text-[var(--sea-ink)] m-0">
										Delete Storage Bucket
									</h3>
									<p className="text-xs text-[var(--sea-ink-soft)] m-0">
										Irreversible action with typed confirmation
									</p>
								</div>
							</div>
							<button
								type="button"
								onClick={closeDeleteStorageModal}
								className="rounded-lg p-1 text-[var(--sea-ink-soft)] hover:text-[var(--sea-ink)] hover:bg-[var(--line)] transition cursor-pointer"
							>
								<X className="h-5 w-5" />
							</button>
						</div>

						{deleteStorageError && (
							<div className="mt-4 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-500">
								{deleteStorageError}
							</div>
						)}

						<form onSubmit={handleDeleteStorage} className="mt-5 space-y-4">
							<p className="text-sm text-[var(--sea-ink-soft)] leading-relaxed m-0">
								This will permanently delete bucket{" "}
								<strong className="text-[var(--sea-ink)] font-mono">
									{storageToDelete.bucketName}
								</strong>
								, delete all stored objects inside it, and revoke its scoped IAM
								access credentials in SeaweedFS.
							</p>

							<div className="rounded-xl border border-red-500/20 bg-red-500/5 p-3.5">
								<label
									htmlFor={deleteConfirmInputId}
									className="block text-xs font-semibold text-[var(--sea-ink)] mb-2"
								>
									To confirm, type{" "}
									<span className="font-mono font-bold text-red-400 select-all">
										{storageToDelete.bucketName}
									</span>{" "}
									below:
								</label>
								<input
									id={deleteConfirmInputId}
									type="text"
									required
									autoFocus
									placeholder={storageToDelete.bucketName}
									value={typedConfirmName}
									onChange={(e) => setTypedConfirmName(e.target.value)}
									className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3.5 py-2.5 font-mono text-sm text-[var(--sea-ink)] focus:outline-none focus:border-red-500 focus:ring-1 focus:ring-red-500"
								/>
							</div>

							<div className="flex items-center justify-end gap-3 pt-3 border-t border-[var(--line)]">
								<button
									type="button"
									onClick={closeDeleteStorageModal}
									className="rounded-xl border border-[var(--line)] px-4 py-2.5 text-xs font-semibold text-[var(--sea-ink-soft)] hover:text-[var(--sea-ink)] hover:bg-[var(--line)] transition cursor-pointer"
								>
									Cancel
								</button>
								<button
									type="submit"
									disabled={
										isDeletingStorage ||
										typedConfirmName !== storageToDelete.bucketName
									}
									className="inline-flex items-center gap-2 rounded-xl bg-red-500 px-5 py-2.5 text-xs font-bold text-white shadow-[0_0_12px_rgba(239,68,68,0.3)] transition hover:bg-red-600 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
								>
									{isDeletingStorage ? "Deleting..." : "Delete Bucket"}
								</button>
							</div>
						</form>
					</div>
				</div>
			)}
		</main>
	);
}
