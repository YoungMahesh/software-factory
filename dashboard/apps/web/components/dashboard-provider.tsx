"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import type {
  AppTemplateKind,
  FactoryAppView,
  LaunchResponse,
  LaunchStatusResponse,
  ModelChoice,
  PrimeSandboxView,
  ProfileInfo,
  RepositoryCatalogCache,
  SandboxSummary,
  ScratchpadCatalogResponse,
  ScratchpadNoteDetailView,
  ScratchpadSection,
  SnapshotSummary,
  VersionInfo,
} from "@dashboard/types";
import { ConfirmDialog, type ConfirmOptions } from "@/components/confirm-dialog";
import { FreshSandboxModal } from "@/components/modals/fresh-sandbox-modal";
import { LaunchResultModal } from "@/components/modals/launch-result-modal";
import {
  SnapshotCreateModal,
  type SnapshotTarget,
} from "@/components/modals/snapshot-create-modal";
import {
  SnapshotLaunchModal,
  type SnapshotLaunchTarget,
} from "@/components/modals/snapshot-launch-modal";
import { ToastViewport, type ToastKind, type ToastMessage } from "@/components/toast";
import { useLaunchObserver } from "@/hooks/use-launch-observer";
import { extractApiError } from "@/lib/format";

export interface BuilderDraftState {
  prompt: string;
  name: string;
  repo: string | null;
  branch: string;
  template: AppTemplateKind;
  web_app: boolean;
  mobile_app: boolean;
  vm: boolean;
  profile: string;
  provider: string;
  model: string;
  thought_level: string;
}

const DEFAULT_MODEL: ModelChoice = {
  provider: "antigravity",
  model: "gemini-4-hydrogen",
  label: "Antigravity · Gemini 4 Hydrogen",
  is_default: true,
  thought_levels: [
    { id: "low", label: "Low" },
    { id: "medium", label: "Medium" },
    { id: "high", label: "High" },
    { id: "xhigh", label: "Extra" },
  ],
};

interface DashboardContextValue {
  loading: boolean;
  autoRefresh: boolean;
  setAutoRefresh: (value: boolean) => void;
  searchQuery: string;
  setSearchQuery: (value: string) => void;
  selectedProfile: string;
  selectProfile: (profile: string) => void;
  profiles: ProfileInfo[];
  version: VersionInfo | null;

  apps: FactoryAppView[];
  primes: PrimeSandboxView[];
  models: ModelChoice[];
  repoCatalog: RepositoryCatalogCache;
  repoRefreshing: boolean;
  sandboxes: SandboxSummary[];
  snapshots: SnapshotSummary[];

  builderDraft: BuilderDraftState;
  setBuilderDraft: React.Dispatch<React.SetStateAction<BuilderDraftState>>;
  builderSubmitting: boolean;
  activeLaunch: LaunchStatusResponse | null;
  trackLaunch: (requestId: string) => Promise<void>;
  dismissActiveLaunch: () => void;

  scratchpadCatalog: ScratchpadCatalogResponse;
  scratchpadLoaded: boolean;
  scratchpadLoading: boolean;
  selectedNotes: Record<ScratchpadSection, ScratchpadNoteDetailView | null>;
  setSelectedNotes: React.Dispatch<
    React.SetStateAction<Record<ScratchpadSection, ScratchpadNoteDetailView | null>>
  >;
  ideasDraft: { titleHint: string; rawText: string };
  setIdeasDraft: React.Dispatch<React.SetStateAction<{ titleHint: string; rawText: string }>>;
  rawDraft: { title: string; content: string };
  setRawDraft: React.Dispatch<React.SetStateAction<{ title: string; content: string }>>;

  refreshAll: (silent?: boolean) => Promise<void>;
  refreshGithubRepos: () => Promise<void>;
  fetchScratchpadNotes: () => Promise<void>;
  refreshScratchpadNotes: () => Promise<void>;
  selectScratchpadNote: (section: ScratchpadSection, filename: string) => Promise<void>;
  loadNoteIntoBuilder: (note: ScratchpadNoteDetailView) => void;

  submitAppPrompt: () => Promise<void>;
  openFactoryApp: (app: FactoryAppView) => Promise<void>;
  relaunchFactoryApp: (
    app: { app_id: string },
    opts?: { resume?: boolean },
  ) => Promise<void>;
  deleteFactoryApp: (app: FactoryAppView) => Promise<void>;
  terminateSandbox: (sb: SandboxSummary) => Promise<void>;
  deleteSnapshotRecord: (snap: SnapshotSummary) => Promise<void>;

  openFreshLaunchModal: () => void;
  openSnapshotModal: (target: SnapshotTarget) => void;
  openLaunchFromSnapshotModal: (target: SnapshotLaunchTarget) => void;
  showToast: (message: string, type?: ToastKind) => void;
}

const DashboardContext = createContext<DashboardContextValue | null>(null);

export function useDashboard(): DashboardContextValue {
  const ctx = useContext(DashboardContext);
  if (!ctx) {
    throw new Error("useDashboard must be used within DashboardProvider");
  }
  return ctx;
}

export function DashboardProvider({ children }: { children: ReactNode }) {
  const router = useRouter();

  const [loading, setLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedProfile, setSelectedProfile] = useState("all");
  const [profiles, setProfiles] = useState<ProfileInfo[]>([]);
  const [version, setVersion] = useState<VersionInfo | null>(null);

  const [apps, setApps] = useState<FactoryAppView[]>([]);
  const [primes, setPrimes] = useState<PrimeSandboxView[]>([]);
  const [models, setModels] = useState<ModelChoice[]>([DEFAULT_MODEL]);
  const [repoCatalog, setRepoCatalog] = useState<RepositoryCatalogCache>({
    org: null,
    refreshed_at: null,
    repos: [],
  });
  const [repoRefreshing, setRepoRefreshing] = useState(false);
  const [sandboxes, setSandboxes] = useState<SandboxSummary[]>([]);
  const [snapshots, setSnapshots] = useState<SnapshotSummary[]>([]);

  const [builderDraft, setBuilderDraft] = useState<BuilderDraftState>({
    prompt: "",
    name: "",
    repo: null,
    branch: "",
    template: "nextjs",
    web_app: true,
    mobile_app: false,
    vm: false,
    profile: "",
    provider: "antigravity",
    model: "gemini-4-hydrogen",
    thought_level: "",
  });
  const [builderSubmitting, setBuilderSubmitting] = useState(false);
  const [activeLaunch, setActiveLaunch] = useState<LaunchStatusResponse | null>(null);

  const [scratchpadCatalog, setScratchpadCatalog] = useState<ScratchpadCatalogResponse>({
    config_repo: "",
    refreshed_at: null,
    ideas_directory: "scratchpad",
    raw_directory: "raw",
    ideas: [],
    raw: [],
  });
  const [scratchpadLoaded, setScratchpadLoaded] = useState(false);
  const [scratchpadLoading, setScratchpadLoading] = useState(false);
  const [selectedNotes, setSelectedNotes] = useState<
    Record<ScratchpadSection, ScratchpadNoteDetailView | null>
  >({ ideas: null, raw: null });
  const [ideasDraft, setIdeasDraft] = useState({ titleHint: "", rawText: "" });
  const [rawDraft, setRawDraft] = useState({ title: "", content: "" });

  // Modals
  const [freshModalOpen, setFreshModalOpen] = useState(false);
  const [snapshotTarget, setSnapshotTarget] = useState<SnapshotTarget | null>(null);
  const [launchSnapshotTarget, setLaunchSnapshotTarget] = useState<SnapshotLaunchTarget | null>(
    null,
  );
  const [resultModalState, setResultModalState] = useState<{
    result: LaunchResponse | null;
    logs: string[];
  }>({ result: null, logs: [] });

  // Toast
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const showToast = useCallback((message: string, type: ToastKind = "info") => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    const id = Date.now();
    setToast({ id, message, type });
    toastTimerRef.current = setTimeout(
      () => setToast((cur) => (cur?.id === id ? null : cur)),
      type === "error" ? 6000 : 3000,
    );
  }, []);

  // Confirm Dialog
  const [confirmState, setConfirmState] = useState<{
    options: ConfirmOptions;
    resolve: (accepted: boolean) => void;
  } | null>(null);

  const confirmAction = useCallback((options: ConfirmOptions): Promise<boolean> => {
    return new Promise((resolve) => {
      setConfirmState({ options, resolve });
    });
  }, []);

  const selectedProfileRef = useRef(selectedProfile);
  useEffect(() => {
    selectedProfileRef.current = selectedProfile;
  }, [selectedProfile]);

  const refreshAll = useCallback(async (silent = false, profileOverride?: string) => {
    if (!silent) setLoading(true);
    const prof = profileOverride ?? selectedProfileRef.current;
    try {
      const profileParam = prof ? `profile=${encodeURIComponent(prof)}` : "";
      const sbParams = ["all_apps=true"];
      if (profileParam) sbParams.push(profileParam);
      const sbQuery = `?${sbParams.join("&")}`;
      const snapQuery = profileParam ? `?${profileParam}` : "";

      const [sbRes, snapRes, appsRes, primesRes] = await Promise.all([
        fetch(`/api/sandboxes${sbQuery}`, { cache: "no-store" }),
        fetch(`/api/snapshots${snapQuery}`, { cache: "no-store" }),
        fetch(`/api/apps${snapQuery}`, { cache: "no-store" }),
        fetch(`/api/primes${snapQuery}`, { cache: "no-store" }),
      ]);

      if (sbRes.ok) setSandboxes((await sbRes.json()) as SandboxSummary[]);
      if (snapRes.ok) setSnapshots((await snapRes.json()) as SnapshotSummary[]);
      if (appsRes.ok) setApps((await appsRes.json()) as FactoryAppView[]);
      if (primesRes.ok) setPrimes((await primesRes.json()) as PrimeSandboxView[]);
    } catch (err) {
      console.error("Failed refreshing dashboard data:", err);
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  const { track: trackLaunch, dismiss: dismissActiveLaunch } = useLaunchObserver({
    onStatus: setActiveLaunch,
    onRefresh: () => refreshAll(true),
  });

  const fetchScratchpadNotes = useCallback(async () => {
    try {
      const res = await fetch("/api/scratchpad/notes", { cache: "no-store" });
      if (!res.ok) {
        const err = await extractApiError(res);
        throw new Error(err.message);
      }
      const data = (await res.json()) as ScratchpadCatalogResponse;
      setScratchpadCatalog(data);
      setScratchpadLoaded(true);
    } catch (err) {
      console.error("Failed loading cached Scratchpad notes:", err);
    }
  }, []);

  const selectScratchpadNote = useCallback(
    async (section: ScratchpadSection, filename: string) => {
      if (!filename) return;
      try {
        const res = await fetch(
          `/api/scratchpad/notes/${encodeURIComponent(filename)}?section=${encodeURIComponent(section)}`,
          { cache: "no-store" },
        );
        if (!res.ok) {
          const err = await extractApiError(res);
          throw new Error(err.message);
        }
        const detail = (await res.json()) as ScratchpadNoteDetailView;
        setSelectedNotes((prev) => ({ ...prev, [section]: detail }));
      } catch (err) {
        showToast(
          `Failed loading note: ${err instanceof Error ? err.message : String(err)}`,
          "error",
        );
      }
    },
    [showToast],
  );

  const refreshScratchpadNotes = useCallback(async () => {
    if (scratchpadLoading) return;
    setScratchpadLoading(true);
    try {
      const res = await fetch("/api/scratchpad/notes/refresh", {
        method: "POST",
        cache: "no-store",
      });
      if (!res.ok) {
        const err = await extractApiError(res);
        throw new Error(err.message);
      }
      const data = (await res.json()) as ScratchpadCatalogResponse;
      setScratchpadCatalog(data);
      setScratchpadLoaded(true);

      for (const sec of ["ideas", "raw"] as const) {
        const current = selectedNotes[sec];
        if (!current) continue;
        const list = sec === "raw" ? data.raw || [] : data.ideas || [];
        const match = list.find((item) => item.filename === current.filename);
        if (!match) {
          setSelectedNotes((prev) => ({ ...prev, [sec]: null }));
        } else if (match.sha !== current.sha) {
          await selectScratchpadNote(sec, current.filename);
        }
      }
      showToast(
        `Loaded ${(data.ideas || []).length} Idea(s) and ${(data.raw || []).length} Raw note(s).`,
      );
    } catch (err) {
      showToast(
        `Scratchpad refresh failed: ${err instanceof Error ? err.message : String(err)}`,
        "error",
      );
    } finally {
      setScratchpadLoading(false);
    }
  }, [scratchpadLoading, selectedNotes, selectScratchpadNote, showToast]);

  const refreshGithubRepos = useCallback(async () => {
    if (repoRefreshing) return;
    setRepoRefreshing(true);
    try {
      const res = await fetch("/api/github/repos/refresh", {
        method: "POST",
        cache: "no-store",
      });
      if (!res.ok) {
        const err = await extractApiError(res);
        throw new Error(err.message);
      }
      const data = (await res.json()) as RepositoryCatalogCache;
      setRepoCatalog(data);
      showToast(`Loaded ${(data.repos || []).length} repositories.`);
    } catch (err) {
      showToast(
        `Repo refresh failed: ${err instanceof Error ? err.message : String(err)}`,
        "error",
      );
    } finally {
      setRepoRefreshing(false);
    }
  }, [repoRefreshing, showToast]);

  // Initial hydration
  useEffect(() => {
    async function init() {
      await Promise.all([
        fetch("/api/profiles", { cache: "no-store" })
          .then((r) => (r.ok ? r.json() : []))
          .then((data: ProfileInfo[]) => setProfiles(data))
          .catch((e) => console.error("Failed fetching profiles:", e)),
        fetch("/api/version", { cache: "no-store" })
          .then((r) => (r.ok ? r.json() : null))
          .then((data: VersionInfo | null) => setVersion(data))
          .catch((e) => console.error("Failed fetching version:", e)),
        fetch("/api/models", { cache: "no-store" })
          .then((r) => (r.ok ? r.json() : []))
          .then((items: ModelChoice[]) => {
            if (Array.isArray(items) && items.length > 0) {
              setModels(items);
              const def = items.find((m) => m.is_default) ?? items[0];
              setBuilderDraft((prev) => ({
                ...prev,
                provider: def.provider,
                model: def.model,
              }));
            }
          })
          .catch((e) => console.error("Failed fetching models:", e)),
        fetch("/api/github/repos", { cache: "no-store" })
          .then((r) => (r.ok ? r.json() : null))
          .then((data: RepositoryCatalogCache | null) => {
            if (data) setRepoCatalog(data);
          })
          .catch((e) => console.error("Failed loading cached GitHub repos:", e)),
        fetchScratchpadNotes(),
      ]);
      await refreshAll();

      if (typeof window !== "undefined") {
        const params = new URLSearchParams(window.location.search);
        const pendingLaunch = params.get("launch");
        if (pendingLaunch) {
          await trackLaunch(pendingLaunch);
        }
      }
    }
    void init();
  }, [fetchScratchpadNotes, refreshAll, trackLaunch]);

  // Hash-route compatibility redirect
  useEffect(() => {
    if (typeof window === "undefined") return;
    const hash = window.location.hash.replace(/^#/, "");
    const search = window.location.search;
    if (hash === "sandboxes" || hash === "snapshots" || hash === "scratchpad") {
      router.replace(`/${hash}${search}`);
    } else if (hash === "builder") {
      router.replace(`/${search}`);
    }
  }, [router]);

  // 5s Auto-Refresh timer
  useEffect(() => {
    if (!autoRefresh) return;
    const timer = setInterval(() => {
      void refreshAll(true);
    }, 5000);
    return () => clearInterval(timer);
  }, [autoRefresh, refreshAll]);

  const selectProfile = useCallback(
    (name: string) => {
      selectedProfileRef.current = name;
      setSelectedProfile(name);
      void refreshAll(false, name);
    },
    [refreshAll],
  );

  const submitAppPrompt = useCallback(async () => {
    const hasRepo = Boolean(builderDraft.repo && builderDraft.repo.trim());
    const hasPrompt = Boolean(builderDraft.prompt && builderDraft.prompt.trim());
    if ((!hasRepo && !hasPrompt) || builderSubmitting) return;

    setBuilderSubmitting(true);
    try {
      const payload = {
        prompt: hasPrompt ? builderDraft.prompt.trim() : "",
        name: builderDraft.name.trim() || null,
        repo: hasRepo ? builderDraft.repo!.trim() : null,
        branch: hasRepo && builderDraft.branch.trim() ? builderDraft.branch.trim() : null,
        template: builderDraft.template,
        web_app: builderDraft.web_app,
        mobile_app:
          !hasRepo && builderDraft.template === "nextjs" ? builderDraft.mobile_app : false,
        vm: builderDraft.vm,
        profile:
          builderDraft.profile || (selectedProfile !== "all" ? selectedProfile : null),
        provider: builderDraft.provider,
        model: builderDraft.model,
        thought_level: builderDraft.thought_level || null,
      };
      const res = await fetch("/api/apps", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await extractApiError(res);
        throw new Error(err.message);
      }
      const data = (await res.json()) as { request_id: string };
      setBuilderDraft((prev) => ({
        ...prev,
        prompt: "",
        name: "",
        repo: null,
        branch: "",
        web_app: prev.template === "nextjs",
      }));
      await refreshAll(true);
      await trackLaunch(data.request_id);
    } catch (err) {
      showToast(
        `Launch failed: ${err instanceof Error ? err.message : String(err)}`,
        "error",
      );
    } finally {
      setBuilderSubmitting(false);
    }
  }, [builderDraft, builderSubmitting, selectedProfile, refreshAll, trackLaunch, showToast]);

  const openFactoryApp = useCallback(
    async (app: FactoryAppView) => {
      try {
        const res = await fetch(`/api/apps/${encodeURIComponent(app.app_id)}/open`, {
          method: "POST",
        });
        if (!res.ok) {
          const err = await extractApiError(res);
          if (res.status === 409 && err.code === "sandbox_stopped") {
            showToast("Sandbox stopped — use Relaunch or Resume Snapshot.", "error");
            await refreshAll(true);
            return;
          }
          throw new Error(err.message);
        }
        const data = (await res.json()) as { handoff_url: string };
        window.location.assign(data.handoff_url);
      } catch (err) {
        showToast(
          `Could not open T3 chat: ${err instanceof Error ? err.message : String(err)}`,
          "error",
        );
      }
    },
    [refreshAll, showToast],
  );

  const relaunchFactoryApp = useCallback(
    async (app: { app_id: string }, { resume = false }: { resume?: boolean } = {}) => {
      if (!app?.app_id) return;
      try {
        const suffix = resume ? "?resume=true" : "";
        const res = await fetch(
          `/api/apps/${encodeURIComponent(app.app_id)}/relaunch${suffix}`,
          { method: "POST" },
        );
        if (!res.ok) {
          const err = await extractApiError(res);
          throw new Error(err.message);
        }
        const data = (await res.json()) as { request_id: string };
        await refreshAll(true);
        await trackLaunch(data.request_id);
      } catch (err) {
        showToast(
          `Relaunch failed: ${err instanceof Error ? err.message : String(err)}`,
          "error",
        );
      }
    },
    [refreshAll, trackLaunch, showToast],
  );

  const deleteFactoryApp = useCallback(
    async (app: FactoryAppView) => {
      const message =
        app.runtime_status === "running"
          ? `Delete "${app.title}" and remove its workspace from the sandbox? (Sibling apps in the Prime Sandbox keep running.)`
          : `Delete "${app.title}" from Factory Apps?`;
      const accepted = await confirmAction({
        title: "Delete Factory App",
        message,
        confirmLabel: "Delete",
        destructive: true,
      });
      if (!accepted) return;

      try {
        const res = await fetch(`/api/apps/${encodeURIComponent(app.app_id)}`, {
          method: "DELETE",
        });
        if (!res.ok) {
          const err = await extractApiError(res);
          throw new Error(err.message);
        }
        showToast(`Deleted "${app.title}".`);
        await refreshAll();
      } catch (err) {
        showToast(
          `Delete failed: ${err instanceof Error ? err.message : String(err)}`,
          "error",
        );
      }
    },
    [confirmAction, refreshAll, showToast],
  );

  const terminateSandbox = useCallback(
    async (sb: SandboxSummary) => {
      const targetName = sb.name ? `${sb.name} (${sb.id})` : sb.id;
      const accepted = await confirmAction({
        title: "Terminate Sandbox",
        message: `Are you sure you want to terminate sandbox ${targetName}?`,
        confirmLabel: "Terminate",
        destructive: true,
      });
      if (!accepted) return;

      try {
        const profileParam = sb.profile
          ? `?profile=${encodeURIComponent(sb.profile)}`
          : "";
        const res = await fetch(
          `/api/sandboxes/${encodeURIComponent(sb.id)}/terminate${profileParam}`,
          { method: "POST" },
        );
        if (!res.ok) {
          const err = await extractApiError(res, "Termination failed");
          throw new Error(err.message);
        }
        showToast(`Sandbox ${sb.id} terminated.`);
        await refreshAll();
      } catch (err) {
        showToast(
          `Error terminating sandbox: ${err instanceof Error ? err.message : String(err)}`,
          "error",
        );
      }
    },
    [confirmAction, refreshAll, showToast],
  );

  const deleteSnapshotRecord = useCallback(
    async (snap: SnapshotSummary) => {
      const accepted = await confirmAction({
        title: "Remove Snapshot Record",
        message: `Remove snapshot record ${snap.image_id} from the registry?`,
        confirmLabel: "Remove",
        destructive: true,
      });
      if (!accepted) return;

      try {
        const res = await fetch(`/api/snapshots/${encodeURIComponent(snap.image_id)}`, {
          method: "DELETE",
        });
        if (!res.ok) {
          const err = await extractApiError(res);
          throw new Error(err.message);
        }
        showToast("Snapshot record removed.");
        await refreshAll();
      } catch (err) {
        showToast(
          `Error deleting snapshot record: ${err instanceof Error ? err.message : String(err)}`,
          "error",
        );
      }
    },
    [confirmAction, refreshAll, showToast],
  );

  const loadNoteIntoBuilder = useCallback(
    (note: ScratchpadNoteDetailView) => {
      if (!note?.content) return;
      setBuilderDraft((prev) => ({ ...prev, prompt: note.content }));
      showToast(`Loaded '${note.title}' into Builder prompt.`);
      router.push("/");
    },
    [router, showToast],
  );

  const value = useMemo<DashboardContextValue>(
    () => ({
      loading,
      autoRefresh,
      setAutoRefresh,
      searchQuery,
      setSearchQuery,
      selectedProfile,
      selectProfile,
      profiles,
      version,
      apps,
      primes,
      models,
      repoCatalog,
      repoRefreshing,
      sandboxes,
      snapshots,
      builderDraft,
      setBuilderDraft,
      builderSubmitting,
      activeLaunch,
      trackLaunch,
      dismissActiveLaunch,
      scratchpadCatalog,
      scratchpadLoaded,
      scratchpadLoading,
      selectedNotes,
      setSelectedNotes,
      ideasDraft,
      setIdeasDraft,
      rawDraft,
      setRawDraft,
      refreshAll,
      refreshGithubRepos,
      fetchScratchpadNotes,
      refreshScratchpadNotes,
      selectScratchpadNote,
      loadNoteIntoBuilder,
      submitAppPrompt,
      openFactoryApp,
      relaunchFactoryApp,
      deleteFactoryApp,
      terminateSandbox,
      deleteSnapshotRecord,
      openFreshLaunchModal: () => setFreshModalOpen(true),
      openSnapshotModal: (target) => setSnapshotTarget(target),
      openLaunchFromSnapshotModal: (target) => setLaunchSnapshotTarget(target),
      showToast,
    }),
    [
      loading,
      autoRefresh,
      searchQuery,
      selectedProfile,
      selectProfile,
      profiles,
      version,
      apps,
      primes,
      models,
      repoCatalog,
      repoRefreshing,
      sandboxes,
      snapshots,
      builderDraft,
      builderSubmitting,
      activeLaunch,
      trackLaunch,
      dismissActiveLaunch,
      scratchpadCatalog,
      scratchpadLoaded,
      scratchpadLoading,
      selectedNotes,
      ideasDraft,
      rawDraft,
      refreshAll,
      refreshGithubRepos,
      fetchScratchpadNotes,
      refreshScratchpadNotes,
      selectScratchpadNote,
      loadNoteIntoBuilder,
      submitAppPrompt,
      openFactoryApp,
      relaunchFactoryApp,
      deleteFactoryApp,
      terminateSandbox,
      deleteSnapshotRecord,
      showToast,
    ],
  );

  return (
    <DashboardContext.Provider value={value}>
      {children}

      <FreshSandboxModal
        open={freshModalOpen}
        profiles={profiles}
        selectedProfile={selectedProfile}
        onClose={() => setFreshModalOpen(false)}
        onToast={showToast}
        onLaunched={(result, logs) => {
          setFreshModalOpen(false);
          setResultModalState({ result, logs });
        }}
      />

      <SnapshotCreateModal
        target={snapshotTarget}
        onClose={() => setSnapshotTarget(null)}
        onToast={showToast}
        onCaptured={() => refreshAll()}
      />

      <SnapshotLaunchModal
        target={launchSnapshotTarget}
        profiles={profiles}
        selectedProfile={selectedProfile}
        onClose={() => setLaunchSnapshotTarget(null)}
        onToast={showToast}
        onLaunched={(result) => {
          setLaunchSnapshotTarget(null);
          setResultModalState({ result, logs: [] });
        }}
      />

      <LaunchResultModal
        result={resultModalState.result}
        logs={resultModalState.logs}
        onClose={() => setResultModalState({ result: null, logs: [] })}
        onViewSandboxes={() => {
          setResultModalState({ result: null, logs: [] });
          router.push("/sandboxes");
          void refreshAll();
        }}
        onToast={showToast}
      />

      <ConfirmDialog
        options={confirmState?.options ?? null}
        onConfirm={() => {
          confirmState?.resolve(true);
          setConfirmState(null);
        }}
        onCancel={() => {
          confirmState?.resolve(false);
          setConfirmState(null);
        }}
      />

      <ToastViewport toast={toast} onDismiss={() => setToast(null)} />
    </DashboardContext.Provider>
  );
}
