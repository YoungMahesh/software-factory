import React, { useState } from "react";
import {
  FileCode,
  Copy,
  Check,
  AlertTriangle,
  FileWarning,
  Loader2,
  Code2,
  Download,
} from "lucide-react";
import { RepoFileResponse } from "../../types";
import { copyToClipboard } from "../../utils";

export interface CodeViewerPanelProps {
  path: string | null;
  fileData: RepoFileResponse | null;
  isLoading?: boolean;
  error?: string | null;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const JS_TS_KEYWORDS = new Set([
  "import", "export", "from", "default", "const", "let", "var",
  "function", "return", "if", "else", "for", "while", "class",
  "interface", "type", "async", "await", "try", "catch", "throw",
  "new", "extends", "implements", "public", "private", "protected",
  "switch", "case", "break", "continue", "def", "yield", "as",
]);

function renderSyntaxTokens(line: string, _language?: string): React.ReactNode {
  if (!line) return "\u00A0";

  // Check for full comment lines
  const trimmed = line.trimStart();
  if (trimmed.startsWith("//") || trimmed.startsWith("#") || trimmed.startsWith("/*") || trimmed.startsWith("*")) {
    return <span className="text-slate-500 italic">{line}</span>;
  }

  // Tokenize line with regex capturing strings, comments, words, numbers, symbols
  const regex = /(\/\/[^\n]*|\/\*.*?\*\/|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|\b\d+(?:\.\d+)?\b|\b[A-Za-z_$][A-Za-z0-9_$]*\b|[{}()[\].,;:+\-*/%=<>!&|^~?]+|[ \t]+)/g;
  const tokens = line.match(regex);

  if (!tokens || tokens.join("") !== line) {
    return line;
  }

  return tokens.map((tok, idx) => {
    if (tok.startsWith("//") || tok.startsWith("/*")) {
      return <span key={idx} className="text-slate-500 italic">{tok}</span>;
    }
    if ((tok.startsWith('"') && tok.endsWith('"')) || (tok.startsWith("'") && tok.endsWith("'")) || (tok.startsWith("`") && tok.endsWith("`"))) {
      return <span key={idx} className="text-emerald-300">{tok}</span>;
    }
    if (/^\d+(?:\.\d+)?$/.test(tok)) {
      return <span key={idx} className="text-amber-300">{tok}</span>;
    }
    if (tok === "true" || tok === "false" || tok === "null" || tok === "undefined" || tok === "None") {
      return <span key={idx} className="text-coral-soft font-semibold">{tok}</span>;
    }
    if (JS_TS_KEYWORDS.has(tok)) {
      return <span key={idx} className="text-coral font-medium">{tok}</span>;
    }
    if (/^[A-Z][A-Za-z0-9_$]*$/.test(tok)) {
      return <span key={idx} className="text-cyan-300">{tok}</span>;
    }
    return <span key={idx} className="text-slate-200">{tok}</span>;
  });
}

export const CodeViewerPanel: React.FC<CodeViewerPanelProps> = ({
  path,
  fileData,
  isLoading = false,
  error = null,
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!fileData?.content) return;
    const ok = await copyToClipboard(fileData.content);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // 1. Empty State (No file selected)
  if (!path) {
    return (
      <div
        data-testid="code-viewer-empty-state"
        className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-white/40"
      >
        <div className="w-12 h-12 rounded-full bg-soft-stone flex items-center justify-center text-slate-400 mb-3">
          <Code2 className="w-6 h-6" />
        </div>
        <h3 className="text-sm font-semibold text-ink mb-1">No file selected</h3>
        <p className="text-xs text-slate-500 max-w-sm">
          Select a file to inspect its source code.
        </p>
      </div>
    );
  }

  // 2. Loading State
  if (isLoading) {
    return (
      <div
        data-testid="code-viewer-loading"
        className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-white/40"
      >
        <Loader2 className="w-6 h-6 animate-spin text-coral mb-2" />
        <span className="text-xs text-slate-500">Loading {path}...</span>
      </div>
    );
  }

  // 3. Error State
  if (error) {
    return (
      <div
        data-testid="code-viewer-error"
        className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-white/40"
      >
        <div className="w-12 h-12 rounded-full bg-rose-100 flex items-center justify-center text-rose-600 mb-3">
          <AlertTriangle className="w-6 h-6" />
        </div>
        <h3 className="text-sm font-semibold text-ink mb-1">Failed to load file</h3>
        <p className="text-xs text-rose-600 max-w-sm">{error}</p>
      </div>
    );
  }

  const rawLines = fileData?.content ? fileData.content.split("\n") : [];
  const downloadUrl = fileData?.download_url || (path && fileData ? `/api/repos/${fileData.repo}/raw?path=${encodeURIComponent(path)}&branch=${encodeURIComponent(fileData.branch)}` : undefined);

  return (
    <div
      data-testid="code-viewer-panel"
      className="flex-1 flex flex-col h-full bg-primary overflow-hidden text-slate-200"
    >
      {/* Code Header Bar */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-cohere-black/60 border-b border-white/10 shrink-0">
        <div className="flex items-center space-x-2.5 min-w-0">
          <FileCode className="w-4 h-4 text-amber-400 shrink-0" />
          <span className="font-mono text-xs font-semibold text-white truncate" title={path}>
            {path}
          </span>
          {fileData?.language && (
            <span className="px-2 py-0.5 rounded-pill text-[10px] font-mono bg-white/10 text-slate-300">
              {fileData.language}
            </span>
          )}
          {fileData?.size !== undefined && (
            <span className="text-[10px] font-mono text-slate-400">
              {formatBytes(fileData.size)}
            </span>
          )}
          {fileData?.source === "sandbox" && (
            <span className="px-1.5 py-0.5 rounded text-[9px] font-mono uppercase bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
              live container
            </span>
          )}
        </div>

        <div className="flex items-center space-x-2 shrink-0">
          {downloadUrl && (
            <a
              data-testid="download-file-button"
              href={downloadUrl}
              download
              className="flex items-center space-x-1 px-2.5 py-1 rounded-pill text-xs font-mono text-slate-300 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
              title="Download raw file"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download</span>
            </a>
          )}
          {fileData?.content && (
            <button
              data-testid="copy-code-button"
              type="button"
              onClick={handleCopy}
              className="flex items-center space-x-1 px-2.5 py-1 rounded-pill text-xs font-mono text-slate-300 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
              title="Copy code"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-pale-green" />
                  <span className="text-pale-green">Copied</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  <span>Copy</span>
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {/* Code / Content Area */}
      <div className="flex-1 overflow-auto bg-primary font-mono text-xs leading-relaxed">
        {fileData?.is_truncated ? (
          <div
            data-testid="code-viewer-truncated"
            className="flex flex-col items-center justify-center p-12 text-center h-full text-slate-300"
          >
            <div className="w-12 h-12 rounded-full bg-amber-500/20 text-amber-400 flex items-center justify-center mb-3">
              <FileWarning className="w-6 h-6" />
            </div>
            <h4 className="text-sm font-semibold text-white mb-1">
              File Exceeds Size Ceiling
            </h4>
            <p className="text-xs text-slate-400 max-w-md mb-3">
              {fileData.message || "This file exceeds the 500KB inspection ceiling."}
            </p>
            <div className="flex items-center space-x-3">
              <span className="px-2.5 py-1 rounded-pill bg-white/10 text-xs text-slate-300 font-mono">
                Size: {formatBytes(fileData.size)}
              </span>
              {downloadUrl && (
                <a
                  href={downloadUrl}
                  download
                  className="flex items-center space-x-1 px-3 py-1 rounded-pill bg-white text-primary text-xs font-semibold hover:bg-soft-stone transition-colors"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Download File</span>
                </a>
              )}
            </div>
          </div>
        ) : fileData?.is_binary ? (
          <div
            data-testid="code-viewer-binary"
            className="flex flex-col items-center justify-center p-12 text-center h-full text-slate-300"
          >
            <div className="w-12 h-12 rounded-full bg-blue-500/20 text-blue-400 flex items-center justify-center mb-3">
              <AlertTriangle className="w-6 h-6" />
            </div>
            <h4 className="text-sm font-semibold text-white mb-1">
              Binary File Detected
            </h4>
            <p className="text-xs text-slate-400 max-w-md mb-3">
              {fileData.message || "Binary files cannot be rendered as text."}
            </p>
            <div className="flex items-center space-x-3">
              <span className="px-2.5 py-1 rounded-pill bg-white/10 text-xs text-slate-300 font-mono">
                Size: {formatBytes(fileData.size)}
              </span>
              {downloadUrl && (
                <a
                  href={downloadUrl}
                  download
                  className="flex items-center space-x-1 px-3 py-1 rounded-pill bg-white text-primary text-xs font-semibold hover:bg-soft-stone transition-colors"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Download File</span>
                </a>
              )}
            </div>
          </div>
        ) : (
          <div className="py-2 flex">
            {/* Line Numbers */}
            <div className="select-none text-slate-500 text-right pr-3 pl-3 shrink-0 border-r border-white/10">
              {rawLines.map((_, idx) => (
                <div
                  key={idx}
                  data-testid={`line-number-${idx + 1}`}
                  className="leading-5 h-5 font-mono text-[11px]"
                >
                  {idx + 1}
                </div>
              ))}
            </div>

            {/* Syntax-Highlighted Code Lines */}
            <div className="pl-3 pr-6 flex-1 overflow-x-auto">
              {rawLines.map((line, idx) => (
                <div
                  key={idx}
                  className="leading-5 h-5 whitespace-pre font-mono text-[11px]"
                >
                  {renderSyntaxTokens(line, fileData?.language)}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
