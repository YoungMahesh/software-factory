import Link from "next/link";
import { useEffect, useState } from "react";
import type { ServicesHealth } from "../types/health";
import { getHealthStatus } from "../services/health";
import ThemeToggle from "./ThemeToggle";

export interface HeaderProps {
	initialHealth?: ServicesHealth | null;
}

export default function Header({ initialHealth = null }: HeaderProps) {
	const [health, setHealth] = useState<ServicesHealth | null>(initialHealth);

	useEffect(() => {
		let active = true;

		const fetchHealth = async () => {
			try {
				const res = await getHealthStatus();
				if (active) {
					setHealth(res);
				}
			} catch {
				// Keep prior state or handle network error
			}
		};

		if (!health) {
			fetchHealth();
		}

		const interval = setInterval(fetchHealth, 5000);
		return () => {
			active = false;
			clearInterval(interval);
		};
	}, []);

	const pgStatus = health?.postgres.status ?? "stopped";
	const swStatus = health?.seaweedfs.status ?? "stopped";

	return (
		<header className="sticky top-0 z-50 border-b border-[var(--line)] bg-[var(--header-bg)] px-4 backdrop-blur-lg">
			<nav className="page-wrap flex flex-wrap items-center gap-x-3 gap-y-2 py-3 sm:py-4">
				<h2 className="m-0 flex-shrink-0 text-base font-semibold tracking-tight">
					<Link
						href="/"
						className="inline-flex items-center gap-2 rounded-full border border-[var(--chip-line)] bg-[var(--chip-bg)] px-3 py-1.5 text-sm text-[var(--sea-ink)] no-underline shadow-[0_8px_24px_rgba(30,90,72,0.08)] sm:px-4 sm:py-2"
					>
						<span className="h-2.5 w-2.5 rounded-full bg-[#00e599] shadow-[0_0_8px_#00e599]" />
						DB Host Control Plane
					</Link>
				</h2>

				{/* Live Service Health Pills */}
				<div
					data-testid="service-health-pills"
					className="flex items-center gap-2"
				>
					{/* PostgreSQL Health Pill */}
					<div
						data-testid="postgres-health-pill"
						className="inline-flex items-center gap-1.5 rounded-full border border-[var(--chip-line)] bg-[var(--chip-bg)] px-2.5 py-1 text-xs font-medium text-[var(--sea-ink)] shadow-xs"
						title={`PostgreSQL: ${pgStatus} (Port: ${health?.postgres.port ?? 5432})`}
					>
						<span
							className={`h-2 w-2 rounded-full ${
								pgStatus === "healthy"
									? "bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.7)]"
									: pgStatus === "starting"
										? "bg-amber-400 animate-pulse"
										: "bg-rose-500"
							}`}
						/>
						<span className="font-semibold">Postgres</span>
						<span className="font-mono text-[11px] text-[var(--sea-ink-soft)]">
							{pgStatus === "healthy"
								? `:${health?.postgres.port ?? 5432}`
								: pgStatus}
						</span>
					</div>

					{/* SeaweedFS Health Pill */}
					<div
						data-testid="seaweedfs-health-pill"
						className="inline-flex items-center gap-1.5 rounded-full border border-[var(--chip-line)] bg-[var(--chip-bg)] px-2.5 py-1 text-xs font-medium text-[var(--sea-ink)] shadow-xs"
						title={`SeaweedFS S3: ${swStatus} (Port: 8333)`}
					>
						<span
							className={`h-2 w-2 rounded-full ${
								swStatus === "healthy"
									? "bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.7)]"
									: swStatus === "starting"
										? "bg-amber-400 animate-pulse"
										: "bg-rose-500"
							}`}
						/>
						<span className="font-semibold">SeaweedFS</span>
						<span className="font-mono text-[11px] text-[var(--sea-ink-soft)]">
							{swStatus === "healthy" ? ":8333" : swStatus}
						</span>
					</div>
				</div>

				<div className="order-3 flex w-full flex-wrap items-center gap-x-4 gap-y-1 pb-1 text-sm font-semibold sm:order-none sm:w-auto sm:flex-nowrap sm:pb-0">
					<Link
						href="/"
						className="nav-link"
					>
						Home
					</Link>
					<Link
						href="/about"
						className="nav-link"
					>
						About
					</Link>
				</div>

				<div className="ml-auto flex items-center gap-1.5 sm:gap-2">
					<ThemeToggle />
				</div>
			</nav>
		</header>
	);
}
