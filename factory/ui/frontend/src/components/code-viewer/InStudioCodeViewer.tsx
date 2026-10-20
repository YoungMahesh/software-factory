import React, { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileTreePane } from "./FileTreePane";
import { CodeViewerPanel } from "./CodeViewerPanel";
import { fetchRepoTree, fetchRepoFile } from "../../api";
import { RepoTreeItem, RepoFileResponse } from "../../types";

export interface InStudioCodeViewerProps {
  repo: string;
  branch?: string;
  initialPath?: string;
}

export const InStudioCodeViewer: React.FC<InStudioCodeViewerProps> = ({
  repo,
  branch,
  initialPath,
}) => {
  const [selectedPath, setSelectedPath] = useState<string | null>(initialPath || null);
  const [isTreeCollapsed, setIsTreeCollapsed] = useState(false);

  // 1. Fetch Repository File Tree
  const {
    data: treeData,
    isLoading: isTreeLoading,
  } = useQuery({
    queryKey: ["repoTree", repo, branch],
    queryFn: () => fetchRepoTree(repo, branch),
    enabled: Boolean(repo),
  });

  // Automatically select initialPath if provided and changed
  useEffect(() => {
    if (initialPath) {
      setSelectedPath(initialPath);
    }
  }, [initialPath]);

  // 2. Fetch File Content for Selected Path
  const {
    data: fileData,
    isLoading: isFileLoading,
    error: fileError,
  } = useQuery<RepoFileResponse>({
    queryKey: ["repoFile", repo, selectedPath, branch],
    queryFn: () => fetchRepoFile(repo, selectedPath!, branch),
    enabled: Boolean(repo && selectedPath),
  });

  const treeItems: RepoTreeItem[] = treeData?.tree || [];

  return (
    <div
      data-testid="in-studio-code-viewer"
      className="flex h-full w-full bg-white rounded-[22px] border border-hairline overflow-hidden shadow-sm"
    >
      <FileTreePane
        tree={treeItems}
        selectedPath={selectedPath}
        onSelectFile={setSelectedPath}
        isLoading={isTreeLoading}
        isCollapsed={isTreeCollapsed}
        onToggleCollapse={() => setIsTreeCollapsed((prev) => !prev)}
      />

      <CodeViewerPanel
        path={selectedPath}
        fileData={fileData || null}
        isLoading={isFileLoading}
        error={fileError ? (fileError as Error).message : null}
      />
    </div>
  );
};
