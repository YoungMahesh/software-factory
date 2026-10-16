import React, { useState, useEffect } from "react";
import {
  Play,
  Cpu,
  XCircle,
} from "lucide-react";
import { Job, Milestone, Issue, LaunchJobParams } from "../../types";
import { fetchMilestones } from "../../api";

export interface JobConfigPanelProps {
  selectedRepo: string;
  onLaunch: (params: LaunchJobParams) => void;
  activeJob: Job | null;
  onCancel: (jobId: string) => void;
}

export const JobConfigPanel: React.FC<JobConfigPanelProps> = ({
  selectedRepo,
  onLaunch,
  activeJob,
  onCancel,
}) => {
  const [milestonesMeta, setMilestonesMeta] = useState<Milestone[]>([]);
  const [feature, setFeature] = useState<string>("");
  const [customFeature, setCustomFeature] = useState<string>("");
  const [issue, setIssue] = useState<string>("");
  const [customIssue, setCustomIssue] = useState<string>("");
  const [model, setModel] = useState<string>("deepseek-v4.1-flash");
  const [vm, setVm] = useState<boolean>(false);
  const [dev, setDev] = useState<boolean>(false);
  const [loadingMeta, setLoadingMeta] = useState<boolean>(false);

  // Discover features / issues when repo changes
  useEffect(() => {
    if (!selectedRepo) {
      setMilestonesMeta([]);
      return;
    }

    let isCancelled = false;
    setLoadingMeta(true);

    fetchMilestones(selectedRepo)
      .then((msRes) => {
        if (isCancelled) return;
        setMilestonesMeta(msRes?.milestones || []);
      })
      .catch(() => {
        if (isCancelled) return;
        setMilestonesMeta([]);
      })
      .finally(() => {
        if (!isCancelled) setLoadingMeta(false);
      });

    return () => {
      isCancelled = true;
    };
  }, [selectedRepo]);

  // Derived available features from GitHub milestones
  const availableFeatures: { slug: string }[] = milestonesMeta.map((m) => ({
    slug: m.title,
  }));

  // Derived available issues for selected feature
  const effectiveFeature = feature === "__custom__" ? customFeature : feature;
  const availableIssues: Issue[] = [];

  if (feature && feature !== "__custom__") {
    const ms = milestonesMeta.find((m) => m.title === feature);
    if (ms) {
      ms.issues.forEach((iss) => {
        if (!availableIssues.some((ai) => String(ai.number) === String(iss.number))) {
          availableIssues.push(iss);
        }
      });
    }
  }

  // Preview selected issue
  const effectiveIssueId = issue === "__custom__" ? customIssue : issue;
  const selectedIssueObj = availableIssues.find(
    (i) => String(i.number) === String(effectiveIssueId)
  );

  const handleLaunchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedRepo) return;
    onLaunch({
      repo: selectedRepo,
      feature: effectiveFeature || undefined,
      issue: effectiveIssueId || undefined,
      model,
      vm,
      dev,
    });
  };

  return (
    <div className="bg-soft-stone rounded-xl border border-hairline p-5 shadow-sm flex flex-col justify-between space-y-4 text-ink">
      {/* Feature & Ticket Target Selectors */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pb-4 border-b border-hairline">
        {/* Feature / Milestone Selector */}
        <div>
          <label className="block text-xs font-medium text-body-muted mb-1.5 font-sans">
            Milestone (Feature)
          </label>
          <select
            id="select-feature"
            value={feature}
            disabled={!selectedRepo || loadingMeta}
            onChange={(e) => {
              setFeature(e.target.value);
              setIssue("");
            }}
            className="w-full bg-white border border-hairline rounded-pill px-3 py-2 text-xs text-ink focus:outline-none focus:ring-1 focus:ring-form-focus disabled:opacity-50"
          >
            <option value="">(None / Root frontier)</option>
            {availableFeatures.map((f) => (
              <option key={f.slug} value={f.slug}>
                {f.slug}
              </option>
            ))}
            <option value="__custom__">Custom feature slug...</option>
          </select>

          {feature === "__custom__" && (
            <input
              id="input-feature-custom"
              type="text"
              value={customFeature}
              onChange={(e) => setCustomFeature(e.target.value)}
              placeholder="e.g. inventory-management"
              className="mt-2 w-full bg-white border border-hairline rounded-pill px-3 py-1.5 text-xs text-ink font-mono focus:outline-none focus:ring-1 focus:ring-form-focus"
            />
          )}
        </div>

        {/* Issue / Ticket Selector */}
        <div>
          <label className="block text-xs font-medium text-body-muted mb-1.5 font-sans">
            Ticket (Issue)
          </label>
          <select
            id="select-issue"
            value={issue}
            disabled={!selectedRepo || loadingMeta}
            onChange={(e) => setIssue(e.target.value)}
            className="w-full bg-white border border-hairline rounded-pill px-3 py-2 text-xs text-ink focus:outline-none focus:ring-1 focus:ring-form-focus disabled:opacity-50"
          >
            <option value="">(Autonomous Frontier Batch)</option>
            {availableIssues.map((iss) => (
              <option key={String(iss.number)} value={String(iss.number)}>
                #{iss.number} — {iss.title}
              </option>
            ))}
            <option value="__custom__">Custom issue ID...</option>
          </select>

          {issue === "__custom__" && (
            <input
              id="input-issue-custom"
              type="text"
              value={customIssue}
              onChange={(e) => setCustomIssue(e.target.value)}
              placeholder="e.g. 01 or 42"
              className="mt-2 w-full bg-white border border-hairline rounded-pill px-3 py-1.5 text-xs text-ink font-mono focus:outline-none focus:ring-1 focus:ring-form-focus"
            />
          )}
        </div>
      </div>

      {/* Issue Badge Preview */}
      {selectedIssueObj && (
        <div
          id="issue-badge-preview"
          className="p-3 bg-white rounded-lg border border-hairline text-xs space-y-1.5 shadow-2xs"
        >
          <div className="flex items-center justify-between">
            <span id="preview-title" className="font-semibold text-ink truncate">
              #{selectedIssueObj.number}: {selectedIssueObj.title}
            </span>
            <span
              id="preview-status-badge"
              className="px-2.5 py-0.5 rounded-pill text-[10px] font-mono uppercase bg-soft-stone text-ink border border-hairline"
            >
              {selectedIssueObj.status}
            </span>
          </div>
          {selectedIssueObj.blocked_by && selectedIssueObj.blocked_by.length > 0 && (
            <div id="preview-details" className="text-[11px] text-amber-600 font-mono">
              Blocked by: {selectedIssueObj.blocked_by.join(", ")}
            </div>
          )}
        </div>
      )}

      {/* Launch Parameters Form */}
      <form id="launch-form" onSubmit={handleLaunchSubmit} className="space-y-4">
        <h2 className="text-sm font-semibold text-ink flex items-center space-x-2 font-display">
          <Cpu className="w-4 h-4 text-ink" />
          <span>Launch Parameters</span>
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium text-body-muted mb-1.5 font-sans">
              LLM Model
            </label>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full bg-white border border-hairline rounded-pill px-3 py-2 text-xs text-ink focus:outline-none focus:ring-1 focus:ring-form-focus font-mono"
            >
              <option value="deepseek-v4.1-flash">DeepSeek V4.1 Flash (Recommended)</option>
              <option value="mimo-v2.6-flash">MiMo-V2.6-Flash</option>
            </select>
          </div>

          <div className="flex flex-col justify-end space-y-2">
            <label className="flex items-center space-x-2 text-xs text-ink cursor-pointer select-none">
              <input
                id="check-vm"
                type="checkbox"
                checked={vm}
                onChange={(e) => setVm(e.target.checked)}
                className="w-4 h-4 rounded border-hairline bg-white text-primary focus:ring-form-focus"
              />
              <span>Launch in VM Sandbox (Full VM with Docker)</span>
            </label>

            <label className="flex items-center space-x-2 text-xs text-ink cursor-pointer select-none">
              <input
                type="checkbox"
                checked={dev}
                onChange={(e) => setDev(e.target.checked)}
                className="w-4 h-4 rounded border-hairline bg-white text-primary focus:ring-form-focus"
              />
              <span>Dev Preview Mode (Port 3000 keep-alive)</span>
            </label>
          </div>
        </div>

        <div className="pt-4 border-t border-hairline flex items-center justify-between">
          <div className="text-xs text-muted">
            Target:{" "}
            <span className="font-mono text-ink font-semibold">
              {selectedRepo || "No repo selected"}
            </span>
            {effectiveFeature ? ` / ${effectiveFeature}` : ""}
            {effectiveIssueId ? ` (Ticket #${effectiveIssueId})` : ""}
          </div>

          <button
            id="btn-launch"
            type="submit"
            disabled={!selectedRepo}
            className="flex items-center space-x-2 px-5 py-2.5 rounded-pill bg-primary hover:bg-cohere-black disabled:opacity-40 disabled:pointer-events-none text-white text-xs font-semibold shadow-sm transition-colors cursor-pointer"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>Launch Assembly Line</span>
          </button>
        </div>
      </form>

      {/* Active Job Header Banner (if any) */}
      {activeJob && (
        <div className="mt-4 p-3.5 bg-white rounded-xl border border-hairline flex items-center justify-between shadow-2xs">
          <div className="flex items-center space-x-3">
            <div className="flex flex-col">
              <span className="text-[10px] text-muted uppercase font-mono">Job ID</span>
              <span id="active-job-id" className="text-xs font-mono font-bold text-ink">
                {activeJob.id}
              </span>
            </div>

            <div className="flex flex-col">
              <span className="text-[10px] text-muted uppercase font-mono">Target</span>
              <span id="active-job-target" className="text-xs font-mono text-body-muted">
                {activeJob.repo} / {activeJob.feature}
              </span>
            </div>

            <div className="flex flex-col">
              <span className="text-[10px] text-muted uppercase font-mono">Status</span>
              <span
                id="active-job-status"
                className="px-2.5 py-0.5 rounded-pill text-[10px] font-mono uppercase bg-soft-stone text-ink border border-hairline font-semibold"
              >
                {activeJob.status}
              </span>
            </div>

            {activeJob.duration && (
              <div className="flex flex-col">
                <span className="text-[10px] text-muted uppercase font-mono">Duration</span>
                <span id="active-job-timer" className="text-xs font-mono text-body-muted">
                  {activeJob.duration.toFixed(1)}s
                </span>
              </div>
            )}
          </div>

          {activeJob.status === "RUNNING" && (
            <button
              id="btn-cancel"
              type="button"
              onClick={() => onCancel(activeJob.id)}
              className="flex items-center space-x-1 px-3 py-1.5 rounded-pill bg-coral/10 hover:bg-coral/20 border border-coral/30 text-coral text-xs font-semibold transition-colors cursor-pointer"
            >
              <XCircle className="w-3.5 h-3.5" />
              <span>Cancel Job</span>
            </button>
          )}
        </div>
      )}
    </div>
  );
};
