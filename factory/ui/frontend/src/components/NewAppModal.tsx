import React, { useState } from "react";
import { Plus, X } from "lucide-react";
import { Button } from "./ui/Button";
import { Input } from "./ui/Input";

export interface NewAppModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (params: { name: string; description?: string }) => Promise<void>;
}

export const NewAppModal: React.FC<NewAppModalProps> = ({
  isOpen,
  onClose,
  onCreate,
}) => {
  const [name, setName] = useState<string>("");
  const [desc, setDesc] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError("App name is required.");
      return;
    }
    setError(null);
    setIsSubmitting(true);
    try {
      await onCreate({
        name: name.trim(),
        description: desc.trim() || undefined,
      });
      setName("");
      setDesc("");
      onClose();
    } catch (err: any) {
      setError(err.message || "Failed to create app");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    setError(null);
    onClose();
  };

  return (
    <div
      id="modal-new-app"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4"
    >
      <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-slate-100 flex items-center space-x-2">
            <Plus className="w-4 h-4 text-indigo-400" />
            <span>Create New App</span>
          </h3>
          <button
            id="btn-close-modal-x"
            type="button"
            onClick={handleClose}
            className="text-slate-400 hover:text-slate-200 cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">
              App Name (Repository) *
            </label>
            <Input
              id="input-new-app-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. inventory-tracker"
              className="font-mono"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">
              Description (Optional)
            </label>
            <Input
              id="input-new-app-desc"
              type="text"
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              placeholder="e.g. Inventory management dashboard"
            />
          </div>

          {error && (
            <div
              id="new-app-error"
              className="text-xs text-rose-400 bg-rose-950/40 border border-rose-900 p-2 rounded"
            >
              {error}
            </div>
          )}

          <div className="flex items-center justify-end space-x-2 pt-2">
            <Button
              id="btn-cancel-new-app"
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleClose}
            >
              Cancel
            </Button>
            <Button
              id="btn-create-new-app"
              type="submit"
              variant="primary"
              size="md"
              isLoading={isSubmitting}
            >
              Create App
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};
