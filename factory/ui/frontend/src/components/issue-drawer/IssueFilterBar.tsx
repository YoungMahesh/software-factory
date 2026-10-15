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
    <div className="p-4 bg-slate-950/40 border-b border-slate-800/80 space-y-3 shrink-0">
      <div className="flex items-center space-x-2">
        {/* Search Input */}
        <div className="relative flex-1">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            data-testid="issue-search-input"
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search by #number, title, or label..."
            className="w-full pl-9 pr-3 py-1.5 bg-slate-900 border border-slate-800 rounded-md text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono"
          />
        </div>

        {/* Filter Toggle Buttons */}
        <div className="flex items-center bg-slate-900 p-0.5 rounded-md border border-slate-800 text-xs shrink-0">
          <button
            data-testid="filter-open"
            type="button"
            onClick={() => onFilterChange("open")}
            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
              filterState === "open"
                ? "bg-indigo-600 text-white shadow-xs"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Open
          </button>
          <button
            data-testid="filter-closed"
            type="button"
            onClick={() => onFilterChange("closed")}
            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
              filterState === "closed"
                ? "bg-indigo-600 text-white shadow-xs"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Closed
          </button>
          <button
            data-testid="filter-all"
            type="button"
            onClick={() => onFilterChange("all")}
            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
              filterState === "all"
                ? "bg-indigo-600 text-white shadow-xs"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            All
          </button>
        </div>
      </div>
    </div>
  );
};
