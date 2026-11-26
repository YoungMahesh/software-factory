"use client";

import { useMemo, useState } from "react";
import type {
  ScratchpadSaveResponse,
  ScratchpadSection,
  ScratchpadSuggestResponse,
} from "@dashboard/types";
import { Loader2, RefreshCw } from "lucide-react";
import { useDashboard } from "@/components/dashboard-provider";
import { ScratchpadSuggestionModal } from "@/components/scratchpad/suggestion-modal";
import { copyToClipboard, extractApiError, formatDate } from "@/lib/format";

export default function ScratchpadPage() {
  const {
    searchQuery,
    scratchpadCatalog,
    scratchpadLoaded,
    scratchpadLoading,
    selectedNotes,
    setSelectedNotes,
    ideasDraft,
    setIdeasDraft,
    rawDraft,
    setRawDraft,
    fetchScratchpadNotes,
    refreshScratchpadNotes,
    selectScratchpadNote,
    loadNoteIntoBuilder,
    showToast,
  } = useDashboard();

  const [section, setSection] = useState<ScratchpadSection>("ideas");
  const [filters, setFilters] = useState<Record<ScratchpadSection, string>>({
    ideas: "",
    raw: "",
  });

  const [suggesting, setSuggesting] = useState(false);
  const [savingIdea, setSavingIdea] = useState(false);
  const [savingRaw, setSavingRaw] = useState(false);
  const [ideasError, setIdeasError] = useState("");
  const [rawError, setRawError] = useState("");

  const [modalOpen, setModalOpen] = useState(false);
  const [modalError, setModalError] = useState("");
  const [suggestion, setSuggestion] = useState({ title: "", content: "", model: "" });

  const ideas = scratchpadCatalog.ideas ?? [];
  const rawNotes = scratchpadCatalog.raw ?? [];
  const activeNotes = section === "raw" ? rawNotes : ideas;
  const selectedNote = selectedNotes[section];
  const configRepo = scratchpadCatalog.config_repo || "";

  const filteredNotes = useMemo(() => {
    const q = (filters[section] || searchQuery || "").toLowerCase().trim();
    if (!q) return activeNotes;
    return activeNotes.filter(
      (n) =>
        n.title.toLowerCase().includes(q) ||
        n.filename.toLowerCase().includes(q) ||
        n.path.toLowerCase().includes(q),
    );
  }, [activeNotes, filters, section, searchQuery]);

  async function submitIdea() {
    const rawText = ideasDraft.rawText.trim();
    if (!rawText || suggesting || savingIdea) return;
    setIdeasError("");
    setModalError("");
    setSuggesting(true);
    try {
      if (!scratchpadLoaded) {
        await fetchScratchpadNotes();
      }
      const res = await fetch("/api/scratchpad/suggest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          raw_text: rawText,
          title_hint: ideasDraft.titleHint.trim() || null,
        }),
      });
      if (!res.ok) {
        const err = await extractApiError(res);
        throw new Error(err.message);
      }
      const data = (await res.json()) as ScratchpadSuggestResponse;
      setSuggestion({
        title: data.title || "",
        content: data.content || "",
        model: data.model || "",
      });
      setModalOpen(true);
    } catch (err) {
      const msg = `AI refinement failed: ${err instanceof Error ? err.message : String(err)}`;
      setIdeasError(msg);
      showToast(msg, "error");
    } finally {
      setSuggesting(false);
    }
  }

  async function acceptSuggestion() {
    const title = suggestion.title.trim();
    const content = suggestion.content.trim();
    if (!title || !content || savingIdea) return;
    setSavingIdea(true);
    setModalError("");
    setIdeasError("");
    try {
      const res = await fetch("/api/scratchpad/notes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, content, section: "ideas", mode: "ai" }),
      });
      if (!res.ok) {
        const err = await extractApiError(res);
        throw new Error(err.message);
      }
      const saved = (await res.json()) as ScratchpadSaveResponse;
      setModalOpen(false);
      setIdeasDraft({ titleHint: "", rawText: "" });
      setSelectedNotes((prev) => ({
        ...prev,
        ideas: {
          section: "ideas",
          filename: saved.filename,
          slug: saved.slug,
          path: saved.path,
          title: saved.title,
          sha: saved.sha,
          content: saved.content,
          html_url: saved.html_url,
        },
      }));
      await fetchScratchpadNotes();
      showToast(`Committed ${saved.path} to ${saved.config_repo}.`, "success");
    } catch (err) {
      const msg = `Failed saving idea: ${err instanceof Error ? err.message : String(err)}`;
      setModalError(msg);
      showToast(msg, "error");
    } finally {
      setSavingIdea(false);
    }
  }

  async function submitRawNote() {
    const rawContent = rawDraft.content;
    if (!rawContent.trim() || savingRaw) return;
    setSavingRaw(true);
    setRawError("");
    try {
      const res = await fetch("/api/scratchpad/notes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: rawDraft.title.trim(),
          content: rawContent,
          section: "raw",
          mode: "raw",
        }),
      });
      if (!res.ok) {
        const err = await extractApiError(res);
        throw new Error(err.message);
      }
      const saved = (await res.json()) as ScratchpadSaveResponse;
      setRawDraft({ title: "", content: "" });
      setSelectedNotes((prev) => ({
        ...prev,
        raw: {
          section: "raw",
          filename: saved.filename,
          slug: saved.slug,
          path: saved.path,
          title: saved.title,
          sha: saved.sha,
          content: saved.content,
          html_url: saved.html_url,
        },
      }));
      await fetchScratchpadNotes();
      showToast(`Committed ${saved.path} to ${saved.config_repo}.`, "success");
    } catch (err) {
      const msg = `Failed committing raw note: ${err instanceof Error ? err.message : String(err)}`;
      setRawError(msg);
      showToast(msg, "error");
    } finally {
      setSavingRaw(false);
    }
  }

  return (
    <div className="space-y-5 sm:space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-ink">
            Scratchpad
          </h2>
          <p className="text-xs sm:text-sm text-muted break-words">
            Refine <span className="text-primary-active font-medium">Ideas</span> with free
            OpenCode AI (
            <span className="font-mono text-primary-active">
              {(configRepo || "config") + "/scratchpad/"}
            </span>
            ), or commit <span className="text-ink font-medium">Raw</span> notes directly to
            GitHub (
            <span className="font-mono text-ink">
              {(configRepo || "config") + "/raw/"}
            </span>
            ) without AI.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5 self-start sm:self-auto flex-shrink-0">
          <span className="text-[11px] text-muted">
            {scratchpadCatalog.refreshed_at
              ? `Updated ${formatDate(scratchpadCatalog.refreshed_at)}`
              : "Not fetched yet (manual refresh only)"}
          </span>
          <button
            id="scratchpad-refresh-btn"
            type="button"
            disabled={scratchpadLoading}
            onClick={() => void refreshScratchpadNotes()}
            className="inline-flex items-center px-3 py-2 rounded-lg bg-surface-soft hover:bg-surface-card text-ink border border-hairline text-xs font-medium transition-colors disabled:opacity-50"
          >
            <RefreshCw
              className={`w-3.5 h-3.5 mr-1.5 ${scratchpadLoading ? "animate-spin" : ""}`}
            />
            <span>{scratchpadLoading ? "Refreshing..." : "Refresh Notes"}</span>
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex bg-surface-soft p-1 rounded-xl border border-hairline w-full sm:w-auto">
          <button
            id="scratchpad-subtab-ideas"
            type="button"
            onClick={() => setSection("ideas")}
            className={`flex-1 sm:flex-initial px-3.5 py-2 sm:py-1.5 rounded-lg text-xs sm:text-sm font-medium transition-all inline-flex items-center justify-center gap-2 ${
              section === "ideas"
                ? "bg-primary text-on-primary shadow-xs"
                : "text-muted hover:text-ink"
            }`}
          >
            <span>Ideas</span>
            <span
              className={`px-1.5 py-0.5 text-[11px] rounded-full ${
                section === "ideas"
                  ? "bg-on-primary/20 text-on-primary"
                  : "bg-surface-card text-ink"
              }`}
            >
              {ideas.length}
            </span>
          </button>

          <button
            id="scratchpad-subtab-raw"
            type="button"
            onClick={() => setSection("raw")}
            className={`flex-1 sm:flex-initial px-3.5 py-2 sm:py-1.5 rounded-lg text-xs sm:text-sm font-medium transition-all inline-flex items-center justify-center gap-2 ${
              section === "raw"
                ? "bg-accent-teal text-on-primary shadow-xs"
                : "text-muted hover:text-ink"
            }`}
          >
            <span>Raw</span>
            <span
              className={`px-1.5 py-0.5 text-[11px] rounded-full ${
                section === "raw"
                  ? "bg-on-primary/20 text-on-primary"
                  : "bg-surface-card text-ink"
              }`}
            >
              {rawNotes.length}
            </span>
          </button>
        </div>

        <span className="text-xs font-mono text-muted">
          {(configRepo || "config") + "/" + (section === "raw" ? "raw/" : "scratchpad/")}
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 sm:gap-6 items-start">
        <div className="lg:col-span-7 space-y-5 sm:space-y-6 min-w-0">
          {section === "ideas" ? (
            <section
              id="scratchpad-ideas-composer"
              className="bg-surface-soft border border-hairline rounded-2xl p-4 sm:p-6 shadow-sm space-y-4"
            >
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-base font-semibold text-ink">New Idea / Plan</h3>
                <span className="text-xs text-ink bg-success/15 border border-success/40 px-2 py-0.5 rounded-full flex-shrink-0">
                  Free AI Model
                </span>
              </div>

              <div className="space-y-3">
                <input
                  id="scratchpad-title-hint"
                  type="text"
                  value={ideasDraft.titleHint}
                  onChange={(e) =>
                    setIdeasDraft((prev) => ({ ...prev, titleHint: e.target.value }))
                  }
                  placeholder="Optional title hint (AI suggests one if blank)..."
                  className="w-full bg-canvas border border-hairline focus:border-primary rounded-lg px-3.5 py-2.5 sm:py-2 text-base sm:text-sm text-ink placeholder:text-muted-soft focus:outline-none"
                />

                <textarea
                  id="scratchpad-raw-input"
                  rows={6}
                  value={ideasDraft.rawText}
                  onChange={(e) =>
                    setIdeasDraft((prev) => ({ ...prev, rawText: e.target.value }))
                  }
                  onKeyDown={(e) => {
                    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                      e.preventDefault();
                      void submitIdea();
                    }
                  }}
                  placeholder="Jot down your idea, feature notes, architecture sketch, or rough prompt..."
                  className="w-full bg-canvas border border-hairline focus:border-primary rounded-xl px-3.5 sm:px-4 py-2.5 sm:py-3 text-base text-ink placeholder:text-muted-soft focus:outline-none resize-y"
                />
              </div>

              {ideasError && (
                <div className="p-3 rounded-lg bg-error/10 border border-error/30 text-xs text-error break-words">
                  {ideasError}
                </div>
              )}

              <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
                <span className="hidden sm:inline text-xs text-muted">
                  Tip: Press Ctrl/Cmd + Enter to refine with AI
                </span>
                <button
                  id="scratchpad-submit-btn"
                  type="button"
                  disabled={suggesting || savingIdea || !ideasDraft.rawText.trim()}
                  onClick={() => void submitIdea()}
                  className="w-full sm:w-auto inline-flex items-center justify-center px-4 py-2.5 sm:py-2 rounded-lg bg-primary hover:bg-primary-active text-on-primary text-sm font-semibold shadow-sm transition-colors disabled:opacity-50"
                >
                  {suggesting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                  <span>{suggesting ? "Thinking..." : "Submit"}</span>
                </button>
              </div>
            </section>
          ) : (
            <section
              id="scratchpad-raw-composer"
              className="bg-surface-soft border border-hairline rounded-2xl p-4 sm:p-6 shadow-sm space-y-4"
            >
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-base font-semibold text-ink">New Raw Note</h3>
                <span className="text-xs text-body bg-surface-card border border-hairline px-2 py-0.5 rounded-full flex-shrink-0">
                  Direct Git · No AI
                </span>
              </div>

              <div className="space-y-3">
                <input
                  id="scratchpad-raw-title"
                  type="text"
                  value={rawDraft.title}
                  onChange={(e) =>
                    setRawDraft((prev) => ({ ...prev, title: e.target.value }))
                  }
                  placeholder="Optional title for <slug>.md filename (uses leading words if blank)..."
                  className="w-full bg-canvas border border-hairline focus:border-accent-teal rounded-lg px-3.5 py-2.5 sm:py-2 text-base sm:text-sm text-ink placeholder:text-muted-soft focus:outline-none"
                />

                <textarea
                  id="scratchpad-raw-direct-input"
                  rows={6}
                  value={rawDraft.content}
                  onChange={(e) =>
                    setRawDraft((prev) => ({ ...prev, content: e.target.value }))
                  }
                  onKeyDown={(e) => {
                    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                      e.preventDefault();
                      void submitRawNote();
                    }
                  }}
                  placeholder="Write raw notes, logs, prompts, or snippets — committed verbatim to GitHub without AI..."
                  className="w-full bg-canvas border border-hairline focus:border-accent-teal rounded-xl px-3.5 sm:px-4 py-2.5 sm:py-3 text-base font-mono text-ink placeholder:text-muted-soft focus:outline-none resize-y"
                />
              </div>

              {rawError && (
                <div className="p-3 rounded-lg bg-error/10 border border-error/30 text-xs text-error break-words">
                  {rawError}
                </div>
              )}

              <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
                <span className="hidden sm:inline text-xs text-muted">
                  Tip: Press Ctrl/Cmd + Enter to commit directly to GitHub
                </span>
                <button
                  id="scratchpad-raw-submit-btn"
                  type="button"
                  disabled={savingRaw || !rawDraft.content.trim()}
                  onClick={() => void submitRawNote()}
                  className="w-full sm:w-auto inline-flex items-center justify-center px-4 py-2.5 sm:py-2 rounded-lg bg-accent-teal hover:opacity-90 text-on-primary text-sm font-semibold shadow-sm transition-colors disabled:opacity-50"
                >
                  {savingRaw && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                  <span>{savingRaw ? "Committing..." : "Commit Raw Note"}</span>
                </button>
              </div>
            </section>
          )}

          {selectedNote && (
            <section className="bg-surface-soft border border-hairline rounded-2xl p-4 sm:p-6 shadow-sm space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 border-b border-hairline pb-4">
                <div className="min-w-0 space-y-1">
                  <h3 className="text-lg font-bold text-ink break-words">
                    {selectedNote.title}
                  </h3>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                    <span
                      className={`font-mono break-all ${
                        section === "raw" ? "text-ink" : "text-primary-active"
                      }`}
                    >
                      {selectedNote.path}
                    </span>
                    {selectedNote.html_url && (
                      <a
                        href={selectedNote.html_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-muted hover:text-ink underline flex-shrink-0"
                      >
                        GitHub ↗
                      </a>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2 w-full sm:w-auto flex-shrink-0">
                  <button
                    type="button"
                    onClick={async () => {
                      await copyToClipboard(selectedNote.content || "");
                      showToast("Note copied!");
                    }}
                    className="flex-1 sm:flex-initial px-3 py-2 sm:py-1.5 rounded-lg bg-canvas hover:bg-surface-card text-ink border border-hairline text-xs font-medium text-center"
                  >
                    Copy
                  </button>
                  <button
                    id="scratchpad-use-in-builder-btn"
                    type="button"
                    onClick={() => loadNoteIntoBuilder(selectedNote)}
                    className="flex-1 sm:flex-initial px-3.5 py-2 sm:py-1.5 rounded-lg bg-primary hover:bg-primary-active text-on-primary text-xs font-semibold shadow-2xs text-center"
                  >
                    Use in Builder →
                  </button>
                </div>
              </div>

              <pre
                id="scratchpad-note-content"
                className="bg-surface-dark text-on-dark border border-surface-dark-elevated rounded-xl p-3 sm:p-4 text-xs sm:text-sm whitespace-pre-wrap break-words font-mono max-h-80 sm:max-h-96 overflow-y-auto"
              >
                {selectedNote.content}
              </pre>
            </section>
          )}
        </div>

        <section className="lg:col-span-5 bg-surface-soft border border-hairline rounded-2xl p-4 sm:p-5 shadow-sm space-y-4 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-base font-semibold text-ink">
              {section === "raw" ? "Saved Raw Notes" : "Saved Ideas"}
            </h3>
            <span className="text-xs px-2 py-0.5 rounded-full bg-surface-card text-body border border-hairline">
              {filteredNotes.length} of {activeNotes.length}
            </span>
          </div>

          <input
            id="scratchpad-notes-filter"
            type="text"
            value={filters[section]}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, [section]: e.target.value }))
            }
            placeholder={
              section === "raw"
                ? "Filter raw notes by title or filename..."
                : "Filter ideas by title or filename..."
            }
            className="w-full bg-canvas border border-hairline rounded-lg px-3 py-2 sm:py-1.5 text-base sm:text-xs text-ink placeholder:text-muted-soft focus:outline-none focus:border-primary"
          />

          {scratchpadLoading && activeNotes.length === 0 && (
            <div className="py-10 text-center text-sm text-muted">
              Refreshing notes from GitHub...
            </div>
          )}

          {!scratchpadLoading && activeNotes.length === 0 && (
            <div className="border border-dashed border-hairline rounded-xl p-6 text-center text-xs text-muted">
              {scratchpadCatalog.refreshed_at
                ? section === "raw"
                  ? "No Raw notes found in config/raw/ yet. Commit one to get started."
                  : "No Idea notes found in config/scratchpad/ yet. Submit an idea to get started."
                : "No cached notes yet. Click Refresh Notes to load from GitHub, or commit a new note."}
            </div>
          )}

          {!scratchpadLoading &&
            activeNotes.length > 0 &&
            filteredNotes.length === 0 && (
              <div className="border border-dashed border-hairline rounded-xl p-6 text-center text-xs text-muted">
                No cached notes match your filter.
              </div>
            )}

          <div className="space-y-2 max-h-96 lg:max-h-[34rem] overflow-y-auto pr-1">
            {filteredNotes.map((note) => {
              const isSelected = selectedNote?.filename === note.filename;
              return (
                <button
                  key={`${note.section}:${note.filename}`}
                  type="button"
                  data-note-filename={note.filename}
                  data-note-section={note.section}
                  onClick={() => void selectScratchpadNote(section, note.filename)}
                  className={`w-full text-left p-3 rounded-xl border transition-colors space-y-1 ${
                    isSelected
                      ? section === "raw"
                        ? "bg-accent-teal/15 border-accent-teal"
                        : "bg-primary/15 border-primary"
                      : "bg-canvas border-hairline hover:border-muted-soft hover:bg-surface-card/40"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-ink truncate min-w-0">
                      {note.title}
                    </span>
                    <span className="text-[11px] text-muted font-mono flex-shrink-0">
                      {note.size} B
                    </span>
                  </div>
                  <div
                    className={`text-xs font-mono truncate ${
                      section === "raw" ? "text-ink" : "text-primary-active"
                    }`}
                  >
                    {note.path}
                  </div>
                </button>
              );
            })}
          </div>
        </section>
      </div>

      <ScratchpadSuggestionModal
        open={modalOpen}
        title={suggestion.title}
        content={suggestion.content}
        model={suggestion.model}
        error={modalError}
        saving={savingIdea}
        existingIdeas={ideas}
        configRepo={configRepo}
        onChangeTitle={(v) => setSuggestion((prev) => ({ ...prev, title: v }))}
        onChangeContent={(v) => setSuggestion((prev) => ({ ...prev, content: v }))}
        onReject={() => {
          setModalOpen(false);
          setModalError("");
          showToast("Suggestion dismissed. Your draft was preserved.");
        }}
        onAccept={() => void acceptSuggestion()}
      />
    </div>
  );
}
