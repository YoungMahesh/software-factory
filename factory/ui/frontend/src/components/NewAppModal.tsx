import React, { useState } from "react";
import { Plus, X } from "lucide-react";
import { Button } from "./ui/Button";
import { Input } from "./ui/Input";

export interface NewAppModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (params: { name: string; description?: string; private?: boolean }) => Promise<void>;
}

export const NewAppModal: React.FC<NewAppModalProps> = ({
  isOpen,
  onClose,
  onCreate,
}) => {
  const [name, setName] = useState<string>("");
  const [desc, setDesc] = useState<string>("");
  const [isPrivate, setIsPrivate] = useState<boolean>(true);
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
        private: isPrivate,
      });
      setName("");
      setDesc("");
      setIsPrivate(true);
      onClose();
    } catch (err: any) {
      setError(err.message || "Failed to create app");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    setError(null);
    setIsPrivate(true);
    onClose();
  };

  return (
    <div
      id="modal-new-app"
      className="fixed inset-0 z-50 flex items-center justify-center bg-cohere-black/50 backdrop-blur-2xs p-4"
    >
      <div className="w-full max-w-md bg-white border border-hairline rounded-[22px] p-6 shadow-2xl space-y-4">
        <div className="flex items-center justify-between pb-2 border-b border-hairline">
          <h3 className="text-sm font-semibold text-ink font-sans flex items-center space-x-2">
            <Plus className="w-4 h-4 text-primary" />
            <span>Create New App</span>
          </h3>
          <button
            id="btn-close-modal-x"
            type="button"
            onClick={handleClose}
            className="text-muted hover:text-ink p-1 rounded-pill hover:bg-soft-stone transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-ink mb-1">
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
            <label className="block text-xs font-medium text-ink mb-1">
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

          <div className="flex items-start space-x-3 pt-1">
            <input
              id="input-new-app-private"
              type="checkbox"
              checked={isPrivate}
              onChange={(e) => setIsPrivate(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-hairline bg-white text-primary focus:ring-form-focus cursor-pointer accent-primary"
            />
            <label htmlFor="input-new-app-private" className="cursor-pointer select-none">
              <span className="block text-xs font-medium text-ink">
                Private repository
              </span>
              <span className="block text-[11px] text-muted">
                Only accessible to members of the organization
              </span>
            </label>
          </div>

          {error && (
            <div
              id="new-app-error"
              className="text-xs text-coral bg-coral/10 border border-coral/30 p-2.5 rounded-lg"
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
