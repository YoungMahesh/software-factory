import React, { useState, useMemo } from "react";
import {
  Folder,
  FolderOpen,
  FileCode,
  FileText,
  File,
  ChevronRight,
  ChevronDown,
  Search,
  X,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { RepoTreeItem } from "../../types";

export interface FileTreePaneProps {
  tree: RepoTreeItem[];
  selectedPath: string | null;
  onSelectFile: (path: string) => void;
  isLoading?: boolean;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

interface TreeNode {
  name: string;
  path: string;
  type: "blob" | "tree";
  size?: number;
  children: TreeNode[];
}

function buildHierarchy(items: RepoTreeItem[]): TreeNode[] {
  const root: TreeNode[] = [];
  const map: Record<string, TreeNode> = {};

  // Sort items so trees and shallower items come consistently
  const sorted = [...items].sort((a, b) => a.path.localeCompare(b.path));

  for (const item of sorted) {
    const parts = item.path.split("/");
    let currentPath = "";
    let currentLevel = root;

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      const isLeaf = i === parts.length - 1;

      let existing = map[currentPath];
      if (!existing) {
        existing = {
          name: part,
          path: currentPath,
          type: isLeaf ? item.type : "tree",
          size: isLeaf ? item.size : undefined,
          children: [],
        };
        map[currentPath] = existing;
        currentLevel.push(existing);
      }
      currentLevel = existing.children;
    }
  }

  // Sort each level: folders first alphabetically, then files alphabetically
  function sortNodes(nodes: TreeNode[]) {
    nodes.sort((a, b) => {
      if (a.type !== b.type) {
        return a.type === "tree" ? -1 : 1;
      }
      return a.name.localeCompare(b.name);
    });
    for (const n of nodes) {
      if (n.children.length > 0) {
        sortNodes(n.children);
      }
    }
  }

  sortNodes(root);
  return root;
}

function getFileIcon(path: string) {
  const ext = path.split(".").pop()?.toLowerCase();
  if (["ts", "tsx", "js", "jsx", "json", "py", "html", "css", "rs", "go"].includes(ext || "")) {
    return <FileCode className="w-3.5 h-3.5 text-amber-500 shrink-0" />;
  }
  if (["md", "txt", "log", "rst"].includes(ext || "")) {
    return <FileText className="w-3.5 h-3.5 text-slate-400 shrink-0" />;
  }
  return <File className="w-3.5 h-3.5 text-slate-400 shrink-0" />;
}

export const FileTreePane: React.FC<FileTreePaneProps> = ({
  tree,
  selectedPath,
  onSelectFile,
  isLoading = false,
  isCollapsed = false,
  onToggleCollapse,
}) => {
  const [filterText, setFilterText] = useState("");
  const [expandedFolders, setExpandedFolders] = useState<Record<string, boolean>>({});

  const filteredTree = useMemo(() => {
    if (!filterText.trim()) return tree;
    const lower = filterText.toLowerCase();
    return tree.filter((item) => item.path.toLowerCase().includes(lower));
  }, [tree, filterText]);

  const hierarchy = useMemo(() => buildHierarchy(filteredTree), [filteredTree]);

  const toggleFolder = (path: string) => {
    setExpandedFolders((prev) => ({
      ...prev,
      [path]: prev[path] === false ? true : false,
    }));
  };

  const renderNode = (node: TreeNode, depth: number = 0) => {
    if (node.type === "tree") {
      // Default to open unless explicitly set to false
      const isOpen = expandedFolders[node.path] !== false;
      return (
        <div key={node.path} className="flex flex-col select-none">
          <button
            type="button"
            onClick={() => toggleFolder(node.path)}
            className="flex items-center space-x-1.5 py-1 px-2 rounded-lg text-xs text-ink hover:bg-white/80 transition-colors text-left w-full cursor-pointer"
            style={{ paddingLeft: `${depth * 14 + 8}px` }}
          >
            {isOpen ? (
              <ChevronDown className="w-3 h-3 text-slate-400 shrink-0" />
            ) : (
              <ChevronRight className="w-3 h-3 text-slate-400 shrink-0" />
            )}
            {isOpen ? (
              <FolderOpen className="w-3.5 h-3.5 text-amber-500 shrink-0" />
            ) : (
              <Folder className="w-3.5 h-3.5 text-amber-500 shrink-0" />
            )}
            <span className="truncate font-medium text-slate-700">{node.name}</span>
          </button>
          {isOpen && node.children.length > 0 && (
            <div className="flex flex-col">
              {node.children.map((child) => renderNode(child, depth + 1))}
            </div>
          )}
        </div>
      );
    }

    const isSelected = selectedPath === node.path;
    return (
      <button
        key={node.path}
        type="button"
        onClick={() => onSelectFile(node.path)}
        className={`flex items-center space-x-1.5 py-1 px-2 rounded-lg text-xs transition-colors text-left w-full cursor-pointer ${
          isSelected
            ? "bg-primary text-white font-medium shadow-xs"
            : "text-ink hover:bg-white/80"
        }`}
        style={{ paddingLeft: `${depth * 14 + 20}px` }}
      >
        {getFileIcon(node.path)}
        <span className="truncate">{node.name}</span>
      </button>
    );
  };

  if (isCollapsed) {
    return (
      <div className="w-10 border-r border-hairline bg-soft-stone/30 flex flex-col items-center py-3 shrink-0">
        <button
          type="button"
          onClick={onToggleCollapse}
          className="p-1.5 rounded-lg text-slate-500 hover:text-ink hover:bg-white/60 transition-colors cursor-pointer"
          title="Expand file tree"
        >
          <PanelLeftOpen className="w-4 h-4" />
        </button>
      </div>
    );
  }

  return (
    <div
      data-testid="file-tree-pane"
      className="w-64 border-r border-hairline bg-soft-stone/20 flex flex-col shrink-0 overflow-hidden"
    >
      {/* Pane Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-hairline bg-white/40">
        <span className="text-xs font-semibold text-slate-700 uppercase tracking-wider font-mono">
          Files &amp; Code
        </span>
        {onToggleCollapse && (
          <button
            type="button"
            onClick={onToggleCollapse}
            className="p-1 rounded-md text-slate-400 hover:text-ink hover:bg-white transition-colors cursor-pointer"
            title="Collapse Files &amp; Code panel"
          >
            <PanelLeftClose className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {/* Filter / Search Bar */}
      <div className="p-2 border-b border-hairline bg-white/20">
        <div className="relative flex items-center">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2 pointer-events-none" />
          <input
            type="text"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            placeholder="Filter files..."
            className="w-full pl-7 pr-6 py-1 text-xs bg-white rounded-md border border-hairline focus:outline-none focus:border-slate-400 text-ink placeholder:text-slate-400"
          />
          {filterText && (
            <button
              type="button"
              onClick={() => setFilterText("")}
              className="absolute right-1.5 text-slate-400 hover:text-ink p-0.5"
            >
              <X className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>

      {/* Tree Content */}
      <div className="flex-1 overflow-y-auto p-1.5 space-y-0.5">
        {isLoading ? (
          <div className="p-4 text-center text-xs text-slate-400">Loading files...</div>
        ) : hierarchy.length === 0 ? (
          <div className="p-4 text-center text-xs text-slate-400">
            {filterText ? "No matching files" : "No files found"}
          </div>
        ) : (
          hierarchy.map((node) => renderNode(node, 0))
        )}
      </div>
    </div>
  );
};
