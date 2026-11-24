import type React from "react";
import { useState, useEffect } from "react";
import {
	Terminal,
	Plus,
	Play,
	Loader2,
	CheckCircle2,
	Clock,
	Table,
	AlertTriangle,
} from "lucide-react";
import { executeSqlQueryFn } from "@/app/actions";
import type { SqlExecutionResult } from "@/services/scratchpad";
import type { DatabaseCredentials } from "@/lib/database-helpers";
import { HydratedButton } from "./HydratedButton";

export interface SqlScratchpadPanelProps {
	databases: DatabaseCredentials[];
	onProvisionDatabase: () => void;
	isHydrated?: boolean;
}

export function SqlScratchpadPanel({
	databases,
	onProvisionDatabase,
	isHydrated = true,
}: SqlScratchpadPanelProps) {
	const [scratchpadDbId, setScratchpadDbId] = useState<string>(
		databases[0]?.id || "",
	);
	const [sqlQuery, setSqlQuery] = useState<string>(
		"SELECT NOW() AS current_time, version() AS pg_version;",
	);
	const [isRunningSql, setIsRunningSql] = useState(false);
	const [sqlResult, setSqlResult] = useState<SqlExecutionResult | null>(null);
	const [sqlError, setSqlError] = useState<string | null>(null);

	useEffect(() => {
		if (!scratchpadDbId && databases.length > 0) {
			setScratchpadDbId(databases[0].id);
		}
	}, [databases, scratchpadDbId]);

	const handleRunSql = async () => {
		if (!isHydrated) return;
		if (!scratchpadDbId) {
			setSqlError("Please select a database to execute the query against.");
			return;
		}
		if (!sqlQuery.trim()) {
			setSqlError("Query cannot be empty.");
			return;
		}

		setIsRunningSql(true);
		setSqlError(null);

		try {
			const result = await executeSqlQueryFn({
				data: {
					databaseId: scratchpadDbId,
					query: sqlQuery.trim(),
				},
			});
			setSqlResult(result);
		} catch (err: any) {
			setSqlError(err.message || "Failed to execute SQL query");
			setSqlResult(null);
		} finally {
			setIsRunningSql(false);
		}
	};

	const handleSqlKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
		if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
			e.preventDefault();
			handleRunSql();
		}
	};

	return (
		<div className="space-y-6">
			<div className="island-shell rounded-2xl p-6 sm:p-8">
				<div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-6 border-b border-[var(--line)] gap-4">
					<div>
						<h3 className="text-lg font-bold text-[var(--sea-ink)] m-0">
							SQL Scratchpad
						</h3>
						<p className="text-sm text-[var(--sea-ink-soft)] m-0 mt-1">
							Execute interactive SQL queries directly against any provisioned
							database in this project.
						</p>
					</div>
					{databases.length > 0 && (
						<div className="flex items-center gap-2">
							<label className="text-xs font-semibold text-[var(--sea-ink-soft)] whitespace-nowrap">
								Database:
							</label>
							<select
								value={scratchpadDbId}
								disabled={!isHydrated}
								onChange={(e) => {
									setScratchpadDbId(e.target.value);
									setSqlError(null);
								}}
								className={`rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-xs font-mono font-semibold text-[var(--sea-ink)] focus:border-[#00e599] focus:outline-hidden ${
									!isHydrated ? "opacity-75 cursor-wait" : "cursor-pointer"
								}`}
							>
								{databases.map((db) => (
									<option key={db.id} value={db.id}>
										{db.name} ({db.username})
									</option>
								))}
							</select>
						</div>
					)}
				</div>

				{databases.length === 0 ? (
					<div className="py-14 text-center">
						<div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-[rgba(0,229,153,0.12)] border border-[rgba(0,229,153,0.25)] text-[#009b67] dark:text-[#00e599]">
							<Terminal className="h-7 w-7" />
						</div>
						<h4 className="text-base font-bold text-[var(--sea-ink)] m-0">
							No databases provisioned
						</h4>
						<p className="mx-auto mt-2 max-w-sm text-sm text-[var(--sea-ink-soft)]">
							Provision a PostgreSQL database first to compose and test SQL
							queries in the Scratchpad.
						</p>
						<HydratedButton
							isHydrated={isHydrated}
							onClick={onProvisionDatabase}
							className="mt-5 inline-flex items-center gap-2 rounded-xl bg-[#00e599] px-4 py-2 text-sm font-bold text-[#0a1418] shadow-[0_0_12px_rgba(0,229,153,0.3)] hover:bg-[#00c985] transition"
						>
							<Plus className="h-4 w-4" />
							Provision Database
						</HydratedButton>
					</div>
				) : (
					<div className="pt-6 space-y-5">
						{/* Query Templates Bar */}
						<div className="flex flex-wrap items-center gap-2">
							<span className="text-xs font-bold uppercase tracking-wider text-[var(--sea-ink-soft)] mr-1">
								Templates:
							</span>
							<HydratedButton
								isHydrated={isHydrated}
								onClick={() =>
									setSqlQuery(
										"SELECT NOW() AS current_time, version() AS pg_version;",
									)
								}
								className="rounded-lg border border-[var(--line)] bg-[var(--foam)] px-2.5 py-1 text-xs font-mono text-[var(--sea-ink)] hover:border-[#00e599]/50 hover:bg-[var(--chip-bg)] transition"
							>
								SELECT NOW()
							</HydratedButton>
							<HydratedButton
								isHydrated={isHydrated}
								onClick={() =>
									setSqlQuery(
										"SELECT table_name, table_type FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;",
									)
								}
								className="rounded-lg border border-[var(--line)] bg-[var(--foam)] px-2.5 py-1 text-xs font-mono text-[var(--sea-ink)] hover:border-[#00e599]/50 hover:bg-[var(--chip-bg)] transition"
							>
								List Tables
							</HydratedButton>
							<HydratedButton
								isHydrated={isHydrated}
								onClick={() =>
									setSqlQuery(
										"CREATE TABLE IF NOT EXISTS demo_notes (\n  id SERIAL PRIMARY KEY,\n  title TEXT NOT NULL,\n  status TEXT DEFAULT 'active',\n  created_at TIMESTAMPTZ DEFAULT NOW()\n);",
									)
								}
								className="rounded-lg border border-[var(--line)] bg-[var(--foam)] px-2.5 py-1 text-xs font-mono text-[var(--sea-ink)] hover:border-[#00e599]/50 hover:bg-[var(--chip-bg)] transition"
							>
								Create Table
							</HydratedButton>
							<HydratedButton
								isHydrated={isHydrated}
								onClick={() =>
									setSqlQuery(
										"INSERT INTO demo_notes (title, status) VALUES ('Interactive Scratchpad', 'verified') RETURNING *;",
									)
								}
								className="rounded-lg border border-[var(--line)] bg-[var(--foam)] px-2.5 py-1 text-xs font-mono text-[var(--sea-ink)] hover:border-[#00e599]/50 hover:bg-[var(--chip-bg)] transition"
							>
								Insert & Return
							</HydratedButton>
							<HydratedButton
								isHydrated={isHydrated}
								onClick={() =>
									setSqlQuery(
										"SELECT * FROM demo_notes ORDER BY id DESC LIMIT 50;",
									)
								}
								className="rounded-lg border border-[var(--line)] bg-[var(--foam)] px-2.5 py-1 text-xs font-mono text-[var(--sea-ink)] hover:border-[#00e599]/50 hover:bg-[var(--chip-bg)] transition"
							>
								Query Items
							</HydratedButton>
						</div>

						{/* SQL Query Editor Textarea */}
						<div className="relative rounded-xl border border-[var(--line)] bg-[#071013] shadow-inner focus-within:border-[#00e599] transition">
							<textarea
								rows={6}
								value={sqlQuery}
								onChange={(e) => setSqlQuery(e.target.value)}
								onKeyDown={handleSqlKeyDown}
								placeholder="Type your SQL query here... (e.g. SELECT * FROM my_table;)"
								className="w-full bg-transparent p-4 font-mono text-sm text-[#e7f3ec] placeholder-[#e7f3ec]/40 focus:outline-hidden resize-y min-h-[140px]"
							/>

							{/* Toolbar inside editor bottom */}
							<div className="flex flex-wrap items-center justify-between border-t border-[var(--line)]/40 bg-[#0a161b] px-4 py-2.5 rounded-b-xl gap-3">
								<div className="flex items-center gap-2 text-xs text-[var(--sea-ink-soft)]">
									<span className="inline-flex items-center gap-1 font-mono text-[11px] bg-[rgba(255,255,255,0.08)] px-2 py-0.5 rounded-md border border-[rgba(255,255,255,0.12)]">
										⌘/Ctrl + Enter to run
									</span>
								</div>

								<div className="flex items-center gap-2">
									<HydratedButton
										isHydrated={isHydrated}
										onClick={() => {
											setSqlQuery("");
											setSqlResult(null);
											setSqlError(null);
										}}
										className="rounded-lg px-3 py-1.5 text-xs font-semibold text-[var(--sea-ink-soft)] hover:text-[var(--sea-ink)] transition"
									>
										Clear
									</HydratedButton>
									<HydratedButton
										isHydrated={isHydrated}
										disabled={isRunningSql || !sqlQuery.trim()}
										onClick={handleRunSql}
										className="inline-flex items-center gap-2 rounded-xl bg-[#00e599] px-4 py-1.5 text-xs font-bold text-[#0a1418] shadow-[0_0_12px_rgba(0,229,153,0.3)] hover:bg-[#00c985] disabled:opacity-50 transition"
									>
										{isRunningSql ? (
											<>
												<Loader2 className="h-3.5 w-3.5 animate-spin" />
												Executing...
											</>
										) : (
											<>
												<Play className="h-3.5 w-3.5 fill-current" />
												Run Query
											</>
										)}
									</HydratedButton>
								</div>
							</div>
						</div>

						{/* Error Banner */}
						{sqlError && (
							<div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-xs text-red-500 flex items-start gap-3 animate-in fade-in">
								<AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
								<div className="space-y-1">
									<p className="font-bold m-0">Query Error</p>
									<pre className="m-0 font-mono text-xs whitespace-pre-wrap break-all text-red-400">
										{sqlError}
									</pre>
								</div>
							</div>
						)}

						{/* Results Section */}
						{sqlResult && (
							<div className="space-y-3 animate-in fade-in">
								{/* Metrics Header */}
								<div className="flex flex-wrap items-center justify-between rounded-xl border border-[var(--line)] bg-[var(--foam)] px-4 py-2.5 text-xs text-[var(--sea-ink-soft)] gap-2">
									<div className="flex items-center gap-3">
										<span className="inline-flex items-center gap-1 font-semibold text-[#009b67] dark:text-[#00e599]">
											<CheckCircle2 className="h-3.5 w-3.5" />
											Success
										</span>
										<span>•</span>
										<span className="inline-flex items-center gap-1">
											<Clock className="h-3.5 w-3.5 text-[var(--lagoon-deep)]" />
											{sqlResult.executionTimeMs} ms
										</span>
										<span>•</span>
										<span className="inline-flex items-center gap-1">
											<Table className="h-3.5 w-3.5 text-[var(--palm)]" />
											{sqlResult.rowCount}{" "}
											{sqlResult.rowCount === 1 ? "row" : "rows"}
										</span>
									</div>
									<span className="font-mono text-[11px] text-[var(--sea-ink-soft)]">
										{sqlResult.columns.length}{" "}
										{sqlResult.columns.length === 1 ? "column" : "columns"}
									</span>
								</div>

								{/* Results Table */}
								{sqlResult.columns.length > 0 ? (
									<div className="overflow-x-auto rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] shadow-xs max-h-[480px] overflow-y-auto">
										<table className="w-full text-left text-xs border-collapse">
											<thead className="sticky top-0 bg-[var(--foam)] border-b border-[var(--line)] z-10">
												<tr>
													{sqlResult.columns.map((col, idx) => (
														<th
															key={idx}
															className="px-4 py-3 font-mono font-bold uppercase tracking-wider text-[var(--sea-ink)] whitespace-nowrap"
														>
															{col}
														</th>
													))}
												</tr>
											</thead>
											<tbody className="divide-y divide-[var(--line)]">
												{sqlResult.rows.length === 0 ? (
													<tr>
														<td
															colSpan={sqlResult.columns.length}
															className="px-4 py-8 text-center text-[var(--sea-ink-soft)]"
														>
															Query returned 0 rows
														</td>
													</tr>
												) : (
													sqlResult.rows.map((row, rIdx) => (
														<tr
															key={rIdx}
															className="transition hover:bg-[rgba(0,229,153,0.04)]"
														>
															{sqlResult.columns.map((col, cIdx) => {
																const val = row[col];
																return (
																	<td
																		key={cIdx}
																		className="px-4 py-2.5 font-mono text-[var(--sea-ink)] whitespace-nowrap align-top"
																	>
																		{val === null || val === undefined ? (
																			<span className="italic text-[var(--sea-ink-soft)]/50">
																				NULL
																			</span>
																		) : typeof val === "boolean" ? (
																			<span className="font-semibold text-[#009b67] dark:text-[#00e599]">
																				{String(val)}
																			</span>
																		) : typeof val === "object" ? (
																			<pre className="m-0 text-[11px] max-w-xs truncate">
																				{JSON.stringify(val)}
																			</pre>
																		) : (
																			String(val)
																		)}
																	</td>
																);
															})}
														</tr>
													))
												)}
											</tbody>
										</table>
									</div>
								) : (
									<div className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-6 text-center text-sm text-[var(--sea-ink-soft)]">
										Query executed successfully. {sqlResult.rowCount} row(s)
										affected in {sqlResult.executionTimeMs} ms.
									</div>
								)}
							</div>
						)}
					</div>
				)}
			</div>
		</div>
	);
}

export default SqlScratchpadPanel;
