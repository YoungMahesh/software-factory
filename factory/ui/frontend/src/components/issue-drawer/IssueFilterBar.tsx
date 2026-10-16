import React from "react";
import { Search } from "lucide-react";

export interface IssueFilterBarProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  filterState: "open" | "closed" | "all";
  onFilterChange: (state: "open" | "closed" | "all") => void;
}

export const IssueFilterBar: React.FC<IssueFilterBarProps> = ({
  searchQuery,
  onSearchChange,
  filterState,
  onFilterChange,
}) => {
  return (
    <div className="p-4 bg-soft-stone border-b border-hairline space-y-3 shrink-0">
      <div className="flex items-center space-x-2">
        {/* Search Input */}
        <div className="relative flex-1">
          <Search className="w-3.5 h-3.5 text-muted absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            data-testid="issue-search-input"
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search by #number, title, or label..."
            className="w-full pl-9 pr-3 py-1.5 bg-white border border-hairline rounded-pill text-xs text-ink placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-form-focus font-mono shadow-2xs"
          />
        </div>

        {/* Filter Toggle Buttons */}
        <div className="flex items-center bg-white p-0.5 rounded-pill border border-hairline text-xs shrink-0 shadow-2xs">
          <button
            data-testid="filter-open"
            type="button"
            onClick={() => onFilterChange("open")}
            className={`px-3 py-1 rounded-pill text-xs font-medium transition-colors cursor-pointer ${
              filterState === "open"
                ? "bg-primary text-white shadow-xs"
                : "text-muted hover:text-ink"
            }`}
          >
            Open
          </button>
          <button
            data-testid="filter-closed"
            type="button"
            onClick={() => onFilterChange("closed")}
            className={`px-3 py-1 rounded-pill text-xs font-medium transition-colors cursor-pointer ${
              filterState === "closed"
                ? "bg-primary text-white shadow-xs"
                : "text-muted hover:text-ink"
            }`}
          >
            Closed
          </button>
          <button
            data-testid="filter-all"
            type="button"
            onClick={() => onFilterChange("all")}
            className={`px-3 py-1 rounded-pill text-xs font-medium transition-colors cursor-pointer ${
              filterState === "all"
                ? "bg-primary text-white shadow-xs"
                : "text-muted hover:text-ink"
            }`}
          >
            All
          </button>
        </div>
      </div>
    </div>
  );
};
