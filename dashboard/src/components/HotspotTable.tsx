import React, { useState } from "react";
import type { Hotspot } from "../types";

interface HotspotTableProps {
  hotspots: Hotspot[];
}

type SortKey = keyof Hotspot;

function shortPath(path: string): string {
  const parts = path.split("/");
  if (parts.length <= 3) return path;
  return `.../${parts.slice(-2).join("/")}`;
}

export function HotspotTable({
  hotspots,
}: HotspotTableProps): React.ReactElement {
  const [sortKey, setSortKey] = useState<SortKey>("hotspot_score");
  const [sortAsc, setSortAsc] = useState(false);

  const sorted = [...hotspots]
    .sort((a, b) => {
      const aVal = a[sortKey];
      const bVal = b[sortKey];
      if (typeof aVal === "number" && typeof bVal === "number") {
        return sortAsc ? aVal - bVal : bVal - aVal;
      }
      return sortAsc
        ? String(aVal).localeCompare(String(bVal))
        : String(bVal).localeCompare(String(aVal));
    })
    .slice(0, 20);

  function handleSort(key: SortKey): void {
    if (key === sortKey) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  }

  function sortIndicator(key: SortKey): string {
    if (key !== sortKey) return "";
    return sortAsc ? " ↑" : " ↓";
  }

  const thClass =
    "px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide cursor-pointer select-none hover:text-gray-700";
  const tdClass = "px-3 py-2 text-sm text-gray-700 whitespace-nowrap";

  return (
    <div className="bg-white rounded-xl shadow p-6">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">
        Top Hotspot Files
      </h2>
      {sorted.length === 0 ? (
        <p className="text-gray-400 text-sm">No hotspot data available.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-gray-200">
                <th
                  className={thClass}
                  onClick={() => handleSort("file")}
                >
                  File{sortIndicator("file")}
                </th>
                <th
                  className={thClass}
                  onClick={() => handleSort("hotspot_score")}
                >
                  Hotspot Score{sortIndicator("hotspot_score")}
                </th>
                <th
                  className={thClass}
                  onClick={() => handleSort("change_frequency")}
                >
                  Change Freq{sortIndicator("change_frequency")}
                </th>
                <th
                  className={thClass}
                  onClick={() => handleSort("complexity_score")}
                >
                  Complexity{sortIndicator("complexity_score")}
                </th>
                <th
                  className={thClass}
                  onClick={() => handleSort("finding_count")}
                >
                  Findings{sortIndicator("finding_count")}
                </th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((h, i) => (
                <tr
                  key={h.file}
                  className={i % 2 === 0 ? "bg-white" : "bg-gray-50"}
                >
                  <td className={tdClass} title={h.file}>
                    <span className="font-mono text-xs">{shortPath(h.file)}</span>
                  </td>
                  <td className={tdClass}>
                    <span className="font-semibold text-red-600">
                      {h.hotspot_score.toFixed(2)}
                    </span>
                  </td>
                  <td className={tdClass}>{h.change_frequency}</td>
                  <td className={tdClass}>{h.complexity_score.toFixed(1)}</td>
                  <td className={tdClass}>{h.finding_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
