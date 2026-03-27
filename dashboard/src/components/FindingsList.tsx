import React, { useState } from "react";
import type { Finding } from "../types";

interface FindingsListProps {
  findings: Finding[];
}

const CATEGORIES = [
  "all",
  "memory_safety",
  "modernization",
  "complexity",
  "misra",
];

function severityBadge(severity: Finding["severity"]): React.ReactElement {
  const classes: Record<Finding["severity"], string> = {
    error: "bg-red-100 text-red-700 border border-red-200",
    warning: "bg-yellow-100 text-yellow-700 border border-yellow-200",
    info: "bg-blue-100 text-blue-700 border border-blue-200",
  };
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wide ${classes[severity]}`}
    >
      {severity}
    </span>
  );
}

function shortPath(path: string): string {
  const parts = path.split("/");
  if (parts.length <= 3) return path;
  return `.../${parts.slice(-2).join("/")}`;
}

export function FindingsList({
  findings,
}: FindingsListProps): React.ReactElement {
  const [category, setCategory] = useState("all");

  const filtered =
    category === "all"
      ? findings
      : findings.filter((f) => f.category === category);

  return (
    <div className="bg-white rounded-xl shadow p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-800">
          Findings{" "}
          <span className="text-sm font-normal text-gray-500">
            ({filtered.length})
          </span>
        </h2>
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="text-sm border border-gray-300 rounded px-2 py-1 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c === "all" ? "All categories" : c}
            </option>
          ))}
        </select>
      </div>

      {filtered.length === 0 ? (
        <p className="text-gray-400 text-sm">No findings for this category.</p>
      ) : (
        <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
          {filtered.map((f) => (
            <div
              key={f.id}
              className="border border-gray-100 rounded-lg p-3 hover:bg-gray-50 transition-colors"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    {severityBadge(f.severity)}
                    <span className="text-xs text-gray-500 font-mono">
                      {f.rule_id}
                    </span>
                    <span className="text-xs text-gray-400">
                      {shortPath(f.file)}:{f.line}
                    </span>
                  </div>
                  <p className="text-sm text-gray-700 mt-1">{f.message}</p>
                  {f.suggestion && (
                    <p className="text-xs text-blue-600 mt-1 italic">
                      Suggestion: {f.suggestion}
                    </p>
                  )}
                </div>
                <span className="text-xs text-gray-400 whitespace-nowrap">
                  {f.category}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
