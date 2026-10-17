import React, { useState } from "react";
import { SlidersHorizontal, ChevronDown, ChevronRight } from "lucide-react";

export type ExecutionModel = "deepseek-v4.1-flash" | "mimo-v2.6-flash";

export interface ExecutionSettings {
  model: ExecutionModel;
  vm: boolean;
}

export const MODEL_LABELS: Record<ExecutionModel, string> = {
  "deepseek-v4.1-flash": "DeepSeek V4.1 Flash",
  "mimo-v2.6-flash": "MiMo-V2.6-Flash",
};

export interface ExecutionSettingsPanelProps {
  model: string;
  onModelChange: (model: string) => void;
  vm: boolean;
  onVmChange: (vm: boolean) => void;
}

export const ExecutionSettingsPanel: React.FC<ExecutionSettingsPanelProps> = ({
  model,
  onModelChange,
  vm,
  onVmChange,
}) => {
  const [isOpen, setIsOpen] = useState<boolean>(false);

  return (
    <div className="border-b border-hairline bg-soft-stone/60">
      <button
        id="btn-toggle-execution-settings"
        data-testid="toggle-execution-settings"
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className="w-full flex items-center justify-between px-6 py-2.5 text-xs text-ink hover:bg-soft-stone transition-colors cursor-pointer select-none"
      >
        <div className="flex items-center space-x-2">
          <SlidersHorizontal className="w-3.5 h-3.5 text-muted" />
          <span className="font-semibold font-sans">Execution Settings</span>
          <span className="text-[10px] font-mono text-muted px-2 py-0.5 rounded-pill bg-white border border-hairline">
            {MODEL_LABELS[model as ExecutionModel] || model}
            {vm ? " • VM Sandbox" : ""}
          </span>
        </div>
        <div className="text-muted">
          {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </div>
      </button>

      {isOpen && (
        <div
          id="execution-settings-panel"
          data-testid="execution-settings-panel"
          className="px-6 py-3 bg-white border-t border-hairline grid grid-cols-1 sm:grid-cols-2 gap-4 animate-in fade-in slide-in-from-top-1 duration-150"
        >
          <div>
            <label
              htmlFor="select-execution-model"
              className="block text-xs font-medium text-muted mb-1 font-sans"
            >
              Model
            </label>
            <select
              id="select-execution-model"
              data-testid="execution-model-select"
              value={model}
              onChange={(e) => onModelChange(e.target.value)}
              className="w-full bg-soft-stone/40 border border-hairline rounded-pill px-3 py-1.5 text-xs text-ink font-mono focus:outline-none focus:ring-1 focus:ring-form-focus cursor-pointer"
            >
              {Object.entries(MODEL_LABELS).map(([val, label]) => (
                <option key={val} value={val}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col justify-end">
            <label className="flex items-center space-x-2 text-xs text-ink cursor-pointer select-none py-1">
              <input
                id="check-execution-vm"
                data-testid="execution-vm-toggle"
                type="checkbox"
                checked={vm}
                onChange={(e) => onVmChange(e.target.checked)}
                className="w-4 h-4 rounded border-hairline bg-white text-primary focus:ring-form-focus"
              />
              <span className="font-sans">VM Sandbox virtualization (Docker support)</span>
            </label>
          </div>
        </div>
      )}
    </div>
  );
};
