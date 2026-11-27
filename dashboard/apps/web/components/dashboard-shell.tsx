"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Check,
  ChevronDown,
  Image as ImageIcon,
  Layers,
  PenLine,
  Plus,
  RefreshCw,
  Search,
  Server,
  X,
  Zap,
} from "lucide-react";
import { useDashboard } from "@/components/dashboard-provider";

export function DashboardShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const {
    loading,
    autoRefresh,
    setAutoRefresh,
    searchQuery,
    setSearchQuery,
    selectedProfile,
    selectProfile,
    profiles,
    version,
    dashboardCommit,
    apps,
    sandboxes,
    snapshots,
    scratchpadCatalog,
    refreshAll,
    openFreshLaunchModal,
  } = useDashboard();

  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const profileMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function handleOutsideClick(evt: MouseEvent) {
      if (
        profileMenuRef.current &&
        !profileMenuRef.current.contains(evt.target as Node)
      ) {
        setProfileMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, []);

  const runningCount = sandboxes.filter((s) => s.running).length;
  const scratchpadCount =
    (scratchpadCatalog.ideas?.length ?? 0) + (scratchpadCatalog.raw?.length ?? 0);

  const navItems = [
    { href: "/", label: "Builder", count: apps.length, Icon: Zap, id: "nav-tab-builder" },
    {
      href: "/sandboxes",
      label: "Sandboxes",
      count: runningCount,
      Icon: Server,
      id: "nav-tab-sandboxes",
    },
    {
      href: "/snapshots",
      label: "Snapshots",
      count: snapshots.length,
      Icon: ImageIcon,
      id: "nav-tab-snapshots",
    },
    {
      href: "/scratchpad",
      label: "Scratchpad",
      count: scratchpadCount,
      Icon: PenLine,
      id: "nav-tab-scratchpad",
    },
  ];

  return (
    <div className="min-h-screen flex flex-col bg-canvas text-ink overflow-x-hidden">
      <header className="border-b border-hairline bg-surface-soft/90 backdrop-blur sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8 py-2.5 sm:py-0 sm:min-h-16 flex flex-wrap items-center justify-between gap-2.5">
          <div className="flex items-center gap-2.5 sm:gap-3 min-w-0">
            <Link
              href="/"
              className="h-8 w-8 sm:h-9 sm:w-9 rounded-lg bg-primary flex-shrink-0 flex items-center justify-center font-bold text-on-primary shadow-sm"
            >
              <Layers className="w-4 h-4 sm:w-5 sm:h-5" />
            </Link>
            <div className="min-w-0">
              <h1 className="text-sm sm:text-lg font-semibold tracking-tight text-ink flex flex-wrap items-center gap-1.5 sm:gap-2 leading-tight">
                <span className="truncate">Sandbox Web Dashboard</span>
                <span className="hidden sm:inline-flex text-xs px-2 py-0.5 rounded-full bg-primary/15 text-primary-active font-mono">
                  Control Plane
                </span>
                {version &&
                  version.commit_short &&
                  version.commit_short !== "unknown" && (
                    <span
                      title={`Control Plane Ref: ${version.ref} | Commit: ${version.commit}`}
                      className="text-[11px] px-1.5 sm:px-2 py-0.5 rounded-full bg-surface-card text-muted font-mono border border-hairline"
                    >
                      CP {version.commit_short}
                      {version.dirty ? "*" : ""}
                    </span>
                  )}
                {dashboardCommit && dashboardCommit !== "unknown" && (
                  <span
                    title={`Dashboard Commit: ${dashboardCommit}`}
                    className="text-[11px] px-1.5 sm:px-2 py-0.5 rounded-full bg-surface-card text-muted font-mono border border-hairline"
                  >
                    UI {dashboardCommit.slice(0, 7)}
                  </span>
                )}
              </h1>
            </div>
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto justify-between sm:justify-end">
            <div ref={profileMenuRef} className="relative flex-1 sm:flex-initial min-w-0">
              <button
                type="button"
                onClick={() => setProfileMenuOpen((v) => !v)}
                className="flex items-center justify-between sm:justify-start gap-2 w-full sm:w-auto bg-canvas hover:bg-surface-card border border-hairline px-2.5 sm:px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium text-ink transition-colors shadow-2xs min-w-0"
              >
                <span className="flex items-center gap-1.5 min-w-0 truncate">
                  <span className="w-2 h-2 rounded-full bg-success flex-shrink-0" />
                  <span className="hidden sm:inline text-muted flex-shrink-0">Profile:</span>
                  <span className="font-mono text-primary-active truncate">
                    {selectedProfile === "all" ? "All Profiles" : selectedProfile}
                  </span>
                </span>
                <ChevronDown className="w-4 h-4 text-muted flex-shrink-0" />
              </button>

              {profileMenuOpen && (
                <div className="absolute left-0 sm:left-auto sm:right-0 mt-2 w-60 max-w-[calc(100vw-1.5rem)] rounded-xl bg-canvas border border-hairline shadow-xl py-1 z-40">
                  <button
                    type="button"
                    onClick={() => {
                      selectProfile("all");
                      setProfileMenuOpen(false);
                    }}
                    className={`w-full text-left px-4 py-2 text-sm hover:bg-surface-soft flex items-center justify-between ${
                      selectedProfile === "all"
                        ? "text-primary-active font-semibold"
                        : "text-body"
                    }`}
                  >
                    <span>All Profiles</span>
                    {selectedProfile === "all" && <Check className="w-4 h-4 text-primary" />}
                  </button>
                  <div className="border-t border-hairline my-1" />
                  {profiles.map((p) => (
                    <button
                      key={p.name}
                      type="button"
                      onClick={() => {
                        selectProfile(p.name);
                        setProfileMenuOpen(false);
                      }}
                      className={`w-full text-left px-4 py-2 text-sm hover:bg-surface-soft flex items-center justify-between gap-2 ${
                        selectedProfile === p.name
                          ? "text-primary-active font-semibold"
                          : "text-body"
                      }`}
                    >
                      <span className="font-mono flex items-center gap-1.5 min-w-0 truncate">
                        <span className="truncate">{p.name}</span>
                        {p.active && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-success/15 text-success font-mono flex-shrink-0">
                            active
                          </span>
                        )}
                      </span>
                      {selectedProfile === p.name && (
                        <Check className="w-4 h-4 text-primary flex-shrink-0" />
                      )}
                    </button>
                  ))}
                  {profiles.length === 0 && (
                    <div className="px-4 py-2 text-xs text-muted italic">
                      No profiles configured
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                type="button"
                onClick={() => setAutoRefresh(!autoRefresh)}
                aria-pressed={autoRefresh}
                className={`sm:hidden inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-medium transition-colors ${
                  autoRefresh
                    ? "bg-success/15 border-success/40 text-ink"
                    : "bg-canvas border-hairline text-muted"
                }`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    autoRefresh ? "bg-success animate-pulse" : "bg-muted-soft"
                  }`}
                />
                <span>5s</span>
              </button>

              <label className="hidden sm:flex items-center gap-2 text-xs text-muted cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                  className="rounded border-hairline text-primary focus:ring-0"
                />
                <span>Auto-refresh (5s)</span>
              </label>

              <button
                type="button"
                disabled={loading}
                onClick={() => void refreshAll()}
                aria-label="Refresh"
                className="inline-flex items-center px-2.5 sm:px-3 py-1.5 rounded-lg bg-canvas hover:bg-surface-card border border-hairline text-xs sm:text-sm font-medium text-ink transition-colors disabled:opacity-50"
              >
                <RefreshCw
                  className={`w-4 h-4 sm:mr-1.5 ${loading ? "animate-spin text-primary" : ""}`}
                />
                <span className="hidden sm:inline">Refresh</span>
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto px-3 sm:px-6 lg:px-8 py-4 sm:py-8">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 sm:gap-4 mb-5 sm:mb-6">
          <nav className="grid grid-cols-2 sm:inline-flex gap-1.5 sm:gap-1.5 bg-surface-soft p-1.5 sm:p-1 rounded-xl border border-hairline w-full lg:w-auto">
            {navItems.map(({ href, label, count, Icon, id }) => {
              const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
              return (
                <Link
                  key={href}
                  id={id}
                  href={href}
                  className={`px-3 sm:px-4 py-2 rounded-lg text-xs sm:text-sm font-medium transition-all flex items-center justify-center sm:justify-start gap-1.5 min-w-0 ${
                    active
                      ? "bg-primary text-on-primary shadow-xs"
                      : "text-muted hover:text-ink hover:bg-surface-card/60"
                  }`}
                >
                  <Icon className="w-4 h-4 flex-shrink-0" />
                  <span className="truncate">{label}</span>
                  <span
                    className={`ml-0.5 px-1.5 sm:px-2 py-0.5 text-[11px] sm:text-xs rounded-full flex-shrink-0 ${
                      active
                        ? "bg-on-primary/20 text-on-primary"
                        : "bg-surface-card text-muted"
                    }`}
                  >
                    {count}
                  </span>
                </Link>
              );
            })}
          </nav>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5 sm:gap-3 w-full lg:w-auto">
            <div className="relative w-full sm:w-64">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-soft pointer-events-none" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Filter apps, IDs, profiles..."
                className="w-full bg-surface-soft border border-hairline rounded-lg pl-9 pr-8 py-2 text-base sm:text-sm text-ink placeholder:text-muted-soft focus:outline-none focus:border-primary"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  aria-label="Clear filter"
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted hover:text-ink p-0.5"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {pathname.startsWith("/sandboxes") && (
              <button
                type="button"
                onClick={openFreshLaunchModal}
                className="inline-flex items-center justify-center px-3.5 py-2.5 sm:py-2 rounded-lg bg-primary hover:bg-primary-active text-on-primary text-sm font-medium transition-colors shadow-xs flex-shrink-0"
              >
                <Plus className="w-4 h-4 mr-1.5" />
                <span>Launch Sandbox</span>
              </button>
            )}
          </div>
        </div>

        {children}
      </main>
    </div>
  );
}
