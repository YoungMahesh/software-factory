"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition, useId } from "react";
import {
	Database,
	HardDrive,
	Plus,
	Globe,
	Calendar,
	Layers,
	ArrowRight,
	X,
	Search,
	FolderPlus,
} from "lucide-react";
import { createProjectFn } from "@/app/actions";
import type { ProjectWithStats } from "@/services/projects";
import { HydratedButton } from "@/components/HydratedButton";

function slugify(text: string): string {
	return (
		text
			.toString()
			.toLowerCase()
			.trim()
			.replace(/\s+/g, "-")
			.replace(/[^\w-]+/g, "")
			.replace(/--+/g, "-")
			.replace(/^-+/, "")
			.replace(/-+$/, "") || "project"
	);
}


const AVAILABLE_REGIONS = [
	{ id: "us-east-1", name: "US East (N. Virginia)" },
	{ id: "us-west-2", name: "US West (Oregon)" },
	{ id: "eu-central-1", name: "Europe (Frankfurt)" },
	{ id: "ap-southeast-1", name: "Asia Pacific (Singapore)" },
];

export default function DashboardHome({ initialProjects = [] }: { initialProjects?: ProjectWithStats[] }) {
	const [projects, setProjects] = useState<ProjectWithStats[]>(initialProjects);
	const router = useRouter();
	const [isPending, startTransition] = useTransition();

	// Modal State
	const [isModalOpen, setIsModalOpen] = useState(false);
	const [name, setName] = useState("");
	const [slug, setSlug] = useState("");
	const [region, setRegion] = useState("us-east-1");
	const [isCustomSlug, setIsCustomSlug] = useState(false);
	const [errorMessage, setErrorMessage] = useState<string | null>(null);
	const [searchQuery, setSearchQuery] = useState("");

	const nameInputId = useId();
	const slugInputId = useId();
	const regionSelectId = useId();

	const openModal = () => {
		setName("");
		setSlug("");
		setRegion("us-east-1");
		setIsCustomSlug(false);
		setErrorMessage(null);
		setIsModalOpen(true);
	};

	const closeModal = () => {
		setIsModalOpen(false);
		setErrorMessage(null);
	};

	const handleNameChange = (val: string) => {
		setName(val);
		if (!isCustomSlug) {
			setSlug(slugify(val));
		}
	};

	const handleSlugChange = (val: string) => {
		setIsCustomSlug(true);
		setSlug(slugify(val));
	};

	const handleCreateProject = async (e: React.FormEvent) => {
		e.preventDefault();
		if (!name.trim()) {
			setErrorMessage("Project name is required");
			return;
		}

		setErrorMessage(null);
		try {
			const created = await createProjectFn({
				name: name.trim(),
				slug: slug.trim() || undefined,
				region,
			});

			closeModal();
			startTransition(async () => {
				router.push(`/projects/${created.id}`);
				router.refresh();
			});
		} catch (err: any) {
			setErrorMessage(err.message || "Failed to create project");
		}
	};

	// Filtered projects
	const filteredProjects = projects.filter((p) => {
		if (!searchQuery.trim()) return true;
		const q = searchQuery.toLowerCase();
		return p.name.toLowerCase().includes(q) || p.slug.toLowerCase().includes(q);
	});

	// Quick stats
	const totalDatabases = projects.reduce((acc, p) => acc + p.databaseCount, 0);
	const totalStorages = projects.reduce((acc, p) => acc + p.storageCount, 0);

	return (
		<main className="page-wrap px-4 pb-16 pt-8">
			{/* Top Banner & Header */}
			<div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between mb-8">
				<div>
					<div className="flex items-center gap-2 mb-1.5">
						<span className="island-kicker">DB Host Cloud Console</span>
						<span className="h-1.5 w-1.5 rounded-full bg-[#00e599]" />
						<span className="text-xs text-[var(--sea-ink-soft)] font-medium">
							Local Control Plane
						</span>
					</div>
					<h1 className="display-title text-3xl sm:text-4xl font-bold tracking-tight text-[var(--sea-ink)] m-0">
						Projects
					</h1>
					<p className="mt-1 text-sm sm:text-base text-[var(--sea-ink-soft)] max-w-xl m-0">
						Organize and manage your isolated PostgreSQL databases and
						S3-compatible object storages.
					</p>
				</div>

				<div className="flex items-center gap-3">
					<HydratedButton
						data-testid="create-project-btn"
						onClick={openModal}
						className="inline-flex items-center gap-2 rounded-xl bg-[#00e599] px-4 py-2.5 text-sm font-bold text-[#0a1418] shadow-[0_0_16px_rgba(0,229,153,0.35)] transition hover:bg-[#00c985] hover:shadow-[0_0_24px_rgba(0,229,153,0.5)]"
					>
						<Plus className="h-4 w-4" />
						New Project
					</HydratedButton>
				</div>
			</div>

			{/* Metrics Bar */}
			{projects.length > 0 && (
				<div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
					<div className="island-shell rounded-xl p-4 flex items-center justify-between">
						<div>
							<p className="text-xs font-semibold text-[var(--sea-ink-soft)] uppercase tracking-wider m-0">
								Total Projects
							</p>
							<p className="text-2xl font-bold text-[var(--sea-ink)] m-0 mt-1">
								{projects.length}
							</p>
						</div>
						<div className="h-10 w-10 rounded-lg bg-[rgba(0,229,153,0.12)] border border-[rgba(0,229,153,0.24)] flex items-center justify-center text-[#009b67] dark:text-[#00e599]">
							<Layers className="h-5 w-5" />
						</div>
					</div>

					<div className="island-shell rounded-xl p-4 flex items-center justify-between">
						<div>
							<p className="text-xs font-semibold text-[var(--sea-ink-soft)] uppercase tracking-wider m-0">
								Postgres Databases
							</p>
							<p className="text-2xl font-bold text-[var(--sea-ink)] m-0 mt-1">
								{totalDatabases}
							</p>
						</div>
						<div className="h-10 w-10 rounded-lg bg-[rgba(79,184,178,0.14)] border border-[rgba(79,184,178,0.28)] flex items-center justify-center text-[var(--lagoon-deep)]">
							<Database className="h-5 w-5" />
						</div>
					</div>

					<div className="island-shell rounded-xl p-4 flex items-center justify-between">
						<div>
							<p className="text-xs font-semibold text-[var(--sea-ink-soft)] uppercase tracking-wider m-0">
								S3 Object Storages
							</p>
							<p className="text-2xl font-bold text-[var(--sea-ink)] m-0 mt-1">
								{totalStorages}
							</p>
						</div>
						<div className="h-10 w-10 rounded-lg bg-[rgba(47,106,74,0.14)] border border-[rgba(47,106,74,0.28)] flex items-center justify-center text-[var(--palm)]">
							<HardDrive className="h-5 w-5" />
						</div>
					</div>
				</div>
			)}

			{/* Projects Search and Count */}
			{projects.length > 0 && (
				<div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
					<div className="relative w-full sm:w-72">
						<Search className="absolute left-3 top-2.5 h-4 w-4 text-[var(--sea-ink-soft)]" />
						<input
							type="text"
							placeholder="Search projects..."
							value={searchQuery}
							onChange={(e) => setSearchQuery(e.target.value)}
							className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface)] pl-9 pr-4 py-2 text-sm text-[var(--sea-ink)] placeholder-[var(--sea-ink-soft)] focus:outline-none focus:border-[#00e599] focus:ring-1 focus:ring-[#00e599]"
						/>
					</div>
					<span className="text-xs text-[var(--sea-ink-soft)]">
						Showing {filteredProjects.length} of {projects.length} project(s)
					</span>
				</div>
			)}

			{/* Projects Cards Grid */}
			{filteredProjects.length > 0 ? (
				<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
					{filteredProjects.map((project) => (
						<ProjectCard key={project.id} project={project} />
					))}
				</div>
			) : projects.length > 0 ? (
				<div className="island-shell rounded-2xl p-12 text-center">
					<p className="text-sm text-[var(--sea-ink-soft)] m-0">
						No projects match &ldquo;{searchQuery}&rdquo;.
					</p>
				</div>
			) : (
				/* Empty State */
				<div
					data-testid="empty-projects-state"
					className="island-shell rise-in rounded-2xl p-10 sm:p-14 text-center border border-[var(--line)]"
				>
					<div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-[rgba(0,229,153,0.12)] border border-[rgba(0,229,153,0.3)] text-[#009b67] dark:text-[#00e599] shadow-[0_0_24px_rgba(0,229,153,0.2)]">
						<FolderPlus className="h-8 w-8" />
					</div>
					<h2 className="text-xl sm:text-2xl font-bold text-[var(--sea-ink)] m-0">
						No projects yet
					</h2>
					<p className="mx-auto mt-2 max-w-md text-sm sm:text-base text-[var(--sea-ink-soft)]">
						Create your first project to start provisioning isolated PostgreSQL
						databases and S3 object storages with dedicated credentials.
					</p>
					<HydratedButton
						onClick={openModal}
						className="mt-6 inline-flex items-center gap-2 rounded-xl bg-[#00e599] px-5 py-3 text-sm font-bold text-[#0a1418] shadow-[0_0_20px_rgba(0,229,153,0.35)] transition hover:bg-[#00c985]"
					>
						<Plus className="h-4 w-4" />
						Create Your First Project
					</HydratedButton>
				</div>
			)}

			{/* Create Project Modal */}
			{isModalOpen && (
				<div
					role="dialog"
					aria-modal="true"
					className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
				>
					<div className="island-shell rounded-2xl max-w-md w-full p-6 border border-[var(--line)] shadow-2xl relative">
						<div className="flex items-center justify-between pb-4 border-b border-[var(--line)] mb-5">
							<div>
								<h3 className="text-lg font-bold text-[var(--sea-ink)] m-0">
									Create New Project
								</h3>
								<p className="text-xs text-[var(--sea-ink-soft)] m-0 mt-0.5">
									Organize your databases and S3 buckets in a project.
								</p>
							</div>
							<button
								type="button"
								onClick={closeModal}
								className="rounded-lg p-1.5 text-[var(--sea-ink-soft)] hover:text-[var(--sea-ink)] hover:bg-[var(--line)] transition"
							>
								<X className="h-5 w-5" />
							</button>
						</div>

						{errorMessage && (
							<div className="mb-4 rounded-xl border border-rose-500/30 bg-rose-500/10 px-3.5 py-2.5 text-xs text-rose-500 font-medium">
								{errorMessage}
							</div>
						)}

						<form onSubmit={handleCreateProject} className="space-y-4">
							<div>
								<label
									htmlFor={nameInputId}
									className="block text-xs font-bold uppercase tracking-wider text-[var(--sea-ink-soft)] mb-1.5"
								>
									Project Name <span className="text-rose-500">*</span>
								</label>
								<input
									id={nameInputId}
									type="text"
									required
									autoFocus
									placeholder="e.g. Acme Production"
									value={name}
									onChange={(e) => handleNameChange(e.target.value)}
									className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3.5 py-2.5 text-sm text-[var(--sea-ink)] placeholder-[var(--sea-ink-soft)] focus:outline-none focus:border-[#00e599] focus:ring-1 focus:ring-[#00e599]"
								/>
							</div>

							<div>
								<label
									htmlFor={slugInputId}
									className="block text-xs font-bold uppercase tracking-wider text-[var(--sea-ink-soft)] mb-1.5"
								>
									Project Slug
								</label>
								<input
									id={slugInputId}
									type="text"
									placeholder="acme-production"
									value={slug}
									onChange={(e) => handleSlugChange(e.target.value)}
									className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3.5 py-2.5 font-mono text-sm text-[var(--sea-ink)] placeholder-[var(--sea-ink-soft)] focus:outline-none focus:border-[#00e599] focus:ring-1 focus:ring-[#00e599]"
								/>
								<p className="mt-1 text-[11px] text-[var(--sea-ink-soft)]">
									Unique identifier used in URLs and resource tags.
								</p>
							</div>

							<div>
								<label
									htmlFor={regionSelectId}
									className="block text-xs font-bold uppercase tracking-wider text-[var(--sea-ink-soft)] mb-1.5"
								>
									Region
								</label>
								<select
									id={regionSelectId}
									value={region}
									onChange={(e) => setRegion(e.target.value)}
									className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3.5 py-2.5 text-sm text-[var(--sea-ink)] focus:outline-none focus:border-[#00e599] focus:ring-1 focus:ring-[#00e599]"
								>
									{AVAILABLE_REGIONS.map((r) => (
										<option key={r.id} value={r.id}>
											{r.name} ({r.id})
										</option>
									))}
								</select>
							</div>

							<div className="flex items-center justify-end gap-3 pt-3 border-t border-[var(--line)]">
								<button
									type="button"
									onClick={closeModal}
									className="rounded-xl border border-[var(--line)] px-4 py-2.5 text-xs font-semibold text-[var(--sea-ink-soft)] hover:text-[var(--sea-ink)] hover:bg-[var(--line)] transition"
								>
									Cancel
								</button>
								<button
									type="submit"
									disabled={isPending}
									className="inline-flex items-center gap-2 rounded-xl bg-[#00e599] px-5 py-2.5 text-xs font-bold text-[#0a1418] shadow-[0_0_12px_rgba(0,229,153,0.3)] transition hover:bg-[#00c985] disabled:opacity-50 cursor-pointer"
								>
									{isPending ? "Creating..." : "Create Project"}
								</button>
							</div>
						</form>
					</div>
				</div>
			)}
		</main>
	);
}

function ProjectCard({ project }: { project: ProjectWithStats }) {
	const createdDate = new Date(project.createdAt).toLocaleDateString(
		undefined,
		{
			year: "numeric",
			month: "short",
			day: "numeric",
		},
	);

	return (
		<Link
			href={`/projects/${project.id}`}
			className="group island-shell feature-card block rounded-2xl p-5 no-underline transition-all duration-200 hover:border-[#00e599]/60 hover:shadow-[0_0_24px_rgba(0,229,153,0.14)]"
		>
			<div className="flex items-start justify-between gap-3 mb-2">
				<h3 className="text-base font-bold text-[var(--sea-ink)] group-hover:text-[#00b377] dark:group-hover:text-[#00e599] transition-colors m-0 truncate">
					{project.name}
				</h3>
				<span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-[rgba(0,229,153,0.1)] text-[#009b67] dark:text-[#00e599] border border-[rgba(0,229,153,0.25)] flex-shrink-0">
					<Globe className="h-3 w-3" />
					{project.region}
				</span>
			</div>

			<p className="font-mono text-xs text-[var(--sea-ink-soft)] mb-4 truncate m-0">
				{project.slug}
			</p>

			{/* Stats */}
			<div className="grid grid-cols-2 gap-2 py-3 border-y border-[var(--line)] text-xs text-[var(--sea-ink)] mb-3">
				<div className="flex items-center gap-2">
					<Database className="h-3.5 w-3.5 text-[var(--lagoon-deep)]" />
					<span className="font-semibold">{project.databaseCount}</span>
					<span className="text-[var(--sea-ink-soft)]">Databases</span>
				</div>
				<div className="flex items-center gap-2">
					<HardDrive className="h-3.5 w-3.5 text-[var(--palm)]" />
					<span className="font-semibold">{project.storageCount}</span>
					<span className="text-[var(--sea-ink-soft)]">Storage</span>
				</div>
			</div>

			<div className="flex items-center justify-between text-xs text-[var(--sea-ink-soft)]">
				<span className="inline-flex items-center gap-1.5">
					<Calendar className="h-3.5 w-3.5" />
					{createdDate}
				</span>
				<span className="inline-flex items-center gap-1 font-semibold text-[var(--lagoon-deep)] group-hover:text-[#00b377] dark:group-hover:text-[#00e599] transition-colors">
					Open{" "}
					<ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
				</span>
			</div>
		</Link>
	);
}
