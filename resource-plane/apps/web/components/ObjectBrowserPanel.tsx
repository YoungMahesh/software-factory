import type React from "react";
import { useState, useEffect, useRef } from "react";
import {
	HardDrive,
	Plus,
	FolderTree,
	RefreshCw,
	FileText,
	FileUp,
	Upload,
	Download,
	Trash2,
	CheckCircle2,
	AlertTriangle,
	Loader2,
} from "lucide-react";
import {
	listBucketObjectsFn,
	uploadBucketObjectFn,
	deleteBucketObjectFn,
	getObjectContentFn,
} from "@/app/actions";
import type { BucketObject } from "@/services/browser";
import type { ObjectStorage } from "@/lib/storage-helpers";
import { HydratedButton } from "./HydratedButton";

function formatBytes(bytes: number, decimals = 1): string {
	if (!bytes || bytes === 0) return "0 B";
	const k = 1024;
	const dm = decimals < 0 ? 0 : decimals;
	const sizes = ["B", "KB", "MB", "GB", "TB"];
	const i = Math.floor(Math.log(bytes) / Math.log(k));
	return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

export interface ObjectBrowserPanelProps {
	storages: ObjectStorage[];
	onProvisionStorage: () => void;
	initialStorageId?: string;
	isHydrated?: boolean;
}

export function ObjectBrowserPanel({
	storages,
	onProvisionStorage,
	initialStorageId,
	isHydrated = true,
}: ObjectBrowserPanelProps) {
	const [browserStorageId, setBrowserStorageId] = useState<string>(
		initialStorageId || storages[0]?.id || "",
	);
	const [bucketObjects, setBucketObjects] = useState<BucketObject[]>([]);
	const [isLoadingObjects, setIsLoadingObjects] = useState(false);
	const [objectBrowserError, setObjectBrowserError] = useState<string | null>(
		null,
	);

	const [uploadFile, setUploadFile] = useState<File | null>(null);
	const [customUploadKey, setCustomUploadKey] = useState("");
	const [isUploadingObject, setIsUploadingObject] = useState(false);
	const [uploadSuccessMessage, setUploadSuccessMessage] = useState<
		string | null
	>(null);
	const [isDraggingOver, setIsDraggingOver] = useState(false);
	const fileInputRef = useRef<HTMLInputElement | null>(null);

	const [downloadingKey, setDownloadingKey] = useState<string | null>(null);
	const [deletingKey, setDeletingKey] = useState<string | null>(null);

	useEffect(() => {
		if (initialStorageId) {
			setBrowserStorageId(initialStorageId);
		} else if (!browserStorageId && storages.length > 0) {
			setBrowserStorageId(storages[0].id);
		}
	}, [initialStorageId, storages, browserStorageId]);

	const loadBucketObjects = async (storageId: string) => {
		if (!storageId) {
			setBucketObjects([]);
			return;
		}
		setIsLoadingObjects(true);
		setObjectBrowserError(null);
		try {
			const objects = await listBucketObjectsFn({ data: storageId });
			setBucketObjects(objects);
		} catch (err: any) {
			setObjectBrowserError(err.message || "Failed to list bucket objects");
			setBucketObjects([]);
		} finally {
			setIsLoadingObjects(false);
		}
	};

	useEffect(() => {
		if (browserStorageId) {
			loadBucketObjects(browserStorageId);
		}
	}, [browserStorageId]);

	const handleUploadObject = async (e?: React.FormEvent) => {
		if (e) e.preventDefault();
		if (!isHydrated) return;
		if (!browserStorageId) {
			setObjectBrowserError("Please select a storage bucket");
			return;
		}
		if (!uploadFile) {
			setObjectBrowserError("Please select a file to upload");
			return;
		}

		const key = customUploadKey.trim() || uploadFile.name;
		setIsUploadingObject(true);
		setObjectBrowserError(null);
		setUploadSuccessMessage(null);

		try {
			const reader = new FileReader();
			const dataUrlPromise = new Promise<string>((resolve, reject) => {
				reader.onload = () => resolve(reader.result as string);
				reader.onerror = reject;
				reader.readAsDataURL(uploadFile);
			});

			const dataUrl = await dataUrlPromise;
			await uploadBucketObjectFn({
				data: {
					storageId: browserStorageId,
					key,
					content: dataUrl,
					contentType: uploadFile.type || "application/octet-stream",
				},
			});

			setUploadSuccessMessage(`Successfully uploaded "${key}"`);
			setUploadFile(null);
			setCustomUploadKey("");
			if (fileInputRef.current) {
				fileInputRef.current.value = "";
			}
			setTimeout(() => setUploadSuccessMessage(null), 4000);

			await loadBucketObjects(browserStorageId);
		} catch (err: any) {
			setObjectBrowserError(err.message || "Failed to upload object");
		} finally {
			setIsUploadingObject(false);
		}
	};

	const handleDownloadObject = async (key: string) => {
		if (!isHydrated) return;
		if (!browserStorageId) return;
		setDownloadingKey(key);
		try {
			const fileData = await getObjectContentFn({
				data: { storageId: browserStorageId, key },
			});

			const byteCharacters = atob(fileData.base64);
			const byteNumbers = new Array(byteCharacters.length);
			for (let i = 0; i < byteCharacters.length; i++) {
				byteNumbers[i] = byteCharacters.charCodeAt(i);
			}
			const byteArray = new Uint8Array(byteNumbers);
			const blob = new Blob([byteArray], { type: fileData.contentType });
			const url = URL.createObjectURL(blob);
			const a = document.createElement("a");
			a.href = url;
			a.download = key.split("/").pop() || key;
			document.body.appendChild(a);
			a.click();
			document.body.removeChild(a);
			URL.revokeObjectURL(url);
		} catch (err: any) {
			alert(`Failed to download object: ${err.message}`);
		} finally {
			setDownloadingKey(null);
		}
	};

	const handleDeleteObject = async (key: string) => {
		if (!isHydrated) return;
		if (!browserStorageId) return;
		if (
			!confirm(`Are you sure you want to delete "${key}" from this bucket?`)
		) {
			return;
		}
		setDeletingKey(key);
		try {
			await deleteBucketObjectFn({
				data: { storageId: browserStorageId, key },
			});
			await loadBucketObjects(browserStorageId);
		} catch (err: any) {
			alert(`Failed to delete object: ${err.message}`);
		} finally {
			setDeletingKey(null);
		}
	};

	const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
		e.preventDefault();
		setIsDraggingOver(false);
		if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
			const file = e.dataTransfer.files[0];
			setUploadFile(file);
			if (!customUploadKey) {
				setCustomUploadKey(file.name);
			}
		}
	};

	return (
		<div className="space-y-6">
			<div className="island-shell rounded-2xl p-6 sm:p-8">
				<div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-6 border-b border-[var(--line)] gap-4">
					<div>
						<h3 className="text-lg font-bold text-[var(--sea-ink)] m-0">
							S3 Object Browser
						</h3>
						<p className="text-sm text-[var(--sea-ink-soft)] m-0 mt-1">
							Explore stored files, upload new test objects, and download assets
							from your provisioned SeaweedFS buckets.
						</p>
					</div>
					{storages.length > 0 && (
						<div className="flex items-center gap-3">
							<div className="flex items-center gap-2">
								<label className="text-xs font-semibold text-[var(--sea-ink-soft)] whitespace-nowrap">
									Bucket:
								</label>
								<select
									value={browserStorageId}
									disabled={!isHydrated}
									onChange={(e) => {
										setBrowserStorageId(e.target.value);
										setUploadSuccessMessage(null);
										setObjectBrowserError(null);
									}}
									className={`rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-xs font-mono font-semibold text-[var(--sea-ink)] focus:border-[#00e599] focus:outline-hidden ${
										!isHydrated ? "opacity-75 cursor-wait" : "cursor-pointer"
									}`}
								>
									{storages.map((s) => (
										<option key={s.id} value={s.id}>
											{s.bucketName} ({s.region})
										</option>
									))}
								</select>
							</div>

							<HydratedButton
								isHydrated={isHydrated}
								title="Refresh objects list"
								onClick={() => loadBucketObjects(browserStorageId)}
								disabled={isLoadingObjects}
								className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-2 text-[var(--sea-ink-soft)] hover:text-[var(--sea-ink)] hover:border-[#00e599]/50 transition disabled:opacity-50"
							>
								<RefreshCw
									className={`h-4 w-4 ${isLoadingObjects ? "animate-spin text-[#00e599]" : ""}`}
								/>
							</HydratedButton>
						</div>
					)}
				</div>

				{storages.length === 0 ? (
					<div className="py-14 text-center">
						<div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-[rgba(0,229,153,0.12)] border border-[rgba(0,229,153,0.25)] text-[#009b67] dark:text-[#00e599]">
							<HardDrive className="h-7 w-7" />
						</div>
						<h4 className="text-base font-bold text-[var(--sea-ink)] m-0">
							No storage buckets provisioned
						</h4>
						<p className="mx-auto mt-2 max-w-sm text-sm text-[var(--sea-ink-soft)]">
							Provision an S3-compatible storage bucket first to browse and
							manage stored objects.
						</p>
						<HydratedButton
							isHydrated={isHydrated}
							onClick={onProvisionStorage}
							className="mt-5 inline-flex items-center gap-2 rounded-xl bg-[#00e599] px-4 py-2 text-sm font-bold text-[#0a1418] shadow-[0_0_12px_rgba(0,229,153,0.3)] hover:bg-[#00c985] transition"
						>
							<Plus className="h-4 w-4" />
							Provision Storage Bucket
						</HydratedButton>
					</div>
				) : (
					<div className="pt-6 space-y-6">
						{/* Upload Section / Dropzone */}
						<div
							onDragOver={(e) => {
								e.preventDefault();
								setIsDraggingOver(true);
							}}
							onDragLeave={() => setIsDraggingOver(false)}
							onDrop={handleDrop}
							className={`rounded-2xl border-2 border-dashed p-6 text-center transition ${
								isDraggingOver
									? "border-[#00e599] bg-[rgba(0,229,153,0.08)]"
									: uploadFile
										? "border-[#00e599]/60 bg-[rgba(0,229,153,0.03)]"
										: "border-[var(--line)] bg-[var(--surface-strong)]/50 hover:border-[#00e599]/40"
							}`}
						>
							<input
								type="file"
								ref={fileInputRef}
								onChange={(e) => {
									if (e.target.files && e.target.files.length > 0) {
										const file = e.target.files[0];
										setUploadFile(file);
										if (!customUploadKey) {
											setCustomUploadKey(file.name);
										}
									}
								}}
								className="hidden"
							/>

							{uploadFile ? (
								<div className="space-y-4 max-w-lg mx-auto">
									<div className="flex items-center justify-center gap-2 text-sm font-semibold text-[var(--sea-ink)]">
										<FileText className="h-5 w-5 text-[#00e599]" />
										<span>{uploadFile.name}</span>
										<span className="text-xs text-[var(--sea-ink-soft)] font-mono">
											({formatBytes(uploadFile.size)})
										</span>
									</div>

									<div>
										<label className="block text-xs font-bold uppercase tracking-wider text-[var(--sea-ink-soft)] mb-1 text-left">
											Object Key / Path
										</label>
										<input
											type="text"
											value={customUploadKey}
											onChange={(e) => setCustomUploadKey(e.target.value)}
											placeholder="e.g. images/photo.png"
											className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3.5 py-2 font-mono text-xs text-[var(--sea-ink)] focus:border-[#00e599] focus:outline-hidden"
										/>
									</div>

									<div className="flex items-center justify-center gap-3">
										<HydratedButton
											isHydrated={isHydrated}
											onClick={() => {
												setUploadFile(null);
												setCustomUploadKey("");
												if (fileInputRef.current)
													fileInputRef.current.value = "";
											}}
											className="rounded-xl border border-[var(--line)] px-4 py-2 text-xs font-semibold text-[var(--sea-ink-soft)] hover:bg-[var(--chip-bg)]"
										>
											Cancel
										</HydratedButton>
										<HydratedButton
											isHydrated={isHydrated}
											disabled={isUploadingObject}
											onClick={() => handleUploadObject()}
											className="inline-flex items-center gap-2 rounded-xl bg-[#00e599] px-5 py-2 text-xs font-bold text-[#0a1418] shadow-[0_0_12px_rgba(0,229,153,0.3)] hover:bg-[#00c985] disabled:opacity-50 transition"
										>
											{isUploadingObject ? (
												<>
													<Loader2 className="h-3.5 w-3.5 animate-spin" />
													Uploading...
												</>
											) : (
												<>
													<Upload className="h-3.5 w-3.5" />
													Upload Object
												</>
											)}
										</HydratedButton>
									</div>
								</div>
							) : (
								<div className="space-y-3">
									<div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-[rgba(0,229,153,0.1)] text-[#009b67] dark:text-[#00e599]">
										<FileUp className="h-6 w-6" />
									</div>
									<div>
										<p className="text-sm font-semibold text-[var(--sea-ink)] m-0">
											Drag and drop a file here, or{" "}
											<HydratedButton
												isHydrated={isHydrated}
												onClick={() => fileInputRef.current?.click()}
												className="text-[#009b67] dark:text-[#00e599] font-bold hover:underline bg-transparent border-none p-0 inline"
											>
												browse your files
											</HydratedButton>
										</p>
										<p className="text-xs text-[var(--sea-ink-soft)] m-0 mt-1">
											Upload images, documents, or data files directly into your
											provisioned S3 bucket.
										</p>
									</div>
								</div>
							)}
						</div>

						{/* Upload Success Alert */}
						{uploadSuccessMessage && (
							<div className="rounded-xl border border-[rgba(0,229,153,0.3)] bg-[rgba(0,229,153,0.08)] p-3 text-xs text-[#009b67] dark:text-[#00e599] font-medium flex items-center gap-2 animate-in fade-in">
								<CheckCircle2 className="h-4 w-4 shrink-0" />
								<span>{uploadSuccessMessage}</span>
							</div>
						)}

						{/* Object Browser Error Alert */}
						{objectBrowserError && (
							<div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-500 font-medium flex items-center gap-2 animate-in fade-in">
								<AlertTriangle className="h-4 w-4 shrink-0" />
								<span>{objectBrowserError}</span>
							</div>
						)}

						{/* Objects List Table */}
						<div className="space-y-3">
							<div className="flex items-center justify-between text-xs text-[var(--sea-ink-soft)] px-1">
								<span className="font-semibold uppercase tracking-wider text-[11px]">
									Stored Objects ({bucketObjects.length})
								</span>
								{bucketObjects.length > 0 && (
									<span>
										Total Size:{" "}
										<strong className="text-[var(--sea-ink)]">
											{formatBytes(
												bucketObjects.reduce((acc, o) => acc + o.size, 0),
											)}
										</strong>
									</span>
								)}
							</div>

							{isLoadingObjects ? (
								<div className="py-12 text-center text-sm text-[var(--sea-ink-soft)] flex items-center justify-center gap-2">
									<Loader2 className="h-4 w-4 animate-spin text-[#00e599]" />
									<span>Loading bucket contents...</span>
								</div>
							) : bucketObjects.length === 0 ? (
								<div className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] py-12 text-center">
									<FolderTree className="h-8 w-8 mx-auto mb-2 text-[var(--sea-ink-soft)]/50" />
									<h4 className="text-sm font-bold text-[var(--sea-ink)] m-0">
										Bucket is empty
									</h4>
									<p className="mt-1 text-xs text-[var(--sea-ink-soft)]">
										No objects found in this bucket. Drop or select a file above
										to upload.
									</p>
								</div>
							) : (
								<div className="overflow-x-auto rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] shadow-xs">
									<table className="w-full text-left text-xs border-collapse">
										<thead className="bg-[var(--foam)] border-b border-[var(--line)]">
											<tr>
												<th className="px-4 py-3 font-mono font-bold uppercase tracking-wider text-[var(--sea-ink)]">
													Key / Name
												</th>
												<th className="px-4 py-3 font-mono font-bold uppercase tracking-wider text-[var(--sea-ink)]">
													Size
												</th>
												<th className="px-4 py-3 font-mono font-bold uppercase tracking-wider text-[var(--sea-ink)]">
													Last Modified
												</th>
												<th className="px-4 py-3 font-mono font-bold uppercase tracking-wider text-[var(--sea-ink)]">
													ETag
												</th>
												<th className="px-4 py-3 font-mono font-bold uppercase tracking-wider text-[var(--sea-ink)] text-right">
													Actions
												</th>
											</tr>
										</thead>
										<tbody className="divide-y divide-[var(--line)]">
											{bucketObjects.map((obj) => (
												<tr
													key={obj.key}
													className="transition hover:bg-[rgba(0,229,153,0.04)]"
												>
													<td className="px-4 py-3 font-mono font-medium text-[var(--sea-ink)] whitespace-nowrap">
														<div className="flex items-center gap-2">
															<FileText className="h-4 w-4 text-[var(--palm)] shrink-0" />
															<span>{obj.key}</span>
														</div>
													</td>
													<td className="px-4 py-3 font-mono text-[var(--sea-ink-soft)] whitespace-nowrap">
														{formatBytes(obj.size)}
													</td>
													<td className="px-4 py-3 text-[var(--sea-ink-soft)] whitespace-nowrap">
														{obj.lastModified
															? new Date(obj.lastModified).toLocaleString()
															: "—"}
													</td>
													<td className="px-4 py-3 font-mono text-[11px] text-[var(--sea-ink-soft)] whitespace-nowrap max-w-[140px] truncate">
														{obj.etag || "—"}
													</td>
													<td className="px-4 py-3 text-right whitespace-nowrap">
														<div className="flex items-center justify-end gap-1.5">
															<HydratedButton
																isHydrated={isHydrated}
																disabled={downloadingKey === obj.key}
																onClick={() => handleDownloadObject(obj.key)}
																title="Download object"
																className="inline-flex items-center gap-1 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2.5 py-1 text-xs font-semibold text-[var(--sea-ink)] hover:bg-[var(--chip-bg)] hover:text-[#00e599] transition"
															>
																{downloadingKey === obj.key ? (
																	<Loader2 className="h-3.5 w-3.5 animate-spin" />
																) : (
																	<Download className="h-3.5 w-3.5" />
																)}
																<span>Download</span>
															</HydratedButton>
															<HydratedButton
																isHydrated={isHydrated}
																disabled={deletingKey === obj.key}
																onClick={() => handleDeleteObject(obj.key)}
																title="Delete object"
																className="inline-flex items-center gap-1 rounded-lg border border-red-500/20 bg-red-500/5 px-2.5 py-1 text-xs font-semibold text-red-500 hover:bg-red-500/10 hover:border-red-500/40 transition"
															>
																{deletingKey === obj.key ? (
																	<Loader2 className="h-3.5 w-3.5 animate-spin" />
																) : (
																	<Trash2 className="h-3.5 w-3.5" />
																)}
																<span>Delete</span>
															</HydratedButton>
														</div>
													</td>
												</tr>
											))}
										</tbody>
									</table>
								</div>
							)}
						</div>
					</div>
				)}
			</div>
		</div>
	);
}

export default ObjectBrowserPanel;
