import React from "react";

interface DiffSplitViewProps {
  patch: string;
}

interface SplitRow {
  type: "hunk" | "content";
  hunkHeader?: string;
  leftLineNumber?: number | string;
  leftText?: string;
  leftType?: "context" | "deletion" | "empty";
  rightLineNumber?: number | string;
  rightText?: string;
  rightType?: "context" | "addition" | "empty";
}

export function parseSplitDiff(patch: string): SplitRow[] {
  if (!patch) return [];
  const lines = patch.split(/\r?\n/);
  const rows: SplitRow[] = [];

  let oldLine = 0;
  let newLine = 0;

  let pendingDels: { lineNum: number; text: string }[] = [];
  let pendingAdds: { lineNum: number; text: string }[] = [];

  const flushPending = () => {
    const maxLen = Math.max(pendingDels.length, pendingAdds.length);
    for (let i = 0; i < maxLen; i++) {
      const del = pendingDels[i];
      const add = pendingAdds[i];
      rows.push({
        type: "content",
        leftLineNumber: del ? del.lineNum : "",
        leftText: del ? del.text : "",
        leftType: del ? "deletion" : "empty",
        rightLineNumber: add ? add.lineNum : "",
        rightText: add ? add.text : "",
        rightType: add ? "addition" : "empty",
      });
    }
    pendingDels = [];
    pendingAdds = [];
  };

  for (const line of lines) {
    if (line.startsWith("@@")) {
      flushPending();
      // Parse hunk header: @@ -old_start,old_count +new_start,new_count @@
      const m = line.match(/@@\s*-(\d+)(?:,\d+)?\s*\+(\d+)(?:,\d+)?\s*@@/);
      if (m) {
        oldLine = parseInt(m[1], 10);
        newLine = parseInt(m[2], 10);
      }
      rows.push({
        type: "hunk",
        hunkHeader: line,
      });
      continue;
    }

    if (line.startsWith("-") && !line.startsWith("---")) {
      pendingDels.push({ lineNum: oldLine++, text: line.slice(1) });
    } else if (line.startsWith("+") && !line.startsWith("+++")) {
      pendingAdds.push({ lineNum: newLine++, text: line.slice(1) });
    } else {
      // Context line or header line
      flushPending();
      const content = line.startsWith(" ") ? line.slice(1) : line;
      if (line.startsWith("---") || line.startsWith("+++")) {
        continue;
      }
      rows.push({
        type: "content",
        leftLineNumber: oldLine++,
        leftText: content,
        leftType: "context",
        rightLineNumber: newLine++,
        rightText: content,
        rightType: "context",
      });
    }
  }

  flushPending();
  return rows;
}

export const DiffSplitView: React.FC<DiffSplitViewProps> = ({ patch }) => {
  const rows = parseSplitDiff(patch);

  return (
    <div
      data-testid="diff-split-container"
      className="overflow-x-auto overflow-y-auto max-h-[480px] bg-primary border-t border-white/10 font-mono text-xs select-text"
    >
      <table className="w-full border-collapse table-fixed text-[11px] leading-snug">
        <colgroup>
          <col className="w-10" />
          <col className="w-[calc(50%-40px)]" />
          <col className="w-10" />
          <col className="w-[calc(50%-40px)]" />
        </colgroup>
        <tbody>
          {rows.map((row, idx) => {
            if (row.type === "hunk") {
              return (
                <tr key={idx} className="bg-white/5 border-y border-white/10">
                  <td
                    colSpan={4}
                    className="px-3 py-1 text-cyan-300 font-mono text-[10px] tracking-wide"
                  >
                    {row.hunkHeader}
                  </td>
                </tr>
              );
            }

            const isLeftDel = row.leftType === "deletion";
            const isRightAdd = row.rightType === "addition";

            return (
              <tr key={idx} className="hover:bg-white/[0.02] border-b border-white/[0.04]">
                {/* Left Line Number */}
                <td
                  className={`diff-split-left text-right px-2 py-0.5 select-none font-mono text-[10px] border-r border-white/5 ${
                    isLeftDel
                      ? "text-coral/70 bg-coral/15"
                      : "text-slate-600 bg-white/[0.01]"
                  }`}
                >
                  {row.leftLineNumber || ""}
                </td>

                {/* Left Code Text (Original/Base) */}
                <td
                  className={`diff-split-left px-2.5 py-0.5 font-mono overflow-x-hidden whitespace-pre-wrap break-all border-r border-white/10 ${
                    isLeftDel
                      ? "bg-coral/10 text-coral font-medium border-l-2 border-coral"
                      : row.leftType === "empty"
                      ? "bg-white/[0.01] text-transparent"
                      : "text-slate-300"
                  }`}
                >
                  {row.leftText || (row.leftType === "empty" ? "" : "\u00A0")}
                </td>

                {/* Right Line Number */}
                <td
                  className={`diff-split-right text-right px-2 py-0.5 select-none font-mono text-[10px] border-r border-white/5 ${
                    isRightAdd
                      ? "text-pale-green/70 bg-pale-green/15"
                      : "text-slate-600 bg-white/[0.01]"
                  }`}
                >
                  {row.rightLineNumber || ""}
                </td>

                {/* Right Code Text (Head/Modified) */}
                <td
                  className={`diff-split-right px-2.5 py-0.5 font-mono overflow-x-hidden whitespace-pre-wrap break-all ${
                    isRightAdd
                      ? "bg-pale-green/10 text-pale-green font-medium border-l-2 border-pale-green"
                      : row.rightType === "empty"
                      ? "bg-white/[0.01] text-transparent"
                      : "text-slate-300"
                  }`}
                >
                  {row.rightText || (row.rightType === "empty" ? "" : "\u00A0")}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};
